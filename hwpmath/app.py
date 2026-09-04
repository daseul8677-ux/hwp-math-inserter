# -*- coding: utf-8 -*-
"""문제 캡쳐 -> 한글 삽입기 (GUI)."""

import os
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageGrab, ImageTk

from . import config as cfg
from . import markup, ocr
from .hwp_writer import HwpError, HwpWriter, Options
from .latex2hwp import convert

TITLE = "문제 캡쳐 → 한글 삽입기"


class App(object):
    def __init__(self, root):
        self.root = root
        self.conf = cfg.load()
        self.image = None
        self.photo = None
        self.writer = HwpWriter()
        self.busy = False

        root.title(TITLE)
        root.geometry("1180x760")
        self._build()
        self._bind()
        self._status("Win+Shift+S 로 문제를 캡쳐한 뒤 Ctrl+V 를 누르세요.")

    # ---------------- 화면 ----------------
    def _build(self):
        bar = ttk.Frame(self.root, padding=(8, 8, 8, 4))
        bar.pack(fill="x")

        def btn(text, cmd, width=18):
            b = ttk.Button(bar, text=text, command=cmd, width=width)
            b.pack(side="left", padx=3)
            return b

        self.b_paste = btn("① 붙여넣기  Ctrl+V", self.paste)
        self.b_open = btn("파일 열기", self.open_file, 12)
        self.b_ocr = btn("② 인식하기  Ctrl+R", self.recognize)
        self.b_insert = btn("③ 한글에 삽입  Ctrl+Enter",
                            self.insert_to_hwp, 22)
        btn("이미지 그대로 삽입", self.insert_picture, 16)
        btn("설정", self.settings, 8)

        pane = ttk.PanedWindow(self.root, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=8, pady=4)

        left = ttk.LabelFrame(pane, text="캡쳐한 이미지", padding=4)
        self.canvas = tk.Canvas(left, bg="#f4f4f4", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        pane.add(left, weight=4)

        right = ttk.Frame(pane)
        pane.add(right, weight=5)

        nb = ttk.Notebook(right)
        nb.pack(fill="both", expand=True)

        f1 = ttk.Frame(nb, padding=4)
        self.txt = tk.Text(f1, wrap="word", font=("맑은 고딕", 11),
                           undo=True, spacing1=2, spacing3=2)
        s1 = ttk.Scrollbar(f1, command=self.txt.yview)
        self.txt.configure(yscrollcommand=s1.set)
        s1.pack(side="right", fill="y")
        self.txt.pack(fill="both", expand=True)
        nb.add(f1, text="인식 결과 (여기서 고치세요)")

        f2 = ttk.Frame(nb, padding=4)
        self.prev = tk.Text(f2, wrap="word", font=("D2Coding", 10),
                            background="#fbfbf7")
        s2 = ttk.Scrollbar(f2, command=self.prev.yview)
        self.prev.configure(yscrollcommand=s2.set)
        s2.pack(side="right", fill="y")
        self.prev.pack(fill="both", expand=True)
        nb.add(f2, text="한글에 들어갈 모양 / 수식 스크립트")
        self.nb = nb
        nb.bind("<<NotebookTabChanged>>", lambda e: self._refresh_preview())

        help_ = ("[[EQ]] 줄 = 따로 떨어진 수식 문단 (앞뒤 줄 띄고 가운데)      "
                 "[[CH]] 줄 = 보기 문단 ( | 로 구분, 탭 간격)      "
                 "$...$ = 글 속의 수식")
        ttk.Label(right, text=help_, foreground="#555").pack(fill="x", pady=(4, 0))

        self.status = ttk.Label(self.root, text="", relief="sunken",
                                anchor="w", padding=(6, 3))
        self.status.pack(fill="x", side="bottom")

    def _bind(self):
        r = self.root
        r.bind("<Control-v>", lambda e: (self.paste(), "break")[1])
        r.bind("<Control-V>", lambda e: (self.paste(), "break")[1])
        r.bind("<Control-r>", lambda e: self.recognize())
        r.bind("<Control-Return>", lambda e: self.insert_to_hwp())
        self.canvas.bind("<Configure>", lambda e: self._draw())

    def _status(self, msg):
        self.status.configure(text=msg)
        self.root.update_idletasks()

    def _lock(self, on):
        self.busy = on
        state = "disabled" if on else "normal"
        for b in (self.b_paste, self.b_ocr, self.b_insert, self.b_open):
            b.configure(state=state)

    # ---------------- 이미지 ----------------
    def _set_image(self, img):
        self.image = img
        self._draw()

    def _draw(self):
        self.canvas.delete("all")
        if self.image is None:
            self.canvas.create_text(
                self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2,
                text="여기에 캡쳐 이미지가 보입니다\n\nWin+Shift+S 로 캡쳐 → Ctrl+V",
                fill="#999", justify="center", font=("맑은 고딕", 11))
            return
        cw = max(self.canvas.winfo_width() - 8, 50)
        ch = max(self.canvas.winfo_height() - 8, 50)
        img = self.image.copy()
        img.thumbnail((cw, ch), Image.LANCZOS)
        self.photo = ImageTk.PhotoImage(img)
        self.canvas.create_image(cw // 2 + 4, ch // 2 + 4, image=self.photo)

    def paste(self):
        try:
            data = ImageGrab.grabclipboard()
        except Exception as e:
            messagebox.showerror(TITLE, "클립보드를 읽지 못했습니다: %s" % e)
            return
        if isinstance(data, list):
            paths = [p for p in data if os.path.splitext(p)[1].lower()
                     in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")]
            if not paths:
                self._status("클립보드에 이미지가 없습니다.")
                return
            data = Image.open(paths[0])
        if data is None:
            self._status("클립보드에 이미지가 없습니다. 캡쳐를 먼저 하세요.")
            return
        self._set_image(data)
        self._status("이미지를 받았습니다. [② 인식하기] 를 누르세요. (Ctrl+R)")

    def open_file(self):
        path = filedialog.askopenfilename(
            title="문제 이미지 열기",
            filetypes=[("이미지", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("모든 파일", "*.*")])
        if path:
            self._set_image(Image.open(path))
            self._status("%s 를 불러왔습니다." % os.path.basename(path))

    # ---------------- 인식 ----------------
    def recognize(self):
        if self.busy:
            return
        if self.image is None:
            self._status("먼저 이미지를 붙여넣으세요.")
            return
        if not self.conf.get("api_key"):
            messagebox.showinfo(TITLE, "먼저 [설정]에서 Gemini API 키를 넣어 주세요.\n"
                                       "https://aistudio.google.com/apikey 에서 무료로 발급됩니다.")
            self.settings()
            return
        self._lock(True)
        self._status("Gemini 로 인식하는 중… (몇 초 걸립니다)")

        def work():
            try:
                text = ocr.recognize(self.image, self.conf["api_key"],
                                     self.conf.get("model", "gemini-2.5-flash"),
                                     extra_hint=self.conf.get("hint", ""))
                self.root.after(0, self._ocr_done, text, None)
            except Exception as e:
                self.root.after(0, self._ocr_done, None, e)

        threading.Thread(target=work, daemon=True).start()

    def _ocr_done(self, text, err):
        self._lock(False)
        if err:
            self._status("인식 실패")
            messagebox.showerror(TITLE, str(err))
            return
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", text)
        self._refresh_preview()
        self._status("인식 끝. 틀린 곳을 고친 뒤 [③ 한글에 삽입] (Ctrl+Enter)")

    def _refresh_preview(self):
        try:
            blocks = markup.parse(self.txt.get("1.0", "end-1c"))
            body = markup.preview(blocks, convert)
            scripts = ["· %s" % convert(b["latex"])
                       for b in blocks if b["kind"] == "eq"]
            extra = ("\n\n── 독립 수식 스크립트 ──\n" + "\n".join(scripts)) if scripts else ""
            self.prev.delete("1.0", "end")
            self.prev.insert("1.0", body + extra)
        except Exception as e:
            self.prev.delete("1.0", "end")
            self.prev.insert("1.0", "미리보기 오류: %s" % e)

    # ---------------- 한글 삽입 ----------------
    def _options(self):
        c = self.conf
        return Options(eq_size=c["eq_size"], eq_align=c["eq_align"],
                       eq_indent_mm=c["eq_indent_mm"], body_align=c["body_align"],
                       blank_before_eq=c["blank_before_eq"],
                       blank_after_eq=c["blank_after_eq"],
                       choice_sep=c["choice_sep"], choice_spaces=c["choice_spaces"])

    def insert_to_hwp(self):
        text = self.txt.get("1.0", "end-1c").strip()
        if not text:
            self._status("삽입할 내용이 없습니다.")
            return
        blocks = markup.parse(text)
        self._status("한글에 넣는 중…")
        try:
            self.writer.insert_blocks(blocks, self._options())
        except HwpError as e:
            self._status("삽입 실패")
            messagebox.showerror(TITLE, str(e))
            return
        except Exception as e:
            self._status("삽입 실패")
            messagebox.showerror(TITLE,
                                 "한글에 넣는 중 오류가 났습니다:\n%s\n\n"
                                 "한글이 열려 있는지, 커서가 문서 안에 있는지 확인해 주세요." % e)
            return
        self._status("한글 커서 위치에 넣었습니다.")

    def insert_picture(self):
        if self.image is None:
            self._status("먼저 이미지를 붙여넣으세요.")
            return
        path = os.path.join(tempfile.gettempdir(), "hwpmath_capture.png")
        self.image.save(path)
        try:
            self.writer.insert_picture(path)
            self._status("이미지를 한글에 그대로 넣었습니다.")
        except Exception as e:
            messagebox.showerror(TITLE, "이미지 삽입 실패: %s" % e)

    # ---------------- 설정 ----------------
    def settings(self):
        d = tk.Toplevel(self.root)
        d.title("설정")
        d.transient(self.root)
        d.resizable(False, False)
        f = ttk.Frame(d, padding=12)
        f.pack(fill="both", expand=True)
        row = [0]

        def add(label, widget):
            ttk.Label(f, text=label).grid(row=row[0], column=0, sticky="w", pady=4, padx=(0, 10))
            widget.grid(row=row[0], column=1, sticky="we", pady=4)
            row[0] += 1

        v_key = tk.StringVar(value=self.conf["api_key"])
        v_model = tk.StringVar(value=self.conf["model"])
        v_size = tk.StringVar(value=str(self.conf["eq_size"]))
        v_align = tk.StringVar(value=self.conf["eq_align"])
        v_indent = tk.StringVar(value=str(self.conf["eq_indent_mm"]))
        v_sep = tk.StringVar(value=self.conf["choice_sep"])
        v_b1 = tk.BooleanVar(value=self.conf["blank_before_eq"])
        v_b2 = tk.BooleanVar(value=self.conf["blank_after_eq"])
        v_hint = tk.StringVar(value=self.conf.get("hint", ""))

        add("Gemini API 키", ttk.Entry(f, textvariable=v_key, width=46, show="*"))
        add("모델", ttk.Combobox(f, textvariable=v_model, width=44, values=[
            "gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"]))
        add("수식 글자 크기(pt)", ttk.Entry(f, textvariable=v_size, width=10))
        add("독립 수식 문단 정렬", ttk.Combobox(f, textvariable=v_align, width=14, state="readonly",
                                       values=["Center", "Left", "Justify"]))
        add("독립 수식 왼쪽 들여쓰기(mm)", ttk.Entry(f, textvariable=v_indent, width=10))
        add("보기 사이 간격", ttk.Combobox(f, textvariable=v_sep, width=14, state="readonly",
                                    values=["tab", "space"]))
        ttk.Checkbutton(f, text="수식 앞에 빈 줄", variable=v_b1).grid(
            row=row[0], column=1, sticky="w"); row[0] += 1
        ttk.Checkbutton(f, text="수식 뒤에 빈 줄", variable=v_b2).grid(
            row=row[0], column=1, sticky="w"); row[0] += 1
        add("인식 추가 지시(선택)", ttk.Entry(f, textvariable=v_hint, width=46))

        ttk.Label(f, text="키 발급: https://aistudio.google.com/apikey  (무료)",
                  foreground="#666").grid(row=row[0], column=0, columnspan=2,
                                          sticky="w", pady=(8, 0))
        row[0] += 1

        def ok():
            self.conf.update({
                "api_key": v_key.get().strip(),
                "model": v_model.get().strip() or "gemini-2.5-flash",
                "eq_size": float(v_size.get() or 10),
                "eq_align": v_align.get(),
                "eq_indent_mm": float(v_indent.get() or 0),
                "choice_sep": v_sep.get(),
                "blank_before_eq": v_b1.get(),
                "blank_after_eq": v_b2.get(),
                "hint": v_hint.get().strip(),
            })
            cfg.save(self.conf)
            d.destroy()
            self._status("설정을 저장했습니다.")

        box = ttk.Frame(f)
        box.grid(row=row[0], column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(box, text="취소", command=d.destroy, width=10).pack(side="right", padx=4)
        ttk.Button(box, text="저장", command=ok, width=10).pack(side="right")
        f.columnconfigure(1, weight=1)
        d.grab_set()


def main():
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
