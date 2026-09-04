# -*- coding: utf-8 -*-
"""LaTeX -> 한글(HWP) 수식 스크립트 변환기.

한글 수식 편집기 스크립트는 LaTeX와 비슷하지만 다르다.
  \\frac{a}{b}       ->  {a} over {b}
  \\sqrt{x}          ->  sqrt {x}
  \\sum_{i=1}^{n}    ->  sum from {i=1} to {n}
  \\alpha            ->  alpha        (백슬래시 없음)
"""

# 백슬래시만 떼면 되는 기호 (한글 수식이 같은 이름을 안다)
_PLAIN = set((
    "alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota "
    "kappa lambda mu nu xi pi varpi rho sigma varsigma tau upsilon phi varphi "
    "chi psi omega "
    "Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega "
    "sin cos tan cot sec csc sinh cosh tanh log ln exp max min gcd det "
    "arcsin arccos arctan "
    "cdot cdots ldots vdots ddots times div "
    "in ni subset supset subseteq supseteq cup cap emptyset "
    "angle triangle perp parallel circ prime partial nabla "
    "equiv sim simeq approx propto therefore because forall exists "
    "oplus otimes bullet ast star deg notin"
).split())

# 이름이 다른 기호
_SYMBOL = {
    "leq": "<=", "le": "<=", "geq": ">=", "ge": ">=",
    "neq": "<>", "ne": "<>", "ll": "<<", "gg": ">>",
    "pm": "+-", "mp": "-+",
    "infty": "inf", "infinity": "inf",
    "to": "->", "rightarrow": "->", "longrightarrow": "->",
    "leftarrow": "<-", "longleftarrow": "<-",
    "leftrightarrow": "<->", "Rightarrow": "=>", "Leftarrow": "<=",
    "Leftrightarrow": "<=>", "mapsto": "->",
    "dots": "cdots", "dotsb": "cdots",
    "square": "box{~~~}", "Box": "box{~~~}",     # 내용 없는 빈 네모
    # 대문자 그리스 문자는 한글에서 이름을 전부 대문자로 쓴다 (Pi 가 아니라 PI)
    "Gamma": "GAMMA", "Delta": "DELTA", "Theta": "THETA", "Lambda": "LAMBDA",
    "Xi": "XI", "Pi": "PI", "Sigma": "SIGMA", "Upsilon": "UPSILON",
    "Phi": "PHI", "Psi": "PSI", "Omega": "OMEGA",
    "langle": "langle", "rangle": "rangle",
    "lvert": "|", "rvert": "|", "vert": "|", "mid": "|",
    "lbrace": "lbrace", "rbrace": "rbrace",
    "%": "%", "$": "$", "#": "#", "&": "&", "_": "_",
    "{": "lbrace", "}": "rbrace",
    ",": "`", ":": "`", ";": "~", " ": "~", "!": "",
    "quad": "~~", "qquad": "~~~~",
    "cr": "#", "\\": "#", "newline": "#",
    "displaystyle": "", "limits": "", "nolimits": "", "textstyle": "",
}

# 위/아래 첨자가 from/to 로 바뀌는 큰 연산자
_BIGOP = {
    "sum": "sum", "prod": "prod", "int": "int", "iint": "dint",
    "iiint": "tint", "oint": "lint", "lim": "lim",
    "bigcup": "cup", "bigcap": "cap", "limsup": "lim", "liminf": "lim",
}

# 씌우는 기호
_ACCENT = {
    "bar": "bar", "overline": "bar", "vec": "vec", "overrightarrow": "vec",
    "hat": "hat", "widehat": "hat", "tilde": "tilde", "widetilde": "tilde",
    "dot": "dot", "ddot": "ddot", "underline": "under",
}

_DELIM = {
    "(": "(", ")": ")", "[": "[", "]": "]", "|": "|",
    "\\{": "lbrace", "\\}": "rbrace", "\\|": "dline",
    "\\langle": "langle", "\\rangle": "rangle",
    "\\lfloor": "lfloor", "\\rfloor": "rfloor",
    "\\lceil": "lceil", "\\rceil": "rceil",
    ".": "",
}


def _read_cmd(s, i):
    """s[i] == '\\' 일 때 명령 이름과 다음 위치."""
    i += 1
    if i >= len(s):
        return "", i
    if s[i].isalpha():
        j = i
        while j < len(s) and s[j].isalpha():
            j += 1
        return s[i:j], j
    return s[i], i + 1


def _read_group(s, i):
    """s[i] == '{' 일 때 중괄호 안 원문과 '}' 다음 위치."""
    depth = 0
    j = i
    while j < len(s):
        if s[j] == "\\":
            j += 2
            continue
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], len(s)


def _take_arg(s, i):
    """다음 인자 하나(그룹이든 글자 하나든)를 원문 그대로."""
    while i < len(s) and s[i] == " ":
        i += 1
    if i >= len(s):
        return "", i
    if s[i] == "{":
        return _read_group(s, i)
    if s[i] == "\\":
        cmd, j = _read_cmd(s, i)
        return "\\" + cmd, j
    return s[i], i + 1


def _take_optional(s, i):
    """[...] 선택 인자."""
    while i < len(s) and s[i] == " ":
        i += 1
    if i < len(s) and s[i] == "[":
        j = s.find("]", i)
        if j != -1:
            return s[i + 1:j], j + 1
    return None, i


def _env_body(s, i, env):
    """\\begin{env} 다음부터 \\end{env} 앞까지."""
    end = "\\end{%s}" % env
    j = s.find(end, i)
    if j == -1:
        return s[i:], len(s)
    return s[i:j], j + len(end)


def _rows(body):
    """행렬/케이스 본문을 [[셀, 셀], ...] 로."""
    rows = []
    for row in body.split("\\\\"):
        row = row.strip()
        if not row:
            continue
        rows.append([c.strip() for c in row.split("&")])
    return rows


def _matrix(body, opener="", closer=""):
    rows = _rows(body)
    inner = " # ".join(" & ".join(convert(c) for c in r) for r in rows)
    core = "matrix{%s}" % inner
    if opener:
        return "left %s %s right %s" % (opener, core, closer)
    return core


def _handle(cmd, s, i):
    # 분수
    if cmd in ("frac", "dfrac", "tfrac", "cfrac"):
        a, i = _take_arg(s, i)
        b, i = _take_arg(s, i)
        return "{%s} over {%s}" % (convert(a), convert(b)), i
    if cmd == "binom":
        a, i = _take_arg(s, i)
        b, i = _take_arg(s, i)
        return "left ( {%s} atop {%s} right )" % (convert(a), convert(b)), i
    if cmd == "over":
        return " over ", i

    # 근호
    if cmd == "sqrt":
        n, i = _take_optional(s, i)
        a, i = _take_arg(s, i)
        if n:
            return "root {%s} of {%s}" % (convert(n), convert(a)), i
        return "sqrt {%s}" % convert(a), i

    # 빈칸 문제의 네모 칸  \boxed{(가)} -> box{(가)}
    if cmd in ("boxed", "box", "fbox", "framebox", "boxtext"):
        a, i = _take_arg(s, i)
        body = convert(a).strip()
        return "box{%s}" % (body or "~~~"), i

    # 로만체 / 굵은체
    if cmd in ("text", "textrm", "mathrm", "mbox", "operatorname", "textbf", "mathbf"):
        a, i = _take_arg(s, i)
        body = convert(a).strip()
        if cmd in ("textbf", "mathbf"):
            return "bold{%s}" % body, i
        return "rm{%s}" % body, i

    # 씌우는 기호
    if cmd in _ACCENT:
        a, i = _take_arg(s, i)
        return "%s {%s}" % (_ACCENT[cmd], convert(a)), i

    # 큰 연산자 + from/to
    if cmd in _BIGOP:
        out = _BIGOP[cmd]
        sub = sup = None
        while i < len(s):
            while i < len(s) and s[i] == " ":
                i += 1
            if i < len(s) and s[i] in "_^":
                ch = s[i]
                arg, i = _take_arg(s, i + 1)
                if ch == "_":
                    sub = arg
                else:
                    sup = arg
            else:
                break
        if sub is not None:
            out += " from {%s}" % convert(sub)
        if sup is not None:
            out += " to {%s}" % convert(sup)
        return out + " ", i

    # 괄호
    if cmd in ("left", "right"):
        while i < len(s) and s[i] == " ":
            i += 1
        if i < len(s) and s[i] == "\\":
            c2, j = _read_cmd(s, i)
            key = "\\" + c2
            i = j
        else:
            key = s[i] if i < len(s) else "."
            i += 1
        d = _DELIM.get(key, key)
        if not d:
            return "", i
        return " %s %s " % (cmd, d), i

    # 환경
    if cmd == "begin":
        env, i = _take_arg(s, i)
        env = env.strip()
        if env == "array":
            _, i = _take_arg(s, i)          # 열 정렬 지정은 버림
        body, i = _env_body(s, i, env)
        if env == "cases":
            rows = _rows(body)
            inner = " # ".join(" & ".join(convert(c) for c in r) for r in rows)
            return "cases{%s}" % inner, i
        if env in ("matrix", "array", "smallmatrix"):
            return _matrix(body), i
        if env == "pmatrix":
            return _matrix(body, "(", ")"), i
        if env == "bmatrix":
            return _matrix(body, "[", "]"), i
        if env == "vmatrix":
            return _matrix(body, "|", "|"), i
        if env == "Bmatrix":
            return _matrix(body, "lbrace", "rbrace"), i
        if env in ("aligned", "align", "align*", "gathered", "gather", "split"):
            rows = _rows(body)
            inner = " # ".join(" ".join(convert(c) for c in r) for r in rows)
            return "pile{%s}" % inner, i
        return convert(body), i
    if cmd == "end":
        _, i = _take_arg(s, i)
        return "", i

    if cmd in _SYMBOL:
        v = _SYMBOL[cmd]
        if not v:
            return "", i
        # 이름형 기호(lbrace 등)는 앞뒤를 띄어야 한글이 토큰으로 알아본다
        if v[0].isalpha():
            v = " %s " % v
        return v, i
    if cmd in _PLAIN:
        return cmd + " ", i

    # 모르는 명령은 이름만 남긴다 (한글이 알 수도 있으므로)
    return cmd + " ", i


def _needs_base(out):
    """첨자 앞에 붙일 글자가 없는지. 없으면 빈 밑틀 {} 을 넣어야 한다."""
    text = "".join(out).rstrip()
    if not text:
        return True
    return text[-1] in "+-=<>(,[{&#~`"


def convert(latex):
    """LaTeX 조각 -> 한글 수식 스크립트."""
    if not latex:
        return ""
    s = latex.strip()
    while s.startswith("$"):
        s = s[1:]
    while s.endswith("$"):
        s = s[:-1]
    for junk in ("\\[", "\\]", "\\(", "\\)"):
        s = s.replace(junk, "")

    out = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            cmd, i = _read_cmd(s, i)
            frag, i = _handle(cmd, s, i)
            out.append(frag)
        elif c == "{":
            body, i = _read_group(s, i)
            out.append("{%s}" % convert(body))
        elif c in "_^":
            # 한글 수식은 _ 뒤를 공백 전까지 통째로 첨자로 먹는다.
            # (a_5=60 -> 아래첨자가 "5=60") 그래서 항상 중괄호로 묶는다.
            # 또 밑틀 없이 _ 로 시작하면 식 전체를 거부해 버린다(_3 C _2 -> 아무것도 안 나옴).
            # 그래서 앞에 붙일 글자가 없으면 빈 밑틀 {} 를 넣어 준다.
            if _needs_base(out):
                out.append("{}")
            j = i + 1
            while j < len(s) and s[j] == " ":
                j += 1
            if j >= len(s):
                i = j
            elif s[j] == "{":
                body, j = _read_group(s, j)
                out.append("%s{%s}" % (c, convert(body)))
                i = j
            elif s[j] == "\\":
                cmd, j2 = _read_cmd(s, j)
                frag, j = _handle(cmd, s, j2)
                out.append("%s{%s}" % (c, frag.strip()))
                i = j
            else:
                out.append("%s{%s}" % (c, s[j]))
                i = j + 1
        elif c == "$":
            i += 1
        else:
            out.append(c)
            i += 1
    res = "".join(out)
    while "  " in res:
        res = res.replace("  ", " ")
    # 첨자가 앞 글자에서 떨어지지 않게
    res = res.replace(" ^", "^").replace(" _", "_")
    return res.strip()


if __name__ == "__main__":
    tests = [
        r"a_3+a_5=60, \quad \frac{a_4}{a_2}+\frac{a_8}{a_6}=6",
        r"\sum_{k=1}^{n} k^2 = \frac{n(n+1)(2n+1)}{6}",
        r"\lim_{x \to 0} \frac{\sin x}{x} = 1",
        r"\sqrt[3]{x^2+1} \geq \frac{1}{2}",
        r"f(x)=\begin{cases} x^2 & (x \geq 0) \\ -x & (x<0) \end{cases}",
        r"\int_{0}^{1} x\,dx = \frac{1}{2}",
        r"\{a_n\} \text{은 등비수열}",
        r"\left( \frac{9}{2} \right)^{2}",
        r"\overline{AB} \perp \overline{CD}",
        r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}",
    ]
    for t in tests:
        print(t)
        print("   ->", convert(t))
        print()
