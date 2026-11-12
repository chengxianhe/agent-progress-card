"""Strict owner-reply syntax; A requests and C card choices never share a namespace."""
import re
import unicodedata


def _selection(text):
    if not isinstance(text, str) or len(text) > 1000:
        return ""
    text = unicodedata.normalize("NFKC", text).strip()
    return re.sub(r"^(?:选项号|选项|回复|选择)\s*", "", text, count=1)


def numbered_selection(text, prefix="A", bare=True):
    text = _selection(text)
    code = prefix + r"[0-9a-f]{10}"
    for pattern in (rf"([1-8])\s+({code})", rf"({code})\s+(?:回复\s*|选择\s*)?([1-8])"):
        match = re.fullmatch(pattern, text, re.I)
        if match:
            number, identity = (match[1], match[2]) if match[1].isdigit() else (match[2], match[1])
            return int(number), identity.upper()
    if bare and re.fullmatch(r"[1-8]", text):
        return int(text), None
    return None


def literal_selection(text, prefix="A"):
    text = _selection(text)
    code = prefix + r"[0-9a-f]{10}"
    match = re.fullmatch(rf"({code})\s+(?:回复\s*|选择\s*)?(.+)", text, re.I)
    if match:
        return match[2].strip(), match[1].upper()
    match = re.fullmatch(rf"(.+?)\s+({code})", text, re.I)
    return (match[1].strip(), match[2].upper()) if match else None


def card_code(choice):
    return "C" + choice["id"][:10].upper()


def approval_syntax(text, prefix="A"):
    # Malformed explicit selectors are explained locally, never sent as a new Agent task.
    text = unicodedata.normalize("NFKC", text).strip()
    return bool(re.match(rf"^(?:(?:选项号|选项|回复|选择)\s*)?(?:\d+\s+)?{prefix}[0-9a-f]{{10}}\b", text, re.I))
