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


def check(url):
    """새 판이 있는지 본다. 없으면 None."""
    if not url:
        return None
    try:
        r = requests.get(url, timeout=TIMEOUT,
                         headers={"Cache-Control": "no-cache"})
    except requests.RequestException as e:
        raise UpdateError("업데이트 확인 실패(인터넷): %s" % e)
    if r.status_code != 200:
        raise UpdateError("업데이트 확인 실패(%s)" % r.status_code)
    try:
        # 파일 앞에 BOM 이 붙어 있어도 읽히도록 utf-8-sig 로 푼다
        data = json.loads(r.content.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        raise UpdateError("업데이트 안내 파일을 읽지 못했습니다.")
    ver = str(data.get("version", "")).strip()
    if not ver or not data.get("url"):
        raise UpdateError("업데이트 안내 파일에 내용이 부족합니다.")
    if not is_newer(ver):
        return None
    return {"version": ver, "url": data["url"], "notes": data.get("notes", "")}


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
    return dest


def apply_and_restart(new_exe):
    """앱을 끄고, 새 파일로 바꾼 뒤 다시 켠다."""
    if not is_frozen():
        raise UpdateError("설치본(exe)에서만 업데이트할 수 있습니다.")
    target = exe_path()
    bat = os.path.join(tempfile.gettempdir(), "hwpmath_update_%d.bat" % int(time.time()))
    script = (
        '@echo off\r\n'
        'chcp 65001 > nul\r\n'
        'ping 127.0.0.1 -n 4 > nul\r\n'                 # 앱이 완전히 꺼질 때까지 잠깐
        ':wait\r\n'
        'move /y "%(new)s" "%(target)s" > nul 2>&1\r\n'
        'if errorlevel 1 (\r\n'
        '  ping 127.0.0.1 -n 3 > nul\r\n'
        '  goto wait\r\n'
        ')\r\n'
        'start "" "%(target)s"\r\n'
        'del "%%~f0"\r\n'
    ) % {"new": new_exe, "target": target}
    with open(bat, "w", encoding="utf-8") as f:
        f.write(script)

    creation = 0x00000008 | 0x08000000                  # DETACHED_PROCESS | NO_WINDOW
    subprocess.Popen(["cmd", "/c", bat], creationflags=creation,
                     close_fds=True, cwd=tempfile.gettempdir())
    return bat


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
