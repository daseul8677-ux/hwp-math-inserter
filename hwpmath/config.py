# -*- coding: utf-8 -*-
"""설정 저장/불러오기.

exe 로 묶었을 때는 exe 가 있는 폴더에 config.json 을 둔다(들고 다니기 편하게).
그 폴더에 쓸 수 없으면 %APPDATA%\\hwpmath 로 넘어간다.
"""

import json
import os
import sys


def _base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _writable(folder):
    probe = os.path.join(folder, ".write_test")
    try:
        with open(probe, "w") as f:
            f.write("")
        os.remove(probe)
        return True
    except Exception:
        return False


def _config_path():
    base = _base_dir()
    if _writable(base):
        return os.path.join(base, "config.json")
    fallback = os.path.join(os.environ.get("APPDATA", base), "hwpmath")
    try:
        os.makedirs(fallback, exist_ok=True)
    except Exception:
        pass
    return os.path.join(fallback, "config.json")


PATH = _config_path()

DEFAULTS = {
    "api_key": "",
    "model": "gemini-2.5-flash",
    "eq_size": 10,
    "eq_align": "Center",
    "eq_indent_mm": 0,
    "body_align": "Justify",
    "blank_before_eq": True,
    "blank_after_eq": True,
    "choice_sep": "tab",
    "choice_spaces": 6,
    "problem_gap": 1,
    "update_url": ("https://api.github.com/repos/"
                   "daseul8677-ux/hwp-math-inserter/releases/latest"),
    "hint": "",
}


def load():
    data = dict(DEFAULTS)
    if os.path.exists(PATH):
        try:
            with open(PATH, "r", encoding="utf-8") as f:
                data.update(json.load(f))
        except Exception:
            pass
    if not data.get("api_key"):
        data["api_key"] = os.environ.get("GEMINI_API_KEY", "")
    return data


def save(data):
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
