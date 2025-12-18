from __future__ import absolute_import

import re


_RE_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\S+")
_RE_LEVEL = re.compile(r"<([^>])>")
_RE_THREAD = re.compile(r"\[([^\]]+)\]")


def _to_text(s):
    if s is None:
        return ""
    # Python 2: tolerate unicode/bytes. Python 3: this is already str.
    try:
        if isinstance(s, unicode):  # noqa: F821 (py2 only)
            return s
    except Exception:
        pass
    try:
        return str(s)
    except Exception:
        return repr(s)


def select_relevant_line(text):
    """
    Pick the line we want to analyze from a pasted block.
    - Prefer the first line containing "<E>"
    - Otherwise use the first non-empty line
    """
    text = _to_text(text)
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if line:
            lines.append(line)
    if not lines:
        return ""
    for line in lines:
        if "<E>" in line:
            return line
    return lines[0]


def parse_line(line):
    """
    Best-effort parse a single printer-style log line.

    Typical pattern:
      2025-12-19T05:22:06.751222+11:00 RS20300529 Kareela0: <I> [#4] EngineConductor: Changing state ...
    """
    line = _to_text(line).strip()

    parsed = {
        "timestamp": None,
        "host_or_serial": None,
        "process": None,
        "level": None,
        "thread": None,
        "component": None,
        "message": "",
    }

    if not line:
        return parsed

    tokens = line.split()
    pos = 0

    # Timestamp: leading ISO-like token (starts with year and contains 'T')
    if pos < len(tokens) and _RE_TS.match(tokens[pos]) and ("T" in tokens[pos]):
        parsed["timestamp"] = tokens[pos]
        pos += 1

    # Host/serial + process detection
    # Primary: if we have a timestamp, next token is host/serial.
    if parsed["timestamp"] is not None and pos < len(tokens):
        parsed["host_or_serial"] = tokens[pos]
        pos += 1
        if pos < len(tokens) and tokens[pos].endswith(":"):
            parsed["process"] = tokens[pos][:-1]
            pos += 1
    else:
        # Fallback: detect "HOST PROCESS:" at the start even without timestamp.
        if (pos + 1) < len(tokens) and tokens[pos + 1].endswith(":"):
            parsed["host_or_serial"] = tokens[pos]
            parsed["process"] = tokens[pos + 1][:-1]
            pos += 2

    remainder = " ".join(tokens[pos:]).strip()

    # Level marker: <X>
    m = _RE_LEVEL.search(remainder)
    if m:
        parsed["level"] = m.group(1)
        remainder = (remainder[: m.start()] + " " + remainder[m.end() :]).strip()

    # Thread marker: [...]
    m = _RE_THREAD.search(remainder)
    if m:
        parsed["thread"] = m.group(1).strip() or None
        remainder = (remainder[: m.start()] + " " + remainder[m.end() :]).strip()

    remainder = re.sub(r"\s+", " ", remainder).strip()

    # Component + message: "Component: message"
    if ":" in remainder:
        left, right = remainder.split(":", 1)
        component = left.strip()
        msg = right.strip()
        parsed["component"] = component or None
        parsed["message"] = msg or remainder.strip()
    else:
        parsed["message"] = remainder.strip() or line

    return parsed


def build_keys(parsed, normalize_numbers=False):
    """
    Produce:
    - key_exact
    - key_normalized
    - tokens
    """
    parsed = parsed or {}
    component = parsed.get("component")
    message = parsed.get("message") or ""

    if component and message:
        key_exact = "%s: %s" % (_to_text(component), _to_text(message))
    else:
        key_exact = _to_text(message) or ""

    # Start from key_exact and apply cheap normalization that helps matching.
    key_norm = _to_text(key_exact)

    # Strip common markers if they leaked in (safe even if absent).
    key_norm = re.sub(r"^\d{4}-\d{2}-\d{2}T\S+\s+", "", key_norm)
    key_norm = re.sub(r"<[^>]{1}>", " ", key_norm)
    key_norm = re.sub(r"\[[^\]]+\]", " ", key_norm)

    # If someone pasted a full prefix, try to remove "HOST PROCESS:" prefix.
    key_norm = re.sub(r"^[A-Za-z0-9_.-]{4,}\s+[A-Za-z0-9_.-]+:\s+", "", key_norm)

    if normalize_numbers:
        # Replace floats and long-ish integers.
        key_norm = re.sub(r"\b\d+\.\d+\b", "<NUM>", key_norm)
        key_norm = re.sub(r"\b\d{4,}\b", "<NUM>", key_norm)

    key_norm = re.sub(r"\s+", " ", key_norm).strip().lower()
    if not key_norm:
        key_norm = _to_text(key_exact).strip().lower()

    # Tokenize for future fallback matching.
    raw_tokens = re.split(r"[^a-z0-9]+", key_norm)
    tokens = []
    for t in raw_tokens:
        if not t:
            continue
        if len(t) < 3:
            continue
        tokens.append(t)

    return {
        "key_exact": key_exact,
        "key_normalized": key_norm,
        "tokens": tokens,
    }


def analyze_pasted_text(text, normalize_numbers=False):
    """
    End-to-end helper for UI/backends.
    Returns a JSON-serializable dict: only strings, lists, None, bool.
    """
    selected_line = select_relevant_line(text)
    parsed = parse_line(selected_line)
    keys = build_keys(parsed, normalize_numbers=normalize_numbers)

    out = {"selected_line": selected_line}
    out.update(parsed)
    out.update(keys)
    return out


