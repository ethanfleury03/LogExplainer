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


# Regex patterns matching the exact requirements:
# ^\s*(async\s+def|def|class)\s+NAME\s*\(
# or ^\s*class\s+NAME\s*(\(|:)\s*
_RE_DEF_HEADER = re.compile(r"^\s*(async\s+def|def)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_RE_CLASS_HEADER = re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\s*(\(|:)\s*")
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


def _extract_docstring(lines, start_idx, end_idx, header_idx):
    """
    Extract Python docstring from function/class body.
    Returns (docstring_text, docstring_start_line, docstring_end_line) or (None, None, None).
    """
    # Docstring is the first statement in the body (after the def/class line)
    # Look for triple-quoted string immediately after header
    max_docstring_size = 16 * 1024  # Cap at 16KB
    
    # Start searching after the header line
    header_indent = _indent_width(lines[header_idx]) if header_idx < len(lines) else 0
    
    for k in range(header_idx + 1, min(end_idx + 1, len(lines))):
        line = lines[k] if k < len(lines) else ""
        if not line:
            continue
        
        stripped = line.lstrip()
        # Skip blank lines and comments
        if not stripped or stripped.startswith("#"):
            continue
        
        # Check indentation - docstring should be indented more than header (inside function)
        line_indent = _indent_width(line)
        if line_indent <= header_indent:
            # Not indented enough to be a docstring, might be module-level or next function
            break
        
        # Check for triple-quote docstring
        if stripped.startswith('"""') or stripped.startswith("'''"):
            quote_char = stripped[0:3]
            # One-line docstring: """text"""
            if stripped.endswith(quote_char) and len(stripped) > 6:
                docstring = stripped[3:-3]
                if len(docstring) <= max_docstring_size:
                    return (docstring, k + 1, k + 1)
            
            # Multi-line docstring
            docstring_lines = [stripped[3:]]  # First line without opening quote
            docstring_start = k + 1
            found_closing = False
            
            for j in range(k + 1, min(end_idx + 1, len(lines))):
                next_line = lines[j] if j < len(lines) else ""
                
                # Check if this line contains the closing quote
                if quote_char in next_line:
                    # Find the closing quote
                    idx = next_line.find(quote_char)
                    if idx >= 0:
                        # Extract text before closing quote
                        if idx > 0:
                            docstring_lines.append(next_line[:idx])
                        found_closing = True
                        docstring_end = j + 1
                        break
                else:
                    # No closing quote yet, add entire line
                    docstring_lines.append(next_line)
                
                # Safety: cap size
                total_size = sum(len(l) for l in docstring_lines)
                if total_size > max_docstring_size:
                    break
            
            if found_closing:
                docstring_text = "\n".join(docstring_lines).strip()
                if docstring_text:
                    return (docstring_text, docstring_start, docstring_end)
        
        # If we hit non-docstring code, no docstring exists
        break
    
    return (None, None, None)


def _extract_leading_comment_block(lines, def_line_no, max_window=25):
    """
    Extract leading comment block directly above def/class line.
    Skips decorators to find comments above them.
    Returns (comment_block, start_line, end_line) or (None, None, None).
    """
    # def_line_no is 1-based, convert to 0-based index
    def_idx = def_line_no - 1
    if def_idx <= 0:
        return (None, None, None)
    
    comment_lines = []
    start_idx = None
    end_idx = None
    blank_gap = 0
    max_blank_gap = 1  # Allow at most 1 blank line gap
    
    # Walk upward from def line, skipping decorators
    for k in range(def_idx - 1, max(-1, def_idx - max_window - 1), -1):
        if k < 0:
            break
        
        line = lines[k] if k < len(lines) else ""
        stripped = line.lstrip()
        
        if not stripped:
            # Blank line - allow small gap
            blank_gap += 1
            if blank_gap > max_blank_gap:
                break
            continue
        
        # Skip decorators (they're between comments and def, but we want comments above decorators)
        if _is_decorator(line):
            blank_gap = 0  # Reset gap when we hit decorator
            continue
        
        blank_gap = 0  # Reset gap counter
        
        # Check for comment or triple-quote block
        if stripped.startswith("#"):
            comment_lines.insert(0, line)
            if end_idx is None:
                end_idx = k
            start_idx = k
        elif stripped.startswith('"""') or stripped.startswith("'''"):
            # Triple-quote block above def (treat as header block)
            quote_char = stripped[0:3]
            block_lines = [line]
            
            # Check if it's a one-liner
            if stripped.endswith(quote_char) and len(stripped) > 6:
                comment_lines.insert(0, line)
                if end_idx is None:
                    end_idx = k
                start_idx = k
            else:
                # Multi-line, collect upward to find opening quote
                found_opening = False
                for j in range(k - 1, max(-1, k - max_window), -1):
                    if j < 0:
                        break
                    prev_line = lines[j] if j < len(lines) else ""
                    # Skip decorators when collecting multi-line quote block
                    if _is_decorator(prev_line):
                        continue
                    block_lines.insert(0, prev_line)
                    # Check if this line has the opening quote
                    if quote_char in prev_line:
                        found_opening = True
                        break
                
                if found_opening or len(block_lines) > 0:
                    comment_lines = block_lines + comment_lines
                    if end_idx is None:
                        end_idx = k
                    start_idx = j if (j >= 0 and found_opening) else k
        else:
            # Non-comment, non-blank, non-decorator line - stop
            break
    
    if comment_lines:
        comment_block = "\n".join(comment_lines)
        return (comment_block, start_idx + 1 if start_idx is not None else None, 
                end_idx + 1 if end_idx is not None else None)
    
    return (None, None, None)


def extract_context_preview(path, match_line_no, context_lines=10):
    """
    Extract a small code snippet around the matched line with line numbers.
    
    Args:
        path: File path to read
        match_line_no: 1-based line number of the match
        context_lines: Number of lines before/after to include (default 10)
    
    Returns:
        str: Formatted preview with line numbers, e.g. "927: ...\n928: ...\n...\n937: logger.error(...)\n...\n947: ..."
        Returns None if file cannot be read.
    """
    if not path or not os.path.exists(path):
        return None
    
    lines = _safe_read_lines(path)
    n = len(lines)
    if n == 0:
        return None
    
    # Convert to 0-based index, ensure valid
    try:
        match_line_1based = int(match_line_no)
        match_idx = match_line_1based - 1
    except Exception:
        match_idx = 0
    
    if match_idx < 0:
        match_idx = 0
    if match_idx >= n:
        match_idx = n - 1
    
    # Calculate bounds (clamp to file boundaries)
    start_idx = max(0, match_idx - context_lines)
    end_idx = min(n - 1, match_idx + context_lines)
    
    # Build preview with line numbers
    preview_lines = []
    for i in range(start_idx, end_idx + 1):
        line_num = i + 1  # 1-based line number
        line_text = lines[i] if i < len(lines) else ""
        preview_lines.append("%d: %s" % (line_num, line_text))
    
    return "\n".join(preview_lines)


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
        "decorator_lines": [],
        "def_line_text": None,
        "decorator_start_line": None,
        "def_line_no": None,
        "enclosure_contains_match": False,
        "docstring_text": None,
        "docstring_start_line": None,
        "docstring_end_line": None,
        "leading_comment_block": None,
        "leading_comment_start_line": None,
        "leading_comment_end_line": None,
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
        """Check if line is a def, async def, or class header using regex."""
        if line is None:
            return False
        # Use regex to match exact pattern: ^\s*(async\s+def|def|class)\s+NAME\s*\(
        # or ^\s*class\s+NAME\s*(\(|:)\s*
        return bool(_RE_DEF_HEADER.match(line) or _RE_CLASS_HEADER.match(line))

    def compute_block_bounds(header_idx):
        """Compute start and end indices for a block starting at header_idx.
        Returns (start_idx, end_idx, decorator_start_idx, decorator_lines) 
        where start_idx may include decorators.
        """
        header_line = lines[header_idx]
        base_indent = _indent_width(header_line)

        # Collect decorators directly above the header (contiguous, same or greater indent).
        decorator_lines = []
        decorator_start_idx = None
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
            decorator_lines.insert(0, line_k.rstrip())
            # Track the first decorator (lowest line number, furthest from def)
            decorator_start_idx = k
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
            # Skip continuation lines (lines that are part of multi-line statements)
            if ind <= base_indent:
                # Don't break on continuation lines (lines ending with backslash)
                is_continuation = False
                if k > 0:
                    prev_line = lines[k - 1].rstrip()
                    if prev_line.endswith("\\"):
                        is_continuation = True
                
                if not is_continuation:
                    # Break on new header or module-level statement (not comments)
                    if is_header_line(s) or (ind == 0 and not stripped.startswith("#")):
                        break
            end_idx = k
        return start_idx, end_idx, decorator_start_idx, decorator_lines

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
            start_idx, end_idx, decorator_start_idx, decorator_lines = compute_block_bounds(header_idx)
            # Validate containment
            contains_match = validate_containment(start_idx, end_idx, i)
            if contains_match:
                out["enclosure_type"] = "async_def" if is_async else "def"
                out["name"] = _parse_def_name(header_line)
                out["start_line"] = start_idx + 1
                out["end_line"] = end_idx + 1
                out["block"] = u"\n".join(lines[start_idx : end_idx + 1])
                
                # Separate decorators from def line
                out["decorator_lines"] = decorator_lines
                out["def_line_text"] = header_line.strip()
                out["def_line_no"] = header_idx + 1
                out["decorator_start_line"] = (decorator_start_idx + 1) if decorator_start_idx is not None else None
                out["enclosure_contains_match"] = True
                
                # Extract docstring
                docstring_text, docstring_start, docstring_end = _extract_docstring(lines, start_idx, end_idx, header_idx)
                out["docstring_text"] = docstring_text
                out["docstring_start_line"] = docstring_start
                out["docstring_end_line"] = docstring_end
                
                # Extract leading comment block
                comment_block, comment_start, comment_end = _extract_leading_comment_block(lines, header_idx + 1)
                out["leading_comment_block"] = comment_block
                out["leading_comment_start_line"] = comment_start
                out["leading_comment_end_line"] = comment_end
                
                return out
            # If not contained, continue searching upward

        elif is_class:
            start_idx, end_idx, decorator_start_idx, decorator_lines = compute_block_bounds(header_idx)
            # Validate containment
            contains_match = validate_containment(start_idx, end_idx, i)
            if contains_match:
                out["enclosure_type"] = "class"
                out["name"] = _parse_class_name(header_line)
                out["start_line"] = start_idx + 1
                out["end_line"] = end_idx + 1
                out["block"] = u"\n".join(lines[start_idx : end_idx + 1])
                
                # Separate decorators from class line
                out["decorator_lines"] = decorator_lines
                out["def_line_text"] = header_line.strip()
                out["def_line_no"] = header_idx + 1
                out["decorator_start_line"] = (decorator_start_idx + 1) if decorator_start_idx is not None else None
                out["enclosure_contains_match"] = True
                
                # Extract docstring
                docstring_text, docstring_start, docstring_end = _extract_docstring(lines, start_idx, end_idx, header_idx)
                out["docstring_text"] = docstring_text
                out["docstring_start_line"] = docstring_start
                out["docstring_end_line"] = docstring_end
                
                # Extract leading comment block
                comment_block, comment_start, comment_end = _extract_leading_comment_block(lines, header_idx + 1)
                out["leading_comment_block"] = comment_block
                out["leading_comment_start_line"] = comment_start
                out["leading_comment_end_line"] = comment_end
                
                return out
            # If not contained, continue searching upward

    # No valid enclosure found - return module-level fallback
    lo = i - int(context_fallback)
    hi = i + int(context_fallback)
    if lo < 0:
        lo = 0
    if hi >= n:
        hi = n - 1
    out["enclosure_type"] = "module"
    out["name"] = None
    out["start_line"] = None
    out["end_line"] = None
    out["block"] = u"\n".join(lines[lo : hi + 1])
    out["enclosure_contains_match"] = False  # Module-level has no containment
    out["notes"] = "No enclosing def/class found; returning module-level context window."
    return out


def extract_signature_only(enclosure_dict):
    """
    Extract signature line for def/class enclosures (def/class line only, no decorators).
    Returns a string or None.
    """
    enclosure_dict = enclosure_dict or {}
    # Use def_line_text if available (already separated from decorators)
    def_line_text = enclosure_dict.get("def_line_text")
    if def_line_text:
        return def_line_text
    
    # Fallback: extract from block
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

