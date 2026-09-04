# -*- coding: utf-8 -*-
"""Gemini 로 문제 이미지 -> 마크업 텍스트."""

import base64
import io
import json

import requests

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT = """너는 시험지 이미지를 한글(HWP) 문서로 옮기는 조판 도우미다.
이미지에 보이는 문제를 **눈에 보이는 그대로** 옮겨 적어라. 문제를 풀지 말고, 해설도 붙이지 마라.

출력 형식 (이 형식 외에는 아무것도 쓰지 마라. 코드펜스 금지):
- 본문 줄은 그냥 그 줄의 글자를 쓴다. 글 속에 섞인 짧은 수식은 $...$ 안에 LaTeX 로 쓴다.
- 이미지에서 줄을 바꿔 가운데(또는 안쪽으로 들여써서) 따로 놓인 수식 줄은
  `[[EQ]] ` 로 시작하고 뒤에 LaTeX 만 쓴다. ($ 기호는 붙이지 않는다)
- 객관식 보기 줄은 `[[CH]] ` 로 시작하고, 보기끼리 ` | ` 로 나눈다.
  원문자 번호(①②③④⑤)는 그대로 두고, 값은 $...$ 로 감싼다.
- 이미지에서 줄이 바뀐 곳은 줄을 바꾸고, 비어 있는 줄은 빈 줄로 남긴다.

표(칸이 나뉜 표. 표준정규분포표 등):
- `[[TABLE]]` 로 시작하고 `[[/TABLE]]` 로 끝내며, 한 줄이 한 행, 칸은 ` | ` 로 나눈다.
  칸 안의 수식도 $...$ 로 감싼다. 행 개수와 칸 개수를 원본과 똑같이 맞춘다.
  예)
  [[TABLE]]
  $z$ | $P(0 \\leq Z \\leq z)$
  1.0 | 0.3413
  1.5 | 0.4332
  [[/TABLE]]

조건 상자(글 여러 줄을 감싼 큰 네모):
- (가), (나) 같은 조건이 큰 네모 상자 안에 여러 줄로 들어 있으면
  `[[BOX]]` 로 시작하고 `[[/BOX]]` 로 끝내며, 그 사이에 상자 안의 줄들을 그대로 쓴다.
  상자 안에서도 $...$ 와 [[EQ]] 규칙을 똑같이 쓴다.
  예)
  [[BOX]]
  (가) 선분 PR은 원 $C$의 지름이다.
  (나) $\\overline{PQ} = 4\\overline{QR}$
  [[/BOX]]

빈칸(네모 칸) 문제:
- 수식 안에 네모 칸이 그려져 있고 그 안에 (가), (나), (다) 같은 표시가 있으면
  `\\boxed{(가)}` 처럼 쓴다. 예: `b_{2n-1} = b_{2n} = \\boxed{(가)} \\quad (n \\geq 1)`
- 네모 칸 안이 비어 있으면 `\\boxed{\\quad}` 로 쓴다.
- 네모 칸을 그냥 괄호나 밑줄로 바꾸지 마라. 원본에 네모가 있으면 네모로 옮긴다.

지킬 것:
- 문제 번호, 배점 표기([3점] 등), 괄호, 쉼표, 마침표, 조사까지 원본 그대로.
- 없는 내용을 지어내지 말고, 안 보이는 글자는 추측하지 마라.
- 여러 문제가 있으면 문제 사이를 빈 줄로 나눈다.
- LaTeX 는 \\frac, \\sqrt, \\sum, \\int, \\lim, \\begin{cases} 같은 표준 명령만 쓴다.

예시 출력:
3. 등비수열 $\\{a_n\\}$이

[[EQ]] a_3+a_5=60, \\quad \\frac{a_4}{a_2}+\\frac{a_8}{a_6}=6

을 만족시킬 때, $a_1$의 값은? [3점]

[[CH]] ① $4$ | ② $\\frac{9}{2}$ | ③ $5$ | ④ $\\frac{11}{2}$ | ⑤ $6$
"""


class OcrError(Exception):
    pass


def _png_bytes(image):
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def recognize(image, api_key, model="gemini-2.5-flash", timeout=90, extra_hint=""):
    """PIL 이미지 -> 마크업 문자열."""
    if not api_key:
        raise OcrError("Gemini API 키가 없습니다. [설정]에서 키를 넣어 주세요.")

    prompt = PROMPT
    if extra_hint.strip():
        prompt += "\n추가 지시:\n" + extra_hint.strip()

    body = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": prompt},
                {"inline_data": {
                    "mime_type": "image/png",
                    "data": base64.b64encode(_png_bytes(image)).decode("ascii"),
                }},
            ],
        }],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 4096},
    }

    url = ENDPOINT.format(model=model)
    try:
        r = requests.post(
            url,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            data=json.dumps(body).encode("utf-8"),
            timeout=timeout,
        )
    except requests.RequestException as e:
        raise OcrError("네트워크 오류: %s" % e)

    if r.status_code == 429:
        raise OcrError("무료 사용 한도(분당/일일 요청 수)를 넘었습니다. 잠시 뒤 다시 시도하세요.")
    if r.status_code in (401, 403):
        raise OcrError("API 키가 잘못되었거나 권한이 없습니다. [설정]에서 키를 확인하세요.")
    if r.status_code != 200:
        raise OcrError("Gemini 오류 %s: %s" % (r.status_code, r.text[:300]))

    data = r.json()
    cands = data.get("candidates") or []
    if not cands:
        fb = data.get("promptFeedback", {})
        raise OcrError("인식 결과가 비었습니다. %s" % (fb or ""))
    parts = cands[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise OcrError("인식 결과가 비었습니다. 이미지가 너무 흐리지 않은지 확인해 주세요.")

    # 혹시 코드펜스로 감싸 왔으면 벗긴다
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text
