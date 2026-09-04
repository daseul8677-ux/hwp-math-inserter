# -*- coding: utf-8 -*-
"""한글 삽입 경로 점검용. 새 빈 문서에 예시 문제를 넣고 결과를 파일로 남긴다."""

import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from hwpmath import markup
from hwpmath.hwp_writer import HwpWriter, Options

HERE = os.path.dirname(os.path.abspath(__file__))

SAMPLE = r"""3. 등비수열 $\{a_n\}$이

[[EQ]] a_3+a_5=60, \quad \frac{a_4}{a_2}+\frac{a_8}{a_6}=6

을 만족시킬 때, $a_1$의 값은? [3점]

[[CH]] ① $4$ | ② $\frac{9}{2}$ | ③ $5$ | ④ $\frac{11}{2}$ | ⑤ $6$"""

w = HwpWriter()
hwp = w.connect()
print("한글 연결 OK, 열린 문서 수:", hwp.XHwpDocuments.Count)
hwp.XHwpDocuments.Add(0)

blocks = markup.parse(SAMPLE)
w.insert_blocks(blocks, Options(eq_size=10, eq_align="Center"))
print("삽입 완료")

hwp_path = os.path.join(HERE, "테스트결과.hwp")
pdf_path = os.path.join(HERE, "테스트결과.pdf")
hwp.SaveAs(hwp_path, "HWP", "")
print("저장:", hwp_path)
try:
    hwp.SaveAs(pdf_path, "PDF", "")
    print("저장:", pdf_path)
except Exception as e:
    print("PDF 저장 실패:", e)
