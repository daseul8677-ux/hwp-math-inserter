# -*- coding: utf-8 -*-
"""내 컴퓨터 안에서 도는 작은 웹 서버.

브라우저로 쓰지만 서버가 이 PC 안에 있어서, 한글(HWP)을 직접 조작할 수 있다.
(인터넷에 올린 서버는 사용자 PC 의 한글을 건드릴 수 없다.)
"""

import base64
import binascii
import io
import json
import os
import queue
import socket
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

from . import config as cfg
from . import markup, ocr
from .hwp_writer import HwpWriter, Options
from .latex2hwp import convert

DEFAULT_PORT = 8765
MAX_BODY = 24 * 1024 * 1024      # 이미지 업로드 상한


def resource_dir():
    """web 폴더 위치 (exe 로 묶였을 때 포함)."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "web")


# --------------------------------------------------------------------------
# 한글 작업 전담 스레드
#   COM 개체는 만든 스레드에서만 안전하게 쓸 수 있어서, 한 스레드가 도맡는다.
# --------------------------------------------------------------------------
class HwpWorker(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self, daemon=True)
        self.jobs = queue.Queue()
        self.writer = None

    def run(self):
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        self.writer = HwpWriter()
        while True:
            fn, box, done = self.jobs.get()
            try:
                box["result"] = fn(self.writer)
                box["ok"] = True
            except Exception as e:
                box["ok"] = False
                box["error"] = str(e)
                box["trace"] = traceback.format_exc()
            finally:
                done.set()

    def call(self, fn, timeout=120):
        box, done = {}, threading.Event()
        self.jobs.put((fn, box, done))
        if not done.wait(timeout):
            raise RuntimeError("한글이 응답하지 않습니다. 한글 창에 열려 있는 대화상자가 없는지 확인해 주세요.")
        if not box.get("ok"):
            raise RuntimeError(box.get("error", "알 수 없는 오류"))
        return box.get("result")


WORKER = HwpWorker()


# --------------------------------------------------------------------------
def _options(conf):
    return Options(eq_size=conf["eq_size"], eq_align=conf["eq_align"],
                   eq_indent_mm=conf["eq_indent_mm"], body_align=conf["body_align"],
                   blank_before_eq=conf["blank_before_eq"],
                   blank_after_eq=conf["blank_after_eq"],
                   choice_sep=conf["choice_sep"], choice_spaces=conf["choice_spaces"])


def _decode_image(data_url):
    if not data_url:
        raise ValueError("이미지가 없습니다.")
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    try:
        raw = base64.b64decode(data_url)
    except (binascii.Error, ValueError):
        raise ValueError("이미지를 읽지 못했습니다.")
    return Image.open(io.BytesIO(raw))


class Handler(BaseHTTPRequestHandler):
    server_version = "hwpmath"

    def log_message(self, fmt, *args):
        pass                                   # 콘솔 조용히

    # ---------- 공통 ----------
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError):
            pass

    def _json_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            # 본문을 끝까지 버려야 연결이 끊기지 않고 오류 메시지가 전달된다
            left = n
            while left > 0:
                chunk = self.rfile.read(min(65536, left))
                if not chunk:
                    break
                left -= len(chunk)
            raise ValueError("이미지가 너무 큽니다. 문제 하나씩 잘라서 캡쳐해 주세요.")
        if n <= 0:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def _guard_origin(self):
        """다른 사이트가 이 로컬 서버를 몰래 부르지 못하게 막는다."""
        origin = self.headers.get("Origin")
        if origin and not (origin.startswith("http://127.0.0.1:")
                           or origin.startswith("http://localhost:")):
            self._send(403, {"error": "허용되지 않은 요청입니다."})
            return False
        return True

    # ---------- GET ----------
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._file("index.html", "text/html; charset=utf-8")
        if path == "/api/config":
            conf = dict(cfg.load())
            conf["api_key_set"] = bool(conf.pop("api_key", ""))
            return self._send(200, conf)
        if path == "/api/hwp":
            try:
                docs = WORKER.call(lambda w: w.documents(), timeout=60)
                active = next((d for d in docs if d["active"]), None)
                return self._send(200, {
                    "connected": True,
                    "docs": docs,
                    "count": len(docs),
                    "active": active["name"] if active else (docs[0]["name"] if docs else ""),
                })
            except Exception as e:
                return self._send(200, {"connected": False, "error": str(e), "docs": []})
        return self._send(404, {"error": "없는 주소입니다."})

    def _file(self, name, ctype):
        path = os.path.join(resource_dir(), name)
        if not os.path.exists(path):
            return self._send(404, "web/%s 를 찾지 못했습니다." % name, "text/plain; charset=utf-8")
        with open(path, "rb") as f:
            return self._send(200, f.read(), ctype)

    # ---------- POST ----------
    def do_POST(self):
        if not self._guard_origin():
            return
        path = self.path.split("?", 1)[0]
        try:
            data = self._json_body()
        except Exception as e:
            return self._send(400, {"error": str(e)})

        try:
            if path == "/api/recognize":
                return self._recognize(data)
            if path == "/api/preview":
                return self._preview(data)
            if path == "/api/insert":
                return self._insert(data)
            if path == "/api/insert-image":
                return self._insert_image(data)
            if path == "/api/config":
                return self._config(data)
            if path == "/api/version":
                from . import updater
                from .version import VERSION
                conf = cfg.load()
                out = {"version": VERSION, "frozen": updater.is_frozen(),
                       "url_set": bool(conf.get("update_url"))}
                if data.get("check") and conf.get("update_url"):
                    try:
                        out["latest"] = updater.check(conf["update_url"])
                    except updater.UpdateError as e:
                        out["error"] = str(e)
                return self._send(200, out)

            if path == "/api/update":
                from . import updater
                conf = cfg.load()
                if not conf.get("update_url"):
                    return self._send(400, {"error": "설정에서 업데이트 주소를 넣어 주세요."})
                if not updater.is_frozen():
                    return self._send(400, {"error": "설치본(exe)에서만 업데이트할 수 있습니다."})
                try:
                    info = updater.update_now(conf["update_url"])
                except updater.UpdateError as e:
                    return self._send(400, {"error": str(e)})
                if not info:
                    return self._send(200, {"ok": True, "updated": False})
                threading.Timer(1.0, lambda: os._exit(0)).start()
                return self._send(200, {"ok": True, "updated": True,
                                        "version": info["version"]})

            if path == "/api/diagnose":
                info = WORKER.call(lambda w: w.diagnose(), timeout=90)
                lines = ["[한글 연결 진단]", ""]
                lines.append("이 앱이 관리자 권한으로 실행 중: %s" % info.get("admin"))
                lines.append("한글에 붙기: %s" % info.get("attach"))
                lines.append("GetActiveObject: %s" % info.get("get_active_object"))
                if info.get("attach_errors"):
                    lines.append("")
                    lines.append("연결 실패 사유:")
                    lines += ["  ! " + s for s in info["attach_errors"]]
                lines.append("")
                if info.get("hwp_monikers"):
                    lines.append("찾은 한글 항목:")
                    lines += ["  · " + s for s in info["hwp_monikers"]]
                else:
                    lines.append("찾은 한글 항목: 없음")
                lines.append("")
                lines.append("실행 중인 개체 목록 (%d개):" % len(info.get("rot", [])))
                lines += ["  - " + s for s in info.get("rot", [])[:40]]
                if info.get("notes"):
                    lines.append("")
                    lines += info["notes"]
                return self._send(200, {"report": "\n".join(lines), "info": info})

            if path == "/api/hwp-launch":
                def job(w):
                    w.connect(launch_if_needed=True)
                    return w.documents()
                docs = WORKER.call(job, timeout=180)
                return self._send(200, {"ok": True, "docs": docs})

            if path == "/api/selftest":
                from . import selftest
                base = os.path.dirname(cfg.PATH)
                ok, report = WORKER.call(
                    lambda w: selftest.run(base, w), timeout=240)
                return self._send(200, {"ok": ok, "report": report})
            if path == "/api/quit":
                threading.Timer(0.3, lambda: os._exit(0)).start()
                return self._send(200, {"ok": True})
        except Exception as e:
            return self._send(500, {"error": str(e)})
        return self._send(404, {"error": "없는 주소입니다."})

    def _recognize(self, data):
        conf = cfg.load()
        if not conf.get("api_key"):
            return self._send(400, {"error": "먼저 설정에서 Gemini API 키를 넣어 주세요."})
        image = _decode_image(data.get("image"))
        try:
            text = ocr.recognize(image, conf["api_key"], conf.get("model"),
                                 extra_hint=conf.get("hint", ""))
        except ocr.OcrError as e:
            return self._send(400, {"error": str(e)})
        return self._send(200, {"markup": text})

    def _preview(self, data):
        text = data.get("markup", "")
        return self._send(200, {"blocks": self._blocks(markup.parse(text))})

    def _blocks(self, blocks):
        out = []
        for b in blocks:
            if b["kind"] == "blank":
                out.append({"kind": "blank"})
            elif b["kind"] == "eq":
                out.append({"kind": "eq", "latex": b["latex"],
                            "script": convert(b["latex"])})
            elif b["kind"] == "box":
                out.append({"kind": "box", "blocks": self._blocks(b["blocks"])})
            elif b["kind"] == "table":
                out.append({"kind": "table", "rows": [
                    [[{"type": k, "value": v, "script": convert(v) if k == "eq" else ""}
                      for k, v in cell] for cell in row] for row in b["rows"]]})
            elif b["kind"] == "choice":
                out.append({"kind": "choice", "items": [
                    [{"type": k, "value": v, "script": convert(v) if k == "eq" else ""}
                     for k, v in runs] for runs in b["items"]]})
            else:
                out.append({"kind": "para", "runs": [
                    {"type": k, "value": v, "script": convert(v) if k == "eq" else ""}
                    for k, v in b["runs"]]})
        return out

    def _insert(self, data):
        texts = data.get("markups")
        if texts is None:
            texts = [data.get("markup") or ""]
        texts = [t.strip() for t in texts if (t or "").strip()]
        if not texts:
            return self._send(400, {"error": "넣을 내용이 없습니다."})
        conf = cfg.load()
        docs = [markup.parse(t) for t in texts]
        opts = _options(conf)
        gap = int(conf.get("problem_gap", 1))
        target = data.get("doc")
        try:
            target = int(target)
        except (TypeError, ValueError):
            target = None

        def job(w):
            if target is not None:
                w.use_document(target)
            w.insert_many(docs, opts, gap)
            names = [d["name"] for d in w.documents() if d["active"]]
            return names[0] if names else ""

        where = WORKER.call(job, timeout=60 + 40 * len(docs))
        return self._send(200, {"ok": True, "count": len(docs), "doc": where})

    def _insert_image(self, data):
        import tempfile
        image = _decode_image(data.get("image"))
        path = os.path.join(tempfile.gettempdir(), "hwpmath_capture.png")
        image.save(path)
        try:
            target = int(data.get("doc"))
        except (TypeError, ValueError):
            target = None

        def job(w):
            if target is not None:
                w.use_document(target)
            return w.insert_picture(path)

        WORKER.call(job)
        return self._send(200, {"ok": True})

    def _config(self, data):
        conf = cfg.load()
        for key in ("model", "eq_align", "body_align", "choice_sep", "hint", "update_url"):
            if key in data:
                conf[key] = data[key]
        for key in ("eq_size", "eq_indent_mm", "choice_spaces", "problem_gap"):
            if key in data:
                try:
                    conf[key] = float(data[key])
                except (TypeError, ValueError):
                    pass
        for key in ("blank_before_eq", "blank_after_eq"):
            if key in data:
                conf[key] = bool(data[key])
        if data.get("api_key"):                 # 빈 값이면 기존 키 유지
            conf["api_key"] = data["api_key"].strip()
        cfg.save(conf)
        out = dict(conf)
        out["api_key_set"] = bool(out.pop("api_key", ""))
        return self._send(200, out)


def find_port(start=DEFAULT_PORT, tries=20):
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return start


def serve(port=None, open_browser=True):
    port = port or find_port()
    WORKER.start()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = "http://127.0.0.1:%d/" % port
    if open_browser:
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    # exe(창 없음) 로 실행하면 stdout 이 없을 수 있다
    if sys.stdout:
        try:
            print("문제 캡쳐 → 한글 삽입기: %s" % url)
            print("끝낼 때는 웹 화면 오른쪽 위 [종료] 를 누르세요.")
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return url
