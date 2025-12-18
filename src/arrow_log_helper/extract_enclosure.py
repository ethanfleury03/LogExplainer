from __future__ import absolute_import

import os
import re


TAB_WIDTH = 4


def _indent_width(line):
    if line is None:
        return 0
    w = 0
    for ch in line:
        if ch == " ":
            w += 1
        elif ch == "\t":
            w += TAB_WIDTH
        else:
            break
    return w


def _is_def(line):
    if line is None:
        return False
    return line.lstrip().startswith("def ")


def _is_class(line):
    if line is None:
        return False
    return line.lstrip().startswith("class ")


def _is_decorator(line):
    if line is None:
        return False
    return line.lstrip().startswith("@")


def _decode_lossy(b):
    try:
        return b.decode("utf-8")
    except Exception:
        try:
            return b.decode("utf-8", "replace")
        except Exception:
            try:
                return b.decode("latin-1", "replace")
            except Exception:
                try:
                    return str(b)
                except Exception:
                    return repr(b)


def _safe_read_lines(path):
    """
    Read file as bytes and return list of decoded unicode lines without trailing newline chars.
    """
    try:
        f = open(path, "rb")
    except Exception:
        return []

    lines = []
    try:
        for raw in f:
            try:
                u = _decode_lossy(raw)
            except Exception:
                continue
            # Preserve content but normalize away newline terminators.
            u = u.rstrip("\r\n")
            lines.append(u)
    finally:
        try:
            f.close()
        except Exception:
            pass
    return lines


_RE_DEF_NAME = re.compile(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)")
_RE_CLASS_NAME = re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)")


def _parse_def_name(line):
    m = _RE_DEF_NAME.match(line or "")
    return m.group(1) if m else None


def _parse_class_name(line):
    m = _RE_CLASS_NAME.match(line or "")
    return m.group(1) if m else None


def extract_enclosure(path, match_line_no, context_fallback=50):
    """
    Extract enclosing def/class for a match location.
    Returns JSON-serializable dict.
    """
    out = {
        "path": path,
        "enclosure_type": "none",
        "name": None,
        "start_line": 1,
        "end_line": 1,
        "block": "",
    }

    if not path:
        out["notes"] = "No path provided."
        return out
    if not os.path.exists(path):
        out["notes"] = "Path does not exist."
        return out

    lines = _safe_read_lines(path)
    n = len(lines)
    if n == 0:
        out["notes"] = "Empty or unreadable file."
        return out

    try:
        i = int(match_line_no) - 1
    except Exception:
        i = 0
    if i < 0:
        i = 0
    if i >= n:
        i = n - 1

    match_indent = _indent_width(lines[i])

    def find_enclosing(is_header_fn):
        # Walk upward from i to find nearest prior header line.
        for j in range(i, -1, -1):
            line = lines[j]
            if not is_header_fn(line):
                continue
            # Good-enough indentation rule: prefer headers with indent < match line indent,
            # otherwise accept the nearest header.
            header_indent = _indent_width(line)
            if header_indent < match_indent or j == i or True:
                return j
        return None

    def compute_block_bounds(header_idx):
        header_line = lines[header_idx]
        base_indent = _indent_width(header_line)

        # Include decorators directly above the header (contiguous).
        start_idx = header_idx
        k = header_idx - 1
        while k >= 0:
            if not _is_decorator(lines[k]):
                break
            if _indent_width(lines[k]) != base_indent:
                break
            start_idx = k
            k -= 1

        end_idx = header_idx
        for k in range(header_idx + 1, n):
            s = lines[k]
            if not s.strip():
                end_idx = k
                continue
            ind = _indent_width(s)
            if ind <= base_indent and (_is_def(s) or _is_class(s) or ind == 0):
                break
            end_idx = k
        return start_idx, end_idx

    # 1) Prefer def
    def_idx = None
    for j in range(i, -1, -1):
        if _is_def(lines[j]):
            def_idx = j
            break
    if def_idx is not None:
        start_idx, end_idx = compute_block_bounds(def_idx)
        out["enclosure_type"] = "def"
        out["name"] = _parse_def_name(lines[def_idx])
        out["start_line"] = start_idx + 1
        out["end_line"] = end_idx + 1
        out["block"] = u"\n".join(lines[start_idx : end_idx + 1])
        return out

    # 2) Else class
    class_idx = None
    for j in range(i, -1, -1):
        if _is_class(lines[j]):
            class_idx = j
            break
    if class_idx is not None:
        start_idx, end_idx = compute_block_bounds(class_idx)
        out["enclosure_type"] = "class"
        out["name"] = _parse_class_name(lines[class_idx])
        out["start_line"] = start_idx + 1
        out["end_line"] = end_idx + 1
        out["block"] = u"\n".join(lines[start_idx : end_idx + 1])
        return out

    # 3) Fallback window
    lo = i - int(context_fallback)
    hi = i + int(context_fallback)
    if lo < 0:
        lo = 0
    if hi >= n:
        hi = n - 1
    out["enclosure_type"] = "none"
    out["name"] = None
    out["start_line"] = lo + 1
    out["end_line"] = hi + 1
    out["block"] = u"\n".join(lines[lo : hi + 1])
    out["notes"] = "No enclosing def/class found; returning context window."
    return out


def extract_signature_only(enclosure_dict):
    """
    Extract only the signature line for def/class enclosures.
    Returns a string or None.
    """
    enclosure_dict = enclosure_dict or {}
    enc_type = enclosure_dict.get("enclosure_type")
    block = enclosure_dict.get("block") or ""
    try:
        lines = block.splitlines()
    except Exception:
        lines = []

    if enc_type == "def":
        for ln in lines:
            if (ln or "").lstrip().startswith("def "):
                return (ln or "").strip()
        return None
    if enc_type == "class":
        for ln in lines:
            if (ln or "").lstrip().startswith("class "):
                return (ln or "").strip()
        return None
    return None

