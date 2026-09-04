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
import hashlib
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
    """GitHub 릴리스 API 응답에서 판 번호, 주소, 크기, 지문을 뽑는다."""
    ver = str(data.get("tag_name", "")).strip().lstrip("vV")
    url, size, digest = "", 0, ""
    for asset in data.get("assets", []):
        if str(asset.get("name", "")).lower().endswith(".exe"):
            url = asset.get("browser_download_url", "")
            size = int(asset.get("size") or 0)
            digest = str(asset.get("digest") or "")
            if digest.lower().startswith("sha256:"):
                digest = digest.split(":", 1)[1].strip().lower()
            else:
                digest = ""
            break
    notes = (data.get("body") or data.get("name") or "").strip()
    if len(notes) > 200:
        notes = notes[:200] + "…"
    return ver, url, notes, size, digest


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
        ver, dl, notes, size, digest = _from_github_api(data)
    else:
        ver = str(data.get("version", "")).strip()
        dl = data.get("url", "")
        notes = data.get("notes", "")
        size = int(data.get("size") or 0)
        digest = str(data.get("sha256") or "").lower()
    if not ver or not dl:
        raise UpdateError("업데이트 안내에 내용이 부족합니다.")
    if not is_newer(ver):
        return None
    return {"version": ver, "url": dl, "notes": notes,
            "size": size, "sha256": digest}


def download(url, dest, expect_size=0, expect_sha256=""):
    """새 파일을 받고, 온전한지 반드시 확인한다.

    확인 없이 갈아 끼우면 반쯤 받다 만 파일이 설치되어
    프로그램이 아예 실행되지 않는다(파이썬 DLL 을 못 찾는 오류).
    """
    try:
        r = requests.get(url, timeout=180, stream=True)
    except requests.RequestException as e:
        raise UpdateError("새 파일을 받지 못했습니다: %s" % e)
    if r.status_code != 200:
        raise UpdateError("새 파일을 받지 못했습니다(%s)" % r.status_code)

    declared = 0
    try:
        declared = int(r.headers.get("Content-Length") or 0)
    except ValueError:
        declared = 0

    digest = hashlib.sha256()
    size = 0
    try:
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1024 * 256):
                if chunk:
                    f.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
    except (OSError, requests.RequestException) as e:
        _drop(dest)
        raise UpdateError("새 파일을 받는 중 끊겼습니다: %s" % e)

    def bad(msg):
        _drop(dest)
        raise UpdateError("받은 파일이 온전하지 않아 설치하지 않았습니다. %s" % msg)

    if size < MIN_SIZE:
        bad("크기가 %.1fMB 뿐입니다." % (size / 1048576.0))
    if declared and size != declared:
        bad("%.1fMB 중 %.1fMB 만 받았습니다." % (declared / 1048576.0, size / 1048576.0))
    if expect_size and size != expect_size:
        bad("크기가 다릅니다(%d != %d)." % (size, expect_size))
    if expect_sha256 and digest.hexdigest().lower() != expect_sha256:
        bad("파일 지문이 다릅니다.")

    _unblock(dest)
    return dest


def _drop(path):
    try:
        os.remove(path)
    except OSError:
        pass


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
        "$bak = $dst + '.bak'\n"
        "$name = [IO.Path]::GetFileNameWithoutExtension($dst)\n"
        "$ok = $false\n"
        # 옛 파일을 옆으로 치워 두고 새 파일을 넣는다. 잘못되면 되돌릴 수 있다.
        "for ($i = 0; $i -lt 60; $i++) {\n"
        "  try {\n"
        "    if (Test-Path -LiteralPath $bak) { Remove-Item -LiteralPath $bak -Force }\n"
        "    Move-Item -LiteralPath $dst -Destination $bak -Force\n"
        "    Move-Item -LiteralPath $src -Destination $dst -Force\n"
        "    $ok = $true; break\n"
        "  } catch { Start-Sleep -Seconds 2 }\n"
        "}\n"
        "Say \"moved=$ok\"\n"
        "if (-not $ok) { Say 'move failed'; exit }\n"
        "try { Unblock-File -LiteralPath $dst -ErrorAction SilentlyContinue } catch {}\n"
        # explorer 로 띄운다. 우리 프로세스 사슬에서 완전히 떨어져 나가,
        # 사용자가 직접 더블클릭한 것과 같은 상태로 실행된다.
        "try { Start-Process -FilePath 'explorer.exe' -ArgumentList \"`\"$dst`\"\"; Say 'launched' }\n"
        "catch { Say \"launch failed: $_\" }\n"
        "Start-Sleep -Seconds 15\n"
        "$running = Get-Process -Name $name -ErrorAction SilentlyContinue\n"
        "if (-not $running) {\n"
        # 새 파일이 안 돌아가면 옛 파일로 되돌린다
        "  Say 'not running - restoring previous version'\n"
        "  try {\n"
        "    Move-Item -LiteralPath $dst -Destination ($dst + '.broken') -Force\n"
        "    Move-Item -LiteralPath $bak -Destination $dst -Force\n"
        "    Start-Process -FilePath 'explorer.exe' -ArgumentList \"`\"$dst`\"\"\n"
        "    Say 'restored'\n"
        "  } catch { Say \"restore failed: $_\" }\n"
        "} else {\n"
        "  Say 'confirmed running'\n"
        "  try { Remove-Item -LiteralPath $bak -Force } catch {}\n"
        "}\n"
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
    staged = os.path.join(tempfile.gettempdir(),
                          "hwpmath_new_%s.exe" % info["version"])
    download(info["url"], staged,
             expect_size=info.get("size", 0),
             expect_sha256=info.get("sha256", ""))
    apply_and_restart(staged)
    return info
