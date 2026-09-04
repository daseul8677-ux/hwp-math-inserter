# -*- coding: utf-8 -*-
"""실행 중인 한글(HWP)의 커서 위치에 문제를 그대로 조판해 넣는다."""

import os

from .latex2hwp import convert

try:
    import win32com.client as win32
except ImportError:          # pywin32 미설치 환경에서도 import 는 되게
    win32 = None

_ALIGN_FALLBACK = {"Justify": 0, "Left": 1, "Right": 2, "Center": 3, "Distribute": 4}


class HwpError(Exception):
    pass


class Options(object):
    def __init__(self, **kw):
        self.eq_size = kw.get("eq_size", 10)          # 수식 글자 크기(pt)
        self.eq_align = kw.get("eq_align", "Center")  # 독립 수식 문단 정렬
        self.eq_indent_mm = kw.get("eq_indent_mm", 0) # 왼쪽 들여쓰기(mm)
        self.body_align = kw.get("body_align", "Justify")
        self.blank_before_eq = kw.get("blank_before_eq", True)
        self.blank_after_eq = kw.get("blank_after_eq", True)
        self.choice_sep = kw.get("choice_sep", "tab") # "tab" 또는 "space"
        self.choice_spaces = kw.get("choice_spaces", 6)
        self.box_width_mm = kw.get("box_width_mm", 150)   # 조건 상자 너비
        self.table_col_mm = kw.get("table_col_mm", 30)    # 표 한 칸 너비
        self.table_align = kw.get("table_align", "Center")


class HwpWriter(object):
    def __init__(self):
        self.hwp = None
        self._registered = False
        self._attach_errors = []

    # ---------- 연결 ----------
    def _running_hwp(self):
        """이미 켜져 있는 한글에 붙는다.

        한글은 MS오피스와 달리 GetActiveObject 로 잡히지 않는다.
        대신 실행 중인 개체 목록(ROT)에 '!HwpObject.130.1' 같은 이름으로 올라와 있어서,
        그 목록을 직접 뒤져 붙는다. -> 사용자가 열어 둔 문서에 그대로 넣을 수 있다.

        컴퓨터에 따라 한글 COM 이 레지스트리에 등록돼 있지 않은 경우가 있는데,
        그때는 win32com 의 일반 Dispatch 가 형식 정보를 찾다가 실패한다.
        그래서 레지스트리를 보지 않는 늦은 바인딩(dynamic)을 먼저 쓴다.
        """
        self._attach_errors = []
        if win32 is None:
            self._attach_errors.append("pywin32 를 불러오지 못했습니다.")
            return None
        try:
            import pythoncom
            from win32com.client import dynamic
        except Exception as e:
            self._attach_errors.append("pythoncom 을 불러오지 못했습니다: %s" % e)
            return None
        try:
            ctx = pythoncom.CreateBindCtx(0)
            rot = pythoncom.GetRunningObjectTable()
        except Exception as e:
            self._attach_errors.append("실행 중인 개체 목록을 읽지 못했습니다: %s" % e)
            return None

        for moniker in rot:
            try:
                name = moniker.GetDisplayName(ctx, None)
            except Exception:
                continue
            if "hwpobject" not in name.lower():
                continue
            try:
                unk = rot.GetObject(moniker)
                disp = unk.QueryInterface(pythoncom.IID_IDispatch)
            except Exception as e:
                self._attach_errors.append("%s 에서 개체를 얻지 못했습니다: %s" % (name, e))
                continue
            # 레지스트리를 보지 않는 방식 먼저, 그다음 일반 방식
            for how, maker in (("늦은 바인딩", dynamic.Dispatch),
                               ("일반", win32.Dispatch)):
                try:
                    obj = maker(disp)
                    obj.XHwpDocuments.Count          # 정말 쓸 수 있는지 확인
                    return obj
                except Exception as e:
                    self._attach_errors.append("%s(%s) 연결 실패: %s" % (name, how, e))

        # 목록에서 못 찾으면 표준 방식도 한 번 시도한다
        try:
            return win32.GetActiveObject("HWPFrame.HwpObject")
        except Exception as e:
            self._attach_errors.append("GetActiveObject 실패: %s" % e)
            return None

    def diagnose(self):
        """왜 한글을 못 찾는지 알아보기 위한 정보 모으기."""
        info = {"rot": [], "hwp_monikers": [], "notes": []}

        try:
            import ctypes
            info["admin"] = bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception as e:
            info["admin"] = "확인 실패 (%s)" % e

        if win32 is None:
            info["notes"].append("pywin32 를 불러오지 못했습니다.")
            return info
        try:
            import pythoncom
        except Exception as e:
            info["notes"].append("pythoncom 을 불러오지 못했습니다: %s" % e)
            return info

        try:
            ctx = pythoncom.CreateBindCtx(0)
            rot = pythoncom.GetRunningObjectTable()
            for moniker in rot:
                try:
                    name = moniker.GetDisplayName(ctx, None)
                except Exception as e:
                    name = "<이름 확인 실패: %s>" % e
                info["rot"].append(name)
                if "hwp" in name.lower():
                    info["hwp_monikers"].append(name)
        except Exception as e:
            info["notes"].append("실행 중인 개체 목록(ROT)을 읽지 못했습니다: %s" % e)

        try:
            win32.GetActiveObject("HWPFrame.HwpObject")
            info["get_active_object"] = "성공"
        except Exception as e:
            info["get_active_object"] = "실패 (%s)" % e

        # 실제로 붙어 보고, 실패했다면 그 이유를 그대로 담는다
        try:
            obj = self._running_hwp()
            info["attach"] = "성공" if obj is not None else "실패"
        except Exception as e:
            info["attach"] = "실패 (%s)" % e
        info["attach_errors"] = list(self._attach_errors)

        if not info["hwp_monikers"]:
            info["notes"].append(
                "실행 중인 한글이 목록에 없습니다. 한글이 정말 실행 중인지, "
                "그리고 이 앱과 한글 중 하나만 '관리자 권한으로 실행' 되어 있지는 않은지 확인해 주세요. "
                "(권한이 다르면 서로를 보지 못합니다)")
        return info

    def _alive(self):
        if self.hwp is None:
            return False
        try:
            self.hwp.XHwpDocuments.Count
            return True
        except Exception:
            return False

    def connect(self, launch_if_needed=False):
        """켜져 있는 한글에 붙는다. 없으면 (launch_if_needed 일 때만) 새로 띄운다."""
        if win32 is None:
            raise HwpError("pywin32 가 설치되어 있지 않습니다. pip install pywin32")

        obj = self._running_hwp()
        if obj is not None:
            self.hwp = obj
        elif not self._alive():
            if not launch_if_needed:
                raise HwpError("켜져 있는 한글을 찾지 못했습니다. "
                               "한글에서 문제를 넣을 문서를 열고 커서를 둔 뒤 다시 눌러 주세요.")
            try:
                self.hwp = win32.Dispatch("HWPFrame.HwpObject")
                self.hwp.XHwpWindows.Item(0).Visible = True
            except Exception as e:
                raise HwpError("한글을 실행하지 못했습니다: %s" % e)

        if not self._registered:
            try:
                # 파일 경로 확인 보안 모듈 (등록돼 있으면 승인창이 안 뜬다)
                self.hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
            except Exception:
                pass
            self._registered = True

        if self.hwp.XHwpDocuments.Count == 0:
            self.hwp.XHwpDocuments.Add(0)
        return self.hwp

    def _need(self):
        # 넣을 때마다 다시 붙는다 -> 사용자가 그 사이에 연 문서에도 바로 들어간다
        return self.connect()

    # ---------- 문서 ----------
    def documents(self):
        """열려 있는 문서 목록."""
        hwp = self._need()
        out = []
        try:
            active = hwp.XHwpDocuments.Active_XHwpDocument
        except Exception:
            active = None
        for i in range(hwp.XHwpDocuments.Count):
            doc = hwp.XHwpDocuments.Item(i)
            try:
                path = doc.FullName or ""
            except Exception:
                path = ""
            same = False
            try:
                same = active is not None and doc.FullName == active.FullName
            except Exception:
                pass
            out.append({
                "index": i,
                "path": path,
                "name": os.path.basename(path) if path else "빈 문서 %d" % (i + 1),
                "active": same,
            })
        return out

    def use_document(self, index):
        """넣을 문서를 고른다."""
        hwp = self._need()
        if index is None or index < 0 or index >= hwp.XHwpDocuments.Count:
            return False
        try:
            hwp.XHwpDocuments.Item(index).SetActive_XHwpDocument()
            return True
        except Exception:
            return False

    # ---------- 낱개 동작 ----------
    @staticmethod
    def _set(pset, name, value):
        """파라미터셋 값 넣기.

        exe 로 묶으면 타입 정보(gen_py) 없이 동적 바인딩으로 붙어서
        속성 대입이 안 될 수 있다. 그때는 SetItem 으로 넣는다.
        """
        try:
            setattr(pset, name, value)
            return True
        except Exception:
            pass
        try:
            pset.HSet.SetItem(name, value)
            return True
        except Exception:
            return False

    def _run(self, action):
        self.hwp.HAction.Run(action)

    def _break(self):
        self._run("BreakPara")

    def _text(self, s):
        if not s:
            return
        hwp = self.hwp
        pset = hwp.HParameterSet.HInsertText
        hwp.HAction.GetDefault("InsertText", pset.HSet)
        self._set(pset, "Text", s)
        hwp.HAction.Execute("InsertText", pset.HSet)

    def _equation(self, script, size_pt):
        if not script:
            return
        hwp = self.hwp
        pset = hwp.HParameterSet.HEqEdit
        hwp.HAction.GetDefault("EquationCreate", pset.HSet)
        self._set(pset, "string", script)
        self._set(pset, "Version", "Equation Version 60")
        try:
            unit = hwp.PointToHwpUnit(float(size_pt))
        except Exception:
            unit = int(float(size_pt) * 100)
        self._set(pset, "BaseUnit", unit)
        hwp.HAction.Execute("EquationCreate", pset.HSet)
        # 여기서 Close 를 부르면 표(조건 상자) 칸 밖으로 커서가 튀어나간다. 부르지 않는다.

    def _align(self, name, indent_mm=0):
        hwp = self.hwp
        try:
            value = hwp.HAlign(name)
        except Exception:
            value = _ALIGN_FALLBACK.get(name, 0)
        pset = hwp.HParameterSet.HParaShape
        hwp.HAction.GetDefault("ParagraphShape", pset.HSet)
        self._set(pset, "AlignType", value)
        try:
            self._set(pset, "LeftMargin", hwp.MiliToHwpUnit(float(indent_mm)))
        except Exception:
            pass
        hwp.HAction.Execute("ParagraphShape", pset.HSet)

    def _runs(self, runs, size_pt):
        for kind, value in runs:
            if kind == "text":
                self._text(value)
            else:
                self._equation(convert(value), size_pt)

    # ---------- 본 작업 ----------
    def insert_blocks(self, blocks, opts=None):
        opts = opts or Options()
        hwp = self._need()
        first = True
        for n, b in enumerate(blocks):
            if not first:
                self._break()
            first = False
            kind = b["kind"]
            prev_blank = n > 0 and blocks[n - 1]["kind"] == "blank"
            next_blank = n + 1 < len(blocks) and blocks[n + 1]["kind"] == "blank"

            if kind == "blank":
                self._align(opts.body_align, 0)

            elif kind == "eq":
                # 인식 결과에 이미 빈 줄이 있으면 또 넣지 않는다
                if opts.blank_before_eq and not prev_blank and n > 0:
                    self._align(opts.body_align, 0)
                    self._break()
                self._align(opts.eq_align, opts.eq_indent_mm)
                self._equation(convert(b["latex"]), opts.eq_size)
                if opts.blank_after_eq and not next_blank and n + 1 < len(blocks):
                    self._break()
                    self._align(opts.body_align, 0)

            elif kind == "box":
                self._align(opts.body_align, 0)
                self.insert_box(b["blocks"], opts)

            elif kind == "table":
                self.insert_table(b["rows"], opts)

            elif kind == "choice":
                self._align(opts.body_align, 0)
                for k, runs in enumerate(b["items"]):
                    if k:
                        if opts.choice_sep == "tab":
                            self._run("InsertTab")
                        else:
                            self._text(" " * opts.choice_spaces)
                    self._runs(runs, opts.eq_size)

            else:  # para
                self._align(opts.body_align, 0)
                self._runs(b["runs"], opts.eq_size)
        return True

    def insert_box(self, blocks, opts=None):
        """조건 상자 — 한 칸짜리 표를 만들고 그 안에 내용을 넣는다."""
        opts = opts or Options()
        hwp = self._need()
        pos = hwp.GetPos()                      # (list, para, pos)

        pset = hwp.HParameterSet.HTableCreation
        hwp.HAction.GetDefault("TableCreate", pset.HSet)
        self._set(pset, "Rows", 1)
        self._set(pset, "Cols", 1)
        self._set(pset, "WidthType", 1)         # 1 = 문단(글자 너비)에 맞춤
        self._set(pset, "HeightType", 0)        # 0 = 자동
        try:
            pset.CreateItemArray("ColWidth", 1)
            pset.ColWidth.SetItem(0, hwp.MiliToHwpUnit(float(opts.box_width_mm)))
        except Exception:
            pass
        hwp.HAction.Execute("TableCreate", pset.HSet)

        # 칸 안에 내용
        self.insert_blocks(blocks, opts)

        # 표 밖(다음 문단)으로 빠져나오기
        try:
            hwp.SetPos(pos[0], pos[1] + 1, 0)
        except Exception:
            try:
                self._run("MoveDown")
            except Exception:
                pass
        return True

    def insert_table(self, rows, opts=None):
        """표 — 행/열이 있는 표를 만들고 칸마다 내용을 넣는다.

        rows 는 [[runs, runs, ...], ...] 형태. runs 는 ('text'|'eq', 값) 목록.
        """
        opts = opts or Options()
        hwp = self._need()
        if not rows:
            return False
        n_rows = len(rows)
        n_cols = max(len(r) for r in rows)
        if n_cols < 1:
            return False

        # 열 수에 맞춰 적당한 너비 (사용자가 한글에서 다시 조절할 수 있다)
        width = opts.table_col_mm * n_cols
        width = max(35.0, min(float(opts.box_width_mm), width))

        pos = hwp.GetPos()
        self._align(opts.table_align, 0)

        pset = hwp.HParameterSet.HTableCreation
        hwp.HAction.GetDefault("TableCreate", pset.HSet)
        self._set(pset, "Rows", n_rows)
        self._set(pset, "Cols", n_cols)
        self._set(pset, "WidthType", 2)            # 2 = 임의 값
        self._set(pset, "HeightType", 0)           # 0 = 자동
        self._set(pset, "WidthValue", hwp.MiliToHwpUnit(width))
        try:
            pset.CreateItemArray("ColWidth", n_cols)
            for c in range(n_cols):
                pset.ColWidth.SetItem(c, hwp.MiliToHwpUnit(width / n_cols))
        except Exception:
            pass
        hwp.HAction.Execute("TableCreate", pset.HSet)

        for r, row in enumerate(rows):
            for c in range(n_cols):
                if r or c:
                    self._run("TableRightCell")
                self._align("Center", 0)
                if c < len(row):
                    self._runs(row[c], opts.eq_size)

        try:
            hwp.SetPos(pos[0], pos[1] + 1, 0)
        except Exception:
            try:
                self._run("MoveDown")
            except Exception:
                pass
        return True

    def insert_many(self, docs, opts=None, gap=1):
        """여러 문제를 이어서 넣는다. gap = 문제 사이에 둘 빈 줄 수."""
        opts = opts or Options()
        self._need()
        for i, blocks in enumerate(docs):
            if not blocks:
                continue
            if i:
                for _ in range(max(0, int(gap)) + 1):
                    self._break()
                self._align(opts.body_align, 0)
            self.insert_blocks(blocks, opts)
        return True

    def insert_picture(self, path):
        hwp = self._need()
        path = os.path.abspath(path)
        try:
            hwp.InsertPicture(path, True, 0, False, False, 0, 0, 0)
            return True
        except Exception:
            pass
        pset = hwp.HParameterSet.HInsertPicture
        hwp.HAction.GetDefault("InsertPicture", pset.HSet)
        self._set(pset, "FileName", path)
        self._set(pset, "Embedded", True)
        hwp.HAction.Execute("InsertPicture", pset.HSet)
        return True
