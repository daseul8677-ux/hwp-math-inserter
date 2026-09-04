# -*- coding: utf-8 -*-
"""인식 결과 마크업 <-> 블록 구조.

마크업 규칙 (사용자가 눈으로 보고 고칠 수 있는 형태)
    일반 줄            : 본문 문단. 인라인 수식은 $...$ 로 감싼다.
    [[EQ]] <latex>     : 독립 수식 문단 (앞뒤 줄 띄고 가운데 정렬)
    [[CH]] a | b | c   : 객관식 보기 문단 (항목 사이를 탭으로 벌림)
    빈 줄              : 빈 문단
"""

import re

_INLINE = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$", re.S)

EQ_TAG = "[[EQ]]"
CH_TAG = "[[CH]]"
BOX_TAG = "[[BOX]]"
BOX_END = "[[/BOX]]"
TB_TAG = "[[TABLE]]"
TB_END = "[[/TABLE]]"


def _runs(line):
    """'글 $x^2$ 글' -> [('text','글 '), ('eq','x^2'), ('text',' 글')]"""
    runs = []
    pos = 0
    for m in _INLINE.finditer(line):
        if m.start() > pos:
            runs.append(("text", line[pos:m.start()]))
        runs.append(("eq", (m.group(1) or m.group(2) or "").strip()))
        pos = m.end()
    if pos < len(line):
        runs.append(("text", line[pos:]))
    return [r for r in runs if r[1] != ""]


def parse(text):
    """마크업 문자열 -> 블록 리스트."""
    blocks = []
    lines = text.replace("\r\n", "\n").split("\n")
    n = 0
    while n < len(lines):
        raw = lines[n]
        line = raw.rstrip()
        stripped = line.strip()
        n += 1

        # 표: [[TABLE]] ... [[/TABLE]]  (줄 = 행, | = 칸 구분)
        if stripped.startswith(TB_TAG):
            rows = []
            first = stripped[len(TB_TAG):].strip()
            body = [first] if first else []
            while n < len(lines) and not lines[n].strip().startswith(TB_END):
                body.append(lines[n])
                n += 1
            n += 1                                   # [[/TABLE]] 건너뛰기
            for row in body:
                row = row.strip()
                if not row:
                    continue
                # ---- 구분선 줄(|---|---|)은 건너뛴다
                if set(row) <= set("|-: "):
                    continue
                if row.startswith("|"):
                    row = row[1:]
                if row.endswith("|"):
                    row = row[:-1]
                rows.append([_runs(cell.strip()) for cell in row.split("|")])
            if rows:
                blocks.append({"kind": "table", "rows": rows})
            continue

        # 조건 상자: [[BOX]] ... [[/BOX]]
        if stripped.startswith(BOX_TAG):
            inner = []
            first = stripped[len(BOX_TAG):].strip()
            if first:
                inner.append(first)
            while n < len(lines) and not lines[n].strip().startswith(BOX_END):
                inner.append(lines[n])
                n += 1
            n += 1                                   # [[/BOX]] 건너뛰기
            blocks.append({"kind": "box", "blocks": parse("\n".join(inner))})
            continue

        if not stripped:
            blocks.append({"kind": "blank"})
        elif stripped.startswith(EQ_TAG):
            blocks.append({"kind": "eq", "latex": stripped[len(EQ_TAG):].strip()})
        elif stripped.startswith(CH_TAG):
            items = [_runs(p.strip()) for p in stripped[len(CH_TAG):].split("|")]
            blocks.append({"kind": "choice", "items": [i for i in items if i]})
        else:
            blocks.append({"kind": "para", "runs": _runs(line)})
    # 끝의 빈 문단은 버린다
    while blocks and blocks[-1]["kind"] == "blank":
        blocks.pop()
    return blocks


def preview(blocks, convert):
    """블록 -> 한글에 들어갈 내용 미리보기(문자열). convert 는 latex2hwp.convert."""
    out = []
    for b in blocks:
        if b["kind"] == "blank":
            out.append("")
        elif b["kind"] == "eq":
            out.append("      [수식·가운데]  " + convert(b["latex"]))
        elif b["kind"] == "choice":
            cells = []
            for runs in b["items"]:
                cells.append("".join(
                    t if k == "text" else "[수식 %s]" % convert(t) for k, t in runs))
            out.append("\t".join(cells))
        else:
            out.append("".join(
                t if k == "text" else "[수식 %s]" % convert(t) for k, t in b["runs"]))
    return "\n".join(out)
