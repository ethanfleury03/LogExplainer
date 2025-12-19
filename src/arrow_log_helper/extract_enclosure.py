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
    stripped = line.lstrip()
    return stripped.startswith("def ") or stripped.startswith("async def ")


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


_RE_DEF_NAME = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)")
_RE_CLASS_NAME = re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)")
_RE_ASYNC_DEF = re.compile(r"^\s*async\s+def\s+")


def _parse_def_name(line):
    m = _RE_DEF_NAME.match(line or "")
    return m.group(1) if m else None


def _is_async_def(line):
    """Check if line is an async def statement."""
    if line is None:
        return False
    return bool(_RE_ASYNC_DEF.match(line))


def _parse_class_name(line):
    m = _RE_CLASS_NAME.match(line or "")
    return m.group(1) if m else None


def extract_enclosure(path, match_line_no, context_fallback=50):
    """
    Extract enclosing def/class for a match location with guaranteed containment.
    Returns JSON-serializable dict.
    
    Ensures: start_line <= match_line_no <= end_line for non-window results.
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

    # Convert to 0-based index, ensure valid
    try:
        match_line_1based = int(match_line_no)
        i = match_line_1based - 1
    except Exception:
        i = 0
    if i < 0:
        i = 0
    if i >= n:
        i = n - 1

    def is_header_line(line):
        """Check if line is a def, async def, or class header."""
        if line is None:
            return False
        stripped = line.lstrip()
        return stripped.startswith("def ") or stripped.startswith("async def ") or stripped.startswith("class ")

    def compute_block_bounds(header_idx):
        """Compute start and end indices for a block starting at header_idx.
        Returns (start_idx, end_idx) where start_idx may include decorators.
        """
        header_line = lines[header_idx]
        base_indent = _indent_width(header_line)

        # Include decorators directly above the header (contiguous, same or greater indent).
        start_idx = header_idx
        k = header_idx - 1
        while k >= 0:
            line_k = lines[k]
            if not _is_decorator(line_k):
                break
            # Decorator must have same indent as header, or greater (but not less)
            decorator_indent = _indent_width(line_k)
            if decorator_indent < base_indent:
                break
            start_idx = k
            k -= 1

        # Find end of block by scanning forward
        end_idx = header_idx
        for k in range(header_idx + 1, n):
            s = lines[k]
            # Blank lines are part of the block
            if not s.strip():
                end_idx = k
                continue
            # Pure comment lines are part of the block
            stripped = s.lstrip()
            if stripped.startswith("#"):
                end_idx = k
                continue
            # Check indentation
            ind = _indent_width(s)
            # Block ends when we hit a line with indentation <= base_indent
            # that is either a new def/class or at module level (ind == 0)
            if ind <= base_indent:
                if is_header_line(s) or ind == 0:
                    break
            end_idx = k
        return start_idx, end_idx

    def validate_containment(start_idx, end_idx, match_idx):
        """Validate that match_idx is contained within [start_idx, end_idx]."""
        return start_idx <= match_idx <= end_idx

    # Scan upward from match line to find all candidate headers
    # Try each candidate and validate containment
    candidates = []
    for j in range(i, -1, -1):
        if is_header_line(lines[j]):
            candidates.append(j)

    # Process candidates: prefer def/async_def, then class
    # Must validate containment for each
    for header_idx in candidates:
        header_line = lines[header_idx]
        is_async = _is_async_def(header_line)
        is_def = _is_def(header_line) and not is_async
        is_class = _is_class(header_line)

        if is_def or is_async:
            start_idx, end_idx = compute_block_bounds(header_idx)
            # Validate containment
            if validate_containment(start_idx, end_idx, i):
                out["enclosure_type"] = "async_def" if is_async else "def"
                out["name"] = _parse_def_name(header_line)
                out["start_line"] = start_idx + 1
                out["end_line"] = end_idx + 1
                out["block"] = u"\n".join(lines[start_idx : end_idx + 1])
                return out
            # If not contained, continue searching upward

        elif is_class:
            start_idx, end_idx = compute_block_bounds(header_idx)
            # Validate containment
            if validate_containment(start_idx, end_idx, i):
                out["enclosure_type"] = "class"
                out["name"] = _parse_class_name(header_line)
                out["start_line"] = start_idx + 1
                out["end_line"] = end_idx + 1
                out["block"] = u"\n".join(lines[start_idx : end_idx + 1])
                return out
            # If not contained, continue searching upward

    # No valid enclosure found - return fallback window
    lo = i - int(context_fallback)
    hi = i + int(context_fallback)
    if lo < 0:
        lo = 0
    if hi >= n:
        hi = n - 1
    out["enclosure_type"] = "window"
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

    if enc_type in ("def", "async_def"):
        for ln in lines:
            if ln is None:
                continue
            stripped = ln.lstrip()
            if stripped.startswith("def ") or stripped.startswith("async def "):
                return ln.strip()
        return None
    if enc_type == "class":
        for ln in lines:
            if ln is None:
                continue
            if (ln or "").lstrip().startswith("class "):
                return (ln or "").strip()
        return None
    return None

