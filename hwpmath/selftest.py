# -*- coding: utf-8 -*-
"""한글 연결/삽입이 되는지 스스로 점검한다.

안전 규칙 — 점검은 **임시 문서 하나**만 새로 만들어서 거기에만 넣고,
그 문서를 정해진 경로로 저장한 뒤 **그 경로가 일치하는 문서만** 닫는다.
사용자가 열어 둔 문서는 어떤 경우에도 닫지 않는다.
"""

import os
import tempfile

SAMPLE = r"""3. 등비수열 $\{a_n\}$이

[[EQ]] a_3+a_5=60, \quad \frac{a_4}{a_2}+\frac{a_8}{a_6}=6

을 만족시킬 때, $a_1$의 값은? [3점]

[[CH]] ① $4$ | ② $\frac{9}{2}$ | ③ $5$ | ④ $\frac{11}{2}$ | ⑤ $6$"""

SAMPLE2 = r"""1. 이차방정식 $x^2+1=0$ 의 해는? [2점]

[[CH]] ① $i$ | ② $-i$"""

SAMPLE3 = r"""9. 원 $C$ 위의 세 점이 다음 조건을 만족시킨다.

[[BOX]]
(가) 선분 PR은 원 $C$의 지름이다.
(나) $\overline{PQ} = 4\overline{QR}$
[[/BOX]]

$b_{2n-1} = \boxed{(가)}$ 일 때의 값은? [4점]"""

SAMPLE4 = r"""20. 아래 표를 이용하여 구한 값은? [4점]

[[TABLE]]
$z$ | $P(0 \leq Z \leq z)$
1.0 | 0.3413
1.5 | 0.4332
[[/TABLE]]"""

EXPECTED_EQ = 8
EXPECTED_EQ2 = 3


def _counts(hwp):
    """문서 안의 개체 종류별 개수."""
    kinds = {}
    ctrl = hwp.HeadCtrl
    while ctrl:
        kinds[ctrl.CtrlID] = kinds.get(ctrl.CtrlID, 0) + 1
        ctrl = ctrl.Next
    return kinds


def run(save_dir=None, writer=None):
    """writer 를 넘기면 그 연결(웹 서버가 쓰는 것)을 그대로 점검한다."""
    lines = []

    def log(msg):
        lines.append(str(msg))

    from . import markup
    from .hwp_writer import HwpWriter, Options
    from .latex2hwp import convert

    opts = Options(eq_size=11, eq_align="Center")

    log("[1] LaTeX -> 한글 수식 변환")
    got = convert(r"a_3+a_5=60, \quad \frac{a_4}{a_2}=6")
    log("    " + got)
    ok_conv = "a_{3}" in got and "over" in got
    log("    " + ("OK" if ok_conv else "실패: 첨자/분수 변환이 이상함"))

    log("[2] 한글 연결")
    w = writer or HwpWriter()
    hwp = w.connect()
    before = hwp.XHwpDocuments.Count
    log("    OK (이미 열려 있는 문서 %d개)" % before)
    try:
        for d in w.documents():
            log("      · %s%s" % (d["name"], "  <- 지금 보고 있는 문서" if d["active"] else ""))
    except Exception:
        pass
    log("    * 점검은 임시 문서 하나에서만 하고, 열어 두신 문서는 닫지도 고치지도 않습니다.")

    out_dir = save_dir or tempfile.gettempdir()
    tmp_path = os.path.join(out_dir, "점검결과.hwp")

    log("[3] 점검용 임시 문서 만들기")
    hwp.XHwpDocuments.Add(0)
    base = _counts(hwp)
    log("    OK")

    def delta(kind, since):
        return _counts(hwp).get(kind, 0) - since.get(kind, 0)

    log("[4] 한 문제 넣기")
    mark = _counts(hwp)
    w.insert_blocks(markup.parse(SAMPLE), opts)
    n = delta("eqed", mark)
    ok_eq = n == EXPECTED_EQ
    log("    수식 %d개 (기대값 %d) %s" % (n, EXPECTED_EQ, "OK" if ok_eq else "실패"))

    log("[5] 여러 문제 한꺼번에 넣기")
    w._break()
    mark = _counts(hwp)
    w.insert_many([markup.parse(SAMPLE), markup.parse(SAMPLE2)], opts, gap=1)
    m = delta("eqed", mark)
    ok_many = m == EXPECTED_EQ + EXPECTED_EQ2
    log("    수식 %d개 (기대값 %d) %s"
        % (m, EXPECTED_EQ + EXPECTED_EQ2, "OK" if ok_many else "실패"))

    log("[6] 조건 상자 + 수식 빈칸 네모")
    w._break()
    mark = _counts(hwp)
    w.insert_blocks(markup.parse(SAMPLE3), opts)
    boxes = delta("tbl", mark)
    ok_box = boxes == 1 and delta("eqed", mark) >= 4
    log("    상자 %d개 (기대값 1) %s" % (boxes, "OK" if ok_box else "실패"))

    log("[7] 표")
    w._break()
    mark = _counts(hwp)
    w.insert_blocks(markup.parse(SAMPLE4), opts)
    tables = delta("tbl", mark)
    ok_tbl = tables == 1
    log("    표 %d개 (기대값 1) %s" % (tables, "OK" if ok_tbl else "실패"))

    log("[8] 결과 저장")
    saved = False
    try:
        hwp.SaveAs(tmp_path, "HWP", "")
        saved = True
        log("    %s" % tmp_path)
    except Exception as e:
        log("    저장 실패: %s" % e)

    log("[9] 임시 문서만 닫기")
    if not saved:
        log("    저장이 안 돼 임시 문서를 남겨 둡니다. 직접 닫아 주세요(저장 안 함).")
    else:
        target = os.path.abspath(tmp_path).lower()
        closed = 0
        try:
            for d in w.documents():
                if (d["path"] or "").lower() == target:
                    doc = hwp.XHwpDocuments.Item(d["index"])
                    doc.SetActive_XHwpDocument()
                    doc.Close(False)
                    closed += 1
                    break
        except Exception as e:
            log("    닫기 실패(직접 닫아 주세요): %s" % e)
        log("    임시 문서 %d개 닫음 (남은 문서 %d개)" % (closed, hwp.XHwpDocuments.Count))
        if hwp.XHwpDocuments.Count != before:
            log("    ※ 문서 수가 점검 전(%d개)과 다릅니다. 한글 창을 확인해 주세요." % before)

    ok = ok_conv and ok_eq and ok_many and ok_box and ok_tbl
    lines.append("")
    lines.append("=== %s ===" % ("전체 통과" if ok else "문제 있음"))
    return ok, "\n".join(lines)
