# -*- coding: utf-8 -*-
"""스스로 새 버전을 받아 갈아 끼우기.

인터넷에 올려 둔 작은 안내 파일(latest.json)을 읽어 새 판이 있는지 보고,
있으면 새 exe 를 내려받은 뒤 작은 배치 파일로 자기 자신을 바꿔치기한다.
(실행 중인 exe 는 스스로를 덮어쓸 수 없어서, 앱이 꺼진 뒤 바꾸는 방식이다)

latest.json 모양:
    {"version": "1.1.0",
     "url": "https://.../문제캡쳐한글삽입기.exe",
     "notes": "무엇이 바뀌었는지 한 줄"}
"""

import base64
import json
import os
import subprocess
import sys
import tempfile
import time

import requests

from .version import VERSION

TIMEOUT = 15
MIN_SIZE = 5 * 1024 * 1024          # 내려받은 파일이 이보다 작으면 뭔가 잘못된 것


class UpdateError(Exception):
    pass


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def exe_path():
    return os.path.abspath(sys.executable)


def _tuple(v):
    out = []
    for part in str(v).strip().split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out + [0] * (4 - len(out)))[:4]


def is_newer(latest, current=VERSION):
    return _tuple(latest) > _tuple(current)


def _from_github_api(data):
    """GitHub 릴리스 API 응답에서 판 번호와 내려받을 주소를 뽑는다."""
    ver = str(data.get("tag_name", "")).strip().lstrip("vV")
    url = ""
    for asset in data.get("assets", []):
        if str(asset.get("name", "")).lower().endswith(".exe"):
            url = asset.get("browser_download_url", "")
            break
    notes = (data.get("body") or data.get("name") or "").strip()
    if len(notes) > 200:
        notes = notes[:200] + "…"
    return ver, url, notes


def check(url):
    """새 판이 있는지 본다. 없으면 None.

    GitHub 릴리스 API 주소면 그걸 그대로 쓰고,
    직접 만든 안내 파일(latest.json) 주소면 그 내용을 읽는다.

    (raw.githubusercontent 는 몇 분간 옛 내용을 캐시해서 주기 때문에
     기본값은 캐시가 없는 릴리스 API 를 쓴다.)
    """
    if not url:
        return None
    try:
        r = requests.get(url, timeout=TIMEOUT,
                         headers={"Cache-Control": "no-cache", "Pragma": "no-cache",
                                  "Accept": "application/vnd.github+json"})
    except requests.RequestException as e:
        raise UpdateError("업데이트 확인 실패(인터넷): %s" % e)
    if r.status_code != 200:
        raise UpdateError("업데이트 확인 실패(%s)" % r.status_code)
    try:
        data = json.loads(r.content.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        raise UpdateError("업데이트 안내 파일을 읽지 못했습니다.")

    if "tag_name" in data:
        ver, dl, notes = _from_github_api(data)
    else:
        ver = str(data.get("version", "")).strip()
        dl = data.get("url", "")
        notes = data.get("notes", "")
    if not ver or not dl:
        raise UpdateError("업데이트 안내에 내용이 부족합니다.")
    if not is_newer(ver):
        return None
    return {"version": ver, "url": dl, "notes": notes}


def download(url, dest):
    try:
        r = requests.get(url, timeout=120, stream=True)
    except requests.RequestException as e:
        raise UpdateError("새 파일을 받지 못했습니다: %s" % e)
    if r.status_code != 200:
        raise UpdateError("새 파일을 받지 못했습니다(%s)" % r.status_code)
    size = 0
    with open(dest, "wb") as f:
        for chunk in r.iter_content(1024 * 256):
            if chunk:
                f.write(chunk)
                size += len(chunk)
    if size < MIN_SIZE:
        try:
            os.remove(dest)
        except OSError:
            pass
        raise UpdateError("받은 파일이 온전하지 않습니다(%d바이트)." % size)
    _unblock(dest)
    return dest


def _unblock(path):
    """인터넷에서 받은 표시(차단 표시)를 지운다.

    이게 남아 있으면 윈도우가 실행을 막거나 경고창을 띄워서,
    업데이트 뒤 앱이 스스로 다시 켜지지 못한다.
    """
    try:
        os.remove(path + ":Zone.Identifier")
    except OSError:
        pass


def apply_and_restart(new_exe):
    """앱을 끄고, 새 파일로 바꾼 뒤 다시 켠다.

    배치(.bat) 파일은 쓰지 않는다. cmd 가 배치 파일을 옛 문자표(CP949)로 읽어서
    경로에 한글이 있으면 깨지기 때문이다.
    대신 PowerShell 에 UTF-16 으로 인코딩한 명령을 넘긴다 — 문자표 문제가 없다.
    """
    if not is_frozen():
        raise UpdateError("설치본(exe)에서만 업데이트할 수 있습니다.")
    target = exe_path()

    log = os.path.join(tempfile.gettempdir(), "hwpmath_update.log")
    ps = (
        "$log = %s\n"
        "function Say($m) { Add-Content -LiteralPath $log -Value \"$(Get-Date -Format o)  $m\" }\n"
        "Say 'start'\n"
        "Start-Sleep -Seconds 3\n"
        "$src = %s\n"
        "$dst = %s\n"
        "$ok = $false\n"
        "for ($i = 0; $i -lt 60; $i++) {\n"
        "  try { Move-Item -LiteralPath $src -Destination $dst -Force; $ok = $true; break }\n"
        "  catch { Start-Sleep -Seconds 2 }\n"
        "}\n"
        "Say \"moved=$ok\"\n"
        "if ($ok) {\n"
        "  try { Unblock-File -LiteralPath $dst -ErrorAction SilentlyContinue } catch {}\n"
        "  try { Start-Process -FilePath $dst -WorkingDirectory (Split-Path -Parent $dst); Say 'relaunched' }\n"
        "  catch { Say \"relaunch failed: $_\" }\n"
        "} else { Say 'move failed' }\n"
    ) % (_ps_quote(log), _ps_quote(new_exe), _ps_quote(target))

    encoded = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    powershell = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                              "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    if not os.path.exists(powershell):
        powershell = "powershell"
    # DETACHED_PROCESS 와 CREATE_NO_WINDOW 는 같이 쓸 수 없다(프로세스 생성 자체가 실패).
    # 창만 숨기면 충분하고, 부모가 꺼져도 자식은 계속 돈다.
    creation = 0x08000000                               # CREATE_NO_WINDOW
    # 창 없는 exe 는 표준 입출력이 없어서, 넘겨줄 것을 명시해야 자식이 뜬다
    subprocess.Popen(
        [powershell, "-NoProfile", "-NonInteractive",
         "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
         "-EncodedCommand", encoded],
        creationflags=creation, close_fds=True, cwd=tempfile.gettempdir(),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def _ps_quote(path):
    """PowerShell 작은따옴표 문자열로 감싼다."""
    return "'" + str(path).replace("'", "''") + "'"


def update_now(url):
    """확인 -> 내려받기 -> 바꿔치기. 성공하면 앱이 곧 꺼진다."""
    info = check(url)
    if not info:
        return None
    folder = os.path.dirname(exe_path()) if is_frozen() else tempfile.gettempdir()
    staged = os.path.join(tempfile.gettempdir(),
                          "문제캡쳐한글삽입기_%s.exe" % info["version"])
    download(info["url"], staged)
    apply_and_restart(staged)
    return info
