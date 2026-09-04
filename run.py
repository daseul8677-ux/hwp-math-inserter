# -*- coding: utf-8 -*-
"""문제 캡쳐 -> 한글 삽입기 실행.

  run.py             브라우저로 열리는 앱 실행 (기본)
  run.py --gui       예전 창(tkinter) 방식으로 실행
  run.py --selftest  한글 삽입이 되는지 점검하고 결과를 파일로 남김
  run.py --port 9000 다른 포트로 실행
"""

import os
import sys


def _base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _selftest():
    from hwpmath import selftest
    base = _base_dir()
    try:
        ok, report = selftest.run(base)
    except Exception:
        import traceback
        ok, report = False, "점검 중 오류:\n" + traceback.format_exc()
    path = os.path.join(base, "점검결과.txt")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(report)
    except Exception:
        pass
    try:
        print(report)
    except Exception:
        pass
    if getattr(sys, "frozen", False):
        import tkinter as tk
        import tkinter.messagebox as mb
        r = tk.Tk()
        r.withdraw()
        mb.showinfo("점검 결과", report)
        r.destroy()
    return 0 if ok else 1


def main():
    argv = sys.argv[1:]
    if "--selftest" in argv:
        sys.exit(_selftest())
    if "--gui" in argv:
        from hwpmath.app import main as app_main
        return app_main()

    port = None
    if "--port" in argv:
        try:
            port = int(argv[argv.index("--port") + 1])
        except (IndexError, ValueError):
            port = None

    from hwpmath.server import serve
    serve(port=port, open_browser="--no-browser" not in argv)


if __name__ == "__main__":
    main()
