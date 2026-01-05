#!/usr/bin/env python2
"""
Codebase ingestion for printer log analysis.

Indexes functions and extracts error messages for fast lookup.
Python 2.7.5 compatible, stdlib only, read-only operation.

Uses tokenize-based boundary detection for accurate function extraction,
with fallback to heuristic-based detection if tokenize fails.

Chunk Schema:
    Backward-compatible fields (required for search/validation):
    - file_path: Full file path
    - function_name: Function name
    - class_name: Class name if method, None if module-level
    - line_start: 1-based inclusive start line (includes leading comments/decorators)
    - line_end: 1-based inclusive end line (last line of function body)
    - signature: Normalized single-line signature (for search compatibility)
    - code: Function code (def + body only, backward compatible)
    - docstring: Docstring text (no quotes)
    - leading_comment: Leading comment block text
    - error_messages: List of error message dicts
    - log_levels: List of log level characters
    - chunk_id: SHA256 hash (first 16 chars) of stable subset
    
    New fields for perfect extraction:
    - def_line: 1-based line number of 'def' statement
    - start_line_inclusive: 1-based inclusive start (leading comment, decorator, or def)
    - end_line_inclusive: 1-based inclusive end (last line of function body)
    - signature_original: Original signature with formatting preserved (multi-line)
    - decorators: List of decorator lines as strings
    - decorator_block: Full decorator block as string
    - code_full: Complete code including leading comments, decorators, def, and body
    - leading_comment_span: Dict with 'start' and 'end' (1-based, inclusive) or None
    - decorator_span: Dict with 'start' and 'end' (1-based, inclusive) or None
    - signature_span: Dict with 'start' and 'end' (1-based, inclusive)
    - extraction_warnings: List of warning strings (e.g., "tokenize_failed_used_old_end_algo")

Line Number Semantics:
    All line numbers are 1-based and INCLUSIVE.
    - line_start: First line included in extraction envelope
    - line_end: Last line included in function body
    - Use _slice_lines() helper for safe slicing with inclusive bounds

Usage:
    python tools/ingest.py --root /opt/memjet --out /index.json
"""

from __future__ import print_function

import argparse
import ast
import hashlib
import json
import os
import re
import sys
import time
import tokenize

# Python 2.7 compatibility for StringIO
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

# Python version compatibility
PY2 = sys.version_info[0] == 2
if PY2:
    try:
        unicode
    except NameError:
        unicode = str
else:
    unicode = str

# Check if AsyncFunctionDef exists (Python 3.5+)
HAS_ASYNC_FUNCTION = hasattr(ast, 'AsyncFunctionDef')


# Default exclude directories
DEFAULT_EXCLUDE_DIRS = {
    '__pycache__', '.git', '.svn', '.hg',
    'node_modules', 'dist', 'build', 'out', 'target',
    'venv', '.venv', 'env', '.env',
    '.idea', '.vscode',
}

# Default file extensions to process
DEFAULT_INCLUDE_EXTS = ['.py']

# Maximum file size to process (10MB)
DEFAULT_MAX_FILE_BYTES = 10 * 1024 * 1024


def safe_walk_files(roots, include_exts=None, exclude_dir_names=None, max_file_bytes=DEFAULT_MAX_FILE_BYTES):
    """Walk files in roots, respecting include_exts and exclude_dir_names."""
    if include_exts is None:
        include_exts = DEFAULT_INCLUDE_EXTS
    
    include_exts = [e.lower() if e.startswith('.') else '.' + e.lower() for e in include_exts]
    
    if exclude_dir_names is None:
        exclude_dir_names = DEFAULT_EXCLUDE_DIRS
    else:
        exclude_dir_names = set(exclude_dir_names)
    
    roots_list = roots if isinstance(roots, (list, tuple)) else [roots]
    
    for root in roots_list:
        if not os.path.isdir(root):
            continue
        
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            # Filter out excluded directories
            dirnames[:] = [d for d in dirnames if d not in exclude_dir_names]
            
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                
                # Check extension
                _, ext = os.path.splitext(filename)
                if ext.lower() not in include_exts:
                    continue
                
                # Check file size
                try:
                    stat_info = os.stat(filepath)
                    if stat_info.st_size > max_file_bytes:
                        continue
                except (OSError, IOError):
                    continue
                
                yield filepath


def _decode_lossy(b):
    """Decode bytes to unicode, trying multiple encodings."""
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


def _safe_read_file(filepath):
    """Read file as unicode string, handling encoding errors."""
    try:
        with open(filepath, 'rb') as f:
            raw = f.read()
        return _decode_lossy(raw)
    except (IOError, OSError) as e:
        return None


def _normalize_indent_width(line):
    """Calculate indent width, treating tabs as 4 spaces (Python standard)."""
    if not line:
        return 0
    width = 0
    for ch in line:
        if ch == ' ':
            width += 1
        elif ch == '\t':
            width += 4
        else:
            break
    return width


def _build_function_boundary_map(source_lines, source_text):
    """
    Build a map of function boundaries using tokenize.
    
    Returns dict: def_line_no -> {
        'end_line_inclusive': int,
        'decorator_start_line': int|None,
        'decorator_end_line': int|None,
        'header_end_line': int,  # Line with the ':' from def header
    }
    
    Falls back to None if tokenize fails.
    """
    try:
        # Python 2.7: use generate_tokens with StringIO
        if PY2:
            tokens = tokenize.generate_tokens(StringIO(source_text).readline)
        else:
            tokens = tokenize.generate_tokens(StringIO(source_text).readline)
        
        boundary_map = {}
        
        # State tracking
        paren_level = 0
        bracket_level = 0
        brace_level = 0
        at_bol = True  # Beginning of logical line
        current_indent = 0
        indent_stack = []  # Stack of (indent_depth, def_line) for nested functions
        
        # Current function being tracked
        current_def_line = None
        current_def_indent = None
        last_significant_line = None
        header_end_line = None
        
        # Decorator tracking
        decorator_start_line = None
        decorator_end_line = None
        in_decorator = False
        decorator_paren_level = 0
        prev_token_type = None
        prev_token_line = None
        
        for tok_type, tok_string, tok_start, tok_end, tok_line in tokens:
            line_no = tok_start[0]
            
            # Track significant lines (non-NL, non-COMMENT tokens)
            if tok_type not in (tokenize.NL, tokenize.COMMENT, tokenize.NEWLINE):
                last_significant_line = line_no
            
            # Track parentheses/brackets/braces for continuation detection
            if tok_type == tokenize.OP:
                if tok_string == '(':
                    paren_level += 1
                elif tok_string == ')':
                    paren_level -= 1
                elif tok_string == '[':
                    bracket_level += 1
                elif tok_string == ']':
                    bracket_level -= 1
                elif tok_string == '{':
                    brace_level += 1
                elif tok_string == '}':
                    brace_level -= 1
            
            # Track indentation
            if tok_type == tokenize.INDENT:
                current_indent += 1
                if current_def_line is not None:
                    indent_stack.append((current_indent, current_def_line, current_def_indent))
            elif tok_type == tokenize.DEDENT:
                current_indent -= 1
                # Check if we're closing a function
                while indent_stack and indent_stack[-1][0] > current_indent:
                    closed_indent, closed_def_line, closed_def_indent = indent_stack.pop()
                    # Finalize this function
                    if closed_def_line in boundary_map:
                        # Update end line if we have a better one
                        if last_significant_line and last_significant_line > boundary_map[closed_def_line]['end_line_inclusive']:
                            boundary_map[closed_def_line]['end_line_inclusive'] = last_significant_line
                    else:
                        # Shouldn't happen, but handle gracefully
                        boundary_map[closed_def_line] = {
                            'end_line_inclusive': last_significant_line or closed_def_line,
                            'decorator_start_line': None,
                            'decorator_end_line': None,
                            'header_end_line': closed_def_line,
                        }
                
                # If we're closing the current function
                if current_def_line is not None and current_indent <= current_def_indent:
                    if current_def_line not in boundary_map:
                        boundary_map[current_def_line] = {
                            'end_line_inclusive': last_significant_line or current_def_line,
                            'decorator_start_line': None,
                            'decorator_end_line': None,
                            'header_end_line': header_end_line or current_def_line,
                        }
                    else:
                        # Update existing entry (decorator info already stored when we saw 'def')
                        boundary_map[current_def_line]['end_line_inclusive'] = last_significant_line or current_def_line
                        if header_end_line:
                            boundary_map[current_def_line]['header_end_line'] = header_end_line
                    current_def_line = None
                    current_def_indent = None
                    in_decorator = False
                    decorator_paren_level = 0
            
            # Detect decorators: '@' at start of logical line (may be indented)
            # Decorators appear at the start of a line (after indentation), not inside expressions
            if (tok_type == tokenize.OP and tok_string == '@' and
                paren_level == 0 and bracket_level == 0 and brace_level == 0):
                # Check if '@' is at the start of its line (after indentation)
                # by examining the source line directly
                is_at_line_start = False
                if line_no <= len(source_lines):
                    line_text = source_lines[line_no - 1]
                    stripped = line_text.lstrip()
                    # '@' should be the first non-whitespace character on the line
                    if stripped.startswith('@'):
                        is_at_line_start = True
                
                # Also check if we're at beginning of logical line (tokenize's at_bol)
                if is_at_line_start or at_bol:
                    if not in_decorator:
                        decorator_start_line = line_no
                        in_decorator = True
                        decorator_paren_level = paren_level
                    decorator_end_line = line_no
            
            # Track decorator continuation (update end line as we process tokens)
            if in_decorator:
                decorator_end_line = line_no
                # Check if we're still in decorator (paren level changed or newline with matching level)
                if tok_type == tokenize.NEWLINE:
                    # On newline, if paren level matches, decorator might be complete
                    # But we keep tracking until we see 'def'
                    pass
            
            # Detect function definition: 'def' or 'async def' at BOL
            # Handle 'async def' by checking if previous token was 'async'
            is_def = (tok_type == tokenize.NAME and tok_string == 'def')
            is_async_def = (tok_type == tokenize.NAME and tok_string == 'async')
            
            if is_def or is_async_def:
                # For async, we need to check if next token is 'def'
                # For now, handle 'def' directly; 'async def' will be caught when we see 'def' after 'async'
                if is_def:
                    # Check if we're at beginning of logical line (not inside parens)
                    if at_bol and paren_level == 0 and bracket_level == 0 and brace_level == 0:
                        # Calculate indent of this def line
                        def_line_no = line_no
                        if def_line_no <= len(source_lines):
                            def_line_text = source_lines[def_line_no - 1]
                            def_indent = _normalize_indent_width(def_line_text)
                            
                            # Finalize previous function if any
                            if current_def_line is not None:
                                if current_def_line not in boundary_map:
                                    boundary_map[current_def_line] = {
                                        'end_line_inclusive': last_significant_line or current_def_line,
                                        'decorator_start_line': decorator_start_line,
                                        'decorator_end_line': decorator_end_line,
                                        'header_end_line': header_end_line or current_def_line,
                                    }
                            
                        # Start tracking new function
                        current_def_line = def_line_no
                        current_def_indent = def_indent
                        header_end_line = None
                        # Store decorator info for this function BEFORE clearing
                        # (decorators immediately precede this 'def')
                        saved_decorator_start = decorator_start_line
                        saved_decorator_end = decorator_end_line
                        # Initialize boundary map entry for this function with decorator info
                        boundary_map[def_line_no] = {
                            'end_line_inclusive': def_line_no,  # Will be updated later
                            'decorator_start_line': saved_decorator_start,
                            'decorator_end_line': saved_decorator_end,
                            'header_end_line': def_line_no,  # Will be updated when we see ':'
                        }
                        # Stop tracking decorators when we see 'def'
                        in_decorator = False
                        decorator_paren_level = 0
                        # Clear decorator tracking for next function
                        decorator_start_line = None
                        decorator_end_line = None
            
            # Track header end (line with ':')
            if tok_type == tokenize.OP and tok_string == ':' and current_def_line is not None:
                if paren_level == 0 and bracket_level == 0 and brace_level == 0:
                    header_end_line = line_no
                    # Update boundary map with header end line
                    if current_def_line in boundary_map:
                        boundary_map[current_def_line]['header_end_line'] = line_no
                    # Decorator block ends when we see the ':' of def
                    if in_decorator:
                        in_decorator = False
            
            # Track beginning of logical line and previous token
            if tok_type == tokenize.NEWLINE:
                at_bol = True
            elif tok_type not in (tokenize.NL, tokenize.COMMENT):
                at_bol = False
            
            # Update previous token tracking
            if tok_type not in (tokenize.NL, tokenize.COMMENT):
                prev_token_type = tok_type
                prev_token_line = line_no
        
        # Finalize any remaining function
        if current_def_line is not None:
            if current_def_line not in boundary_map:
                boundary_map[current_def_line] = {
                    'end_line_inclusive': last_significant_line or current_def_line,
                    'decorator_start_line': decorator_start_line,
                    'decorator_end_line': decorator_end_line,
                    'header_end_line': header_end_line or current_def_line,
                }
        
        return boundary_map
    
    except Exception:
        # Tokenize failed, return None to trigger fallback
        return None


def _slice_lines(lines, start_inclusive, end_inclusive):
    """
    Safely slice lines array with inclusive bounds.
    
    Args:
        lines: List of strings (0-indexed)
        start_inclusive: 1-based start line (inclusive)
        end_inclusive: 1-based end line (inclusive)
    
    Returns:
        String with newlines joining the slice
    """
    if start_inclusive < 1:
        start_inclusive = 1
    if end_inclusive > len(lines):
        end_inclusive = len(lines)
    if start_inclusive > end_inclusive:
        return ""
    # Convert to 0-based for slicing
    start_idx = start_inclusive - 1
    end_idx = end_inclusive  # Exclusive for slicing
    return "\n".join(lines[start_idx:end_idx])


def _extract_decorators_from_lines(lines, decorator_start_line, decorator_end_line, def_line):
    """
    Extract decorator lines between start and end (inclusive, 1-based).
    Excludes the def line itself.
    
    Args:
        lines: List of source lines (0-indexed)
        decorator_start_line: 1-based start line of decorators (or None)
        decorator_end_line: 1-based end line of decorators (or None)
        def_line: 1-based def line number (to exclude from decorators)
    
    Returns:
        (decorator_lines: List[str], decorator_block: str|None)
    """
    if decorator_start_line is None or decorator_end_line is None:
        return [], None
    
    if decorator_start_line < 1:
        return [], None
    
    # Ensure decorator_end_line is before def_line
    if def_line is not None and decorator_end_line >= def_line:
        decorator_end_line = def_line - 1
    
    if decorator_end_line < decorator_start_line:
        return [], None
    
    if decorator_end_line > len(lines):
        decorator_end_line = len(lines)
    
    decorator_lines = []
    for i in range(decorator_start_line - 1, decorator_end_line):
        if i < len(lines):
            decorator_lines.append(lines[i])
    
    if decorator_lines:
        return decorator_lines, "\n".join(decorator_lines)
    return [], None


def _extract_signature_original(lines, def_line_no, header_end_line):
    """
    Extract original signature preserving formatting from def line through header end.
    
    Args:
        lines: List of source lines (0-indexed)
        def_line_no: 1-based def line number
        header_end_line: 1-based line with ':' (inclusive)
    
    Returns:
        String with original formatting preserved
    """
    if def_line_no < 1 or header_end_line < def_line_no:
        return None
    if header_end_line > len(lines):
        header_end_line = len(lines)
    
    signature_lines = []
    for i in range(def_line_no - 1, header_end_line):
        if i < len(lines):
            signature_lines.append(lines[i])
    
    return "\n".join(signature_lines) if signature_lines else None


def _extract_leading_comment_block(lines, start_line_idx, max_window=30, stop_at_decorators=False):
    """
    Extract leading comment/docstring block above function definition.
    Looks for triple-quoted strings (docstrings) or # comments above the def line.
    
    Args:
        lines: List of source lines (0-indexed)
        start_line_idx: 0-based index of def line (or decorator start if not stop_at_decorators)
        max_window: Maximum lines to scan upward
        stop_at_decorators: If True, stop when hitting decorator; if False, continue through decorators
    
    Returns:
        (text, start_line, end_line) where lines are 1-based, or (None, None, None)
    """
    if start_line_idx <= 0:
        return (None, None, None)
    
    comment_lines = []
    start_idx = None
    end_idx = None
    blank_gap = 0
    max_blank_gap = 1  # Allow at most 1 blank line gap
    
    # Walk upward from start line
    for k in range(start_line_idx - 1, max(-1, start_line_idx - max_window - 1), -1):
        if k < 0:
            break
        
        line = lines[k] if k < len(lines) else ""
        stripped = line.lstrip()
        
        if not stripped:
            blank_gap += 1
            if blank_gap > max_blank_gap:
                break
            continue
        
        # Check for decorator (if we should stop)
        if stop_at_decorators and stripped.startswith('@'):
            break
        
        blank_gap = 0
        
        # Check for triple-quote docstring/comment
        if stripped.startswith('"""') or stripped.startswith("'''"):
            quote_char = stripped[0:3]
            block_lines = [line]
            
            # Check if it's a one-liner
            if stripped.endswith(quote_char) and len(stripped) > 6:
                comment_lines.insert(0, line)
                if end_idx is None:
                    end_idx = k
                start_idx = k
            else:
                # Multi-line, collect upward
                for j in range(k - 1, max(-1, k - max_window), -1):
                    if j < 0:
                        break
                    prev_line = lines[j] if j < len(lines) else ""
                    block_lines.insert(0, prev_line)
                    if quote_char in prev_line:
                        break
                
                comment_lines = block_lines + comment_lines
                if end_idx is None:
                    end_idx = k
                start_idx = j if j >= 0 else k
        
        # Check for # comment
        elif stripped.startswith("#"):
            comment_lines.insert(0, line)
            if end_idx is None:
                end_idx = k
            start_idx = k
        else:
            # Non-comment, non-blank line - stop
            break
    
    if comment_lines:
        comment_block = "\n".join(comment_lines)
        return (comment_block, start_idx + 1 if start_idx is not None else None,
                end_idx + 1 if end_idx is not None else None)
    
    return (None, None, None)


def _extract_docstring_from_ast(node):
    """Extract docstring from AST node (function/class)."""
    # Build function types tuple (Python 2.7 doesn't have AsyncFunctionDef)
    function_types = (ast.FunctionDef,)
    if HAS_ASYNC_FUNCTION:
        function_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    if not isinstance(node, function_types + (ast.ClassDef,)):
        return None
    
    if not node.body:
        return None
    
    first_stmt = node.body[0]
    if isinstance(first_stmt, ast.Expr):
        # Python 2.7: ast.Str, Python 3.8+: ast.Constant
        if hasattr(ast, 'Str') and isinstance(first_stmt.value, ast.Str):
            return first_stmt.value.s
        elif hasattr(ast, 'Constant') and isinstance(first_stmt.value, ast.Constant):
            if isinstance(first_stmt.value.value, (str, unicode)):
                return first_stmt.value.value
    
    return None


def _extract_signature_from_ast(node, source_lines):
    """Extract function signature from AST node, handling multi-line signatures."""
    # Build function types tuple (Python 2.7 doesn't have AsyncFunctionDef)
    function_types = (ast.FunctionDef,)
    if HAS_ASYNC_FUNCTION:
        function_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    if not isinstance(node, function_types):
        return None
    
    # Get the def line
    def_line_no = node.lineno
    if def_line_no > len(source_lines):
        return None
    
    def_line = source_lines[def_line_no - 1]
    
    # Handle multi-line signatures (find the closing paren)
    signature_lines = [def_line]
    if '(' in def_line:
        # Count parentheses to see if signature spans multiple lines
        paren_count = def_line.count('(') - def_line.count(')')
        if paren_count > 0:
            # Multi-line signature, collect until we find closing paren
            for i in range(def_line_no, min(def_line_no + 15, len(source_lines))):
                if i >= len(source_lines):
                    break
                line = source_lines[i]
                signature_lines.append(line)
                paren_count += line.count('(') - line.count(')')
                if paren_count == 0:
                    break
    
    # Join and clean up signature
    signature = ' '.join(signature_lines).strip()
    # Remove extra whitespace
    signature = re.sub(r'\s+', ' ', signature)
    return signature


def _get_string_value(ast_node):
    """Extract string value from AST node (handles both Python 2.7 and 3.x)."""
    # Python 2.7: ast.Str
    if hasattr(ast, 'Str') and isinstance(ast_node, ast.Str):
        return ast_node.s
    # Python 3.8+: ast.Constant
    elif hasattr(ast, 'Constant') and isinstance(ast_node, ast.Constant):
        if isinstance(ast_node.value, (str, unicode)):
            return ast_node.value
    return None


def _extract_error_messages_from_ast(node):
    """
    Extract error messages from AST node.
    Returns list of (error_message, log_level, source_type) tuples.
    """
    errors = []
    
    if isinstance(node, ast.Call):
        # Check for logging calls: logger.error("msg"), logging.warning("msg")
        if isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            log_level = None
            
            if attr_name in ('error', 'critical', 'exception'):
                log_level = 'E'
            elif attr_name == 'warning':
                log_level = 'W'
            elif attr_name in ('info', 'debug'):
                log_level = 'I'
            
            if log_level:
                # Extract string arguments
                for arg in node.args:
                    str_val = _get_string_value(arg)
                    if str_val:
                        errors.append((str_val, log_level, 'logging'))
                    elif isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute):
                        # Handle .format() calls: "Error: {} {}".format(x, y)
                        if arg.func.attr == 'format' and arg.func.value:
                            format_template = _get_string_value(arg.func.value)
                            if format_template:
                                errors.append((format_template, log_level, 'logging_format_template'))
                    elif isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Mod):
                        # String formatting: "Error: %s" % value
                        str_val = _get_string_value(arg.left)
                        if str_val:
                            errors.append((str_val, log_level, 'logging_format'))
        
        # Check for print() function calls (Python 3): print("ERROR: msg")
        elif isinstance(node.func, ast.Name) and node.func.id == 'print':
            for arg in node.args:
                str_val = _get_string_value(arg)
                if str_val:
                    msg = str_val
                    if 'error' in msg.lower() or 'fail' in msg.lower() or 'exception' in msg.lower():
                        errors.append((msg, 'E', 'print'))
    
    # Check for raise statements: raise ValueError("msg")
    if isinstance(node, ast.Raise):
        # Python 2.7: ast.Raise has 'type', 'inst', 'tback'
        # Python 3: ast.Raise has 'exc', 'cause'
        exc_node = None
        if hasattr(node, 'exc'):
            # Python 3
            exc_node = node.exc
        elif hasattr(node, 'inst'):
            # Python 2.7
            exc_node = node.inst
        
        if exc_node and isinstance(exc_node, ast.Call):
            for arg in exc_node.args:
                str_val = _get_string_value(arg)
                if str_val:
                    errors.append((str_val, 'E', 'exception'))
    
    # Check for print statements (Python 2.7): print "ERROR: msg"
    if hasattr(ast, 'Print') and isinstance(node, ast.Print):
        for value in node.values:
            str_val = _get_string_value(value)
            if str_val:
                msg = str_val
                if 'error' in msg.lower() or 'fail' in msg.lower() or 'exception' in msg.lower():
                    errors.append((msg, 'E', 'print'))
    
    return errors


def _collect_all_errors_from_function(func_node):
    """Collect all error messages from a function AST node."""
    all_errors = []
    log_levels = set()
    
    for node in ast.walk(func_node):
        errors = _extract_error_messages_from_ast(node)
        for error_msg, log_level, source_type in errors:
            all_errors.append({
                'message': error_msg,
                'log_level': log_level,
                'source_type': source_type
            })
            if log_level:
                log_levels.add(log_level)
    
    return all_errors, list(log_levels)


def _extract_custom_exception_classes(node, file_path, source_lines):
    """
    Extract custom exception class definitions from AST.
    Returns list of dicts with exception class info.
    Python 2.7.5 compatible.
    """
    custom_exceptions = []
    
    if isinstance(node, ast.ClassDef):
        # Check if it's an exception class (inherits from Exception or BaseException)
        is_exception = False
        base_classes = []
        
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_name = base.id
                if 'Exception' in base_name or 'Error' in base_name:
                    is_exception = True
                    base_classes.append(base_name)
            elif isinstance(base, ast.Attribute):
                # Handle cases like exceptions.Exception
                if isinstance(base.value, ast.Name):
                    if base.value.id in ('exceptions', 'Exception', 'BaseException'):
                        is_exception = True
                        base_classes.append(base.attr)
                    elif base.attr in ('Exception', 'BaseException', 'Error'):
                        is_exception = True
                        base_classes.append(base.attr)
        
        if is_exception:
            # Extract class info
            class_name = node.name
            docstring = _extract_docstring_from_ast(node)
            
            # Look for __init__ method to find message template
            message_template = None
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == '__init__':
                    # Extract string arguments from __init__ body
                    for stmt in ast.walk(child):
                        if isinstance(stmt, ast.Call):
                            for arg in stmt.args:
                                str_val = _get_string_value(arg)
                                if str_val:
                                    # Check if it looks like an error message
                                    str_lower = str_val.lower()
                                    if any(keyword in str_lower for keyword in ['error', 'message', 'msg', 'fail', 'exception']):
                                        message_template = str_val
                                        break
                            if message_template:
                                break
                    if message_template:
                        break
            
            # Get line numbers
            class_line = node.lineno
            # Estimate end line (class body)
            class_end_line = class_line
            if node.body:
                # Rough estimate: last line of class body
                class_end_line = node.lineno + len(node.body) * 2
                class_end_line = min(class_end_line, len(source_lines))
            
            custom_exceptions.append({
                'class_name': class_name,
                'file_path': file_path,
                'line_number': class_line,
                'base_classes': base_classes,
                'docstring': docstring,
                'message_template': message_template,
                'definition': _slice_lines(source_lines, class_line, class_end_line)
            })
    
    return custom_exceptions


def _find_custom_exception_usage(node, custom_exception_classes):
    """
    Find where custom exception classes are raised.
    Returns list of dicts with usage info.
    Python 2.7.5 compatible.
    """
    usages = []
    
    if isinstance(node, ast.Raise):
        exc_node = None
        # Python 2.7: ast.Raise has 'type', 'inst', 'tback'
        # Python 3: ast.Raise has 'exc', 'cause'
        if hasattr(node, 'exc'):
            # Python 3
            exc_node = node.exc
        elif hasattr(node, 'inst'):
            # Python 2.7
            exc_node = node.inst
        elif hasattr(node, 'type'):
            # Python 2.7 alternative
            exc_node = node.type
        
        if exc_node:
            # Check if it's a custom exception
            exc_class_name = None
            if isinstance(exc_node, ast.Call):
                if isinstance(exc_node.func, ast.Name):
                    exc_class_name = exc_node.func.id
                elif isinstance(exc_node.func, ast.Attribute):
                    exc_class_name = exc_node.func.attr
            elif isinstance(exc_node, ast.Name):
                # Just raising the class without calling: raise MyError
                exc_class_name = exc_node.id
            
            # Check if this matches any custom exception
            if exc_class_name:
                for exc_info in custom_exception_classes:
                    if exc_info['class_name'] == exc_class_name:
                        # Extract message from raise call
                        message = None
                        if isinstance(exc_node, ast.Call):
                            for arg in exc_node.args:
                                str_val = _get_string_value(arg)
                                if str_val:
                                    message = str_val
                                    break
                        
                        usages.append({
                            'exception_class': exc_class_name,
                            'message': message,
                            'line_number': node.lineno,
                            'file_path': exc_info['file_path']
                        })
                        break
    
    return usages


def _collect_custom_exceptions_from_file(file_path, source_lines, tree):
    """
    Collect all custom exception class definitions from a file.
    Returns list of exception info dicts.
    """
    custom_exceptions = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            exceptions = _extract_custom_exception_classes(node, file_path, source_lines)
            custom_exceptions.extend(exceptions)
    
    return custom_exceptions


def _collect_custom_exception_usages_from_file(file_path, source_lines, tree, custom_exception_classes):
    """
    Collect all usages of custom exceptions from a file.
    Returns list of usage info dicts.
    """
    usages = []
    
    for node in ast.walk(tree):
        node_usages = _find_custom_exception_usage(node, custom_exception_classes)
        usages.extend(node_usages)
    
    return usages


def build_custom_error_glossary(all_custom_exceptions, all_exception_usages):
    """
    Build a glossary of custom exceptions from the index.
    Returns dict mapping exception class names to their definitions and usages.
    Python 2.7.5 compatible.
    
    Args:
        all_custom_exceptions: List of custom exception definition dicts
        all_exception_usages: List of usage dicts (collected during file processing)
    """
    glossary = {}
    
    # Initialize glossary with definitions
    for exc_info in all_custom_exceptions:
        class_name = exc_info['class_name']
        if class_name not in glossary:
            glossary[class_name] = {
                'definition': exc_info,
                'usages': []
            }
    
    # Add usages to glossary
    for usage in all_exception_usages:
        exc_class = usage.get('exception_class')
        if exc_class and exc_class in glossary:
            glossary[exc_class]['usages'].append(usage)
    
    return glossary


def extract_function_chunk(file_path, func_node, source_lines, class_name=None, boundary_map=None, source_text=None):
    """
    Extract function as chunk with full metadata including signature, decorators, and perfect boundaries.
    
    Handles:
    - Function signature (from def line, may be multi-line) - both normalized and original
    - Decorators (multi-line support)
    - Leading comment/docstring blocks above function
    - Function docstring (inside function body)
    - Error messages from logging, exceptions, prints
    - Accurate function boundaries using tokenize (with fallback)
    
    Args:
        file_path: Full file path
        func_node: AST FunctionDef or AsyncFunctionDef node
        source_lines: List of source lines (0-indexed)
        class_name: Class name if method, None if module-level
        boundary_map: Optional pre-computed boundary map from _build_function_boundary_map
        source_text: Optional source text (needed if boundary_map is None)
    
    Returns:
        Dictionary with chunk data (backward compatible + new fields)
    """
    def_line = func_node.lineno
    extraction_warnings = []
    
    # Try to get boundary info from token map
    end_line_inclusive = None
    decorator_start_line = None
    decorator_end_line = None
    header_end_line = None
    
    if boundary_map and def_line in boundary_map:
        boundary_info = boundary_map[def_line]
        end_line_inclusive = boundary_info['end_line_inclusive']
        decorator_start_line = boundary_info.get('decorator_start_line')
        decorator_end_line = boundary_info.get('decorator_end_line')
        header_end_line = boundary_info.get('header_end_line', def_line)
    else:
        # Fallback to old algorithm
        extraction_warnings.append("tokenize_failed_used_old_end_algo")
        if hasattr(func_node, 'end_lineno'):
            end_line_inclusive = func_node.end_lineno
        else:
            # Estimate end line by finding next def/class at same or lower indent
            func_indent = _normalize_indent_width(source_lines[def_line - 1])
            for i in range(def_line, min(def_line + 500, len(source_lines))):
                line = source_lines[i]
                if not line.strip():
                    continue
                line_indent = _normalize_indent_width(line)
                if line_indent <= func_indent:
                    stripped = line.lstrip()
                    if stripped.startswith('def ') or stripped.startswith('class ') or stripped.startswith('async def '):
                        end_line_inclusive = i - 1  # Make it inclusive (previous line)
                        break
            else:
                # Didn't find next def/class, use function body estimate
                if func_node.body:
                    # Rough estimate: last line of body
                    end_line_inclusive = def_line + len(func_node.body) * 2  # rough estimate
                    end_line_inclusive = min(end_line_inclusive, len(source_lines))
                    extraction_warnings.append("end_line_fallback_used")
                else:
                    end_line_inclusive = def_line
        
        header_end_line = def_line
        # Try to find header end by looking for ':'
        for i in range(def_line - 1, min(def_line + 15, len(source_lines))):
            if ':' in source_lines[i]:
                # Check if it's the function header (not inside parens - simple heuristic)
                header_end_line = i + 1
                break
    
    # Ensure end_line_inclusive is valid
    if end_line_inclusive is None:
        end_line_inclusive = def_line
    if end_line_inclusive < def_line:
        end_line_inclusive = def_line
    if end_line_inclusive > len(source_lines):
        end_line_inclusive = len(source_lines)
    
    # Extract decorators
    decorator_lines_list, decorator_block = _extract_decorators_from_lines(
        source_lines, decorator_start_line, decorator_end_line, def_line
    )
    
    # Determine start_line_inclusive (leading comment start, or decorator start, or def line)
    start_line_inclusive = def_line
    leading_comment_start = None
    leading_comment_end = None
    
    # Extract leading comments (walk upward from decorator start or def line)
    comment_start_line_idx = def_line - 1
    if decorator_start_line is not None:
        comment_start_line_idx = decorator_start_line - 1
    
    leading_comment, comment_start, comment_end = _extract_leading_comment_block(
        source_lines, comment_start_line_idx, max_window=30, stop_at_decorators=False
    )
    
    if comment_start is not None:
        leading_comment_start = comment_start
        leading_comment_end = comment_end
        start_line_inclusive = comment_start
    elif decorator_start_line is not None:
        start_line_inclusive = decorator_start_line
    
    # Extract signature (normalized for backward compatibility)
    signature = _extract_signature_from_ast(func_node, source_lines)
    
    # Extract signature_original (preserving formatting)
    signature_original = _extract_signature_original(source_lines, def_line, header_end_line)
    if signature_original is None:
        # Fallback to def line only
        signature_original = source_lines[def_line - 1] if def_line <= len(source_lines) else ""
    
    # Extract docstring from function body
    docstring = _extract_docstring_from_ast(func_node)
    
    # Extract error messages
    error_messages, log_levels = _collect_all_errors_from_function(func_node)
    
    # Extract code (def + body only, for backward compatibility)
    func_code = _slice_lines(source_lines, def_line, end_line_inclusive)
    
    # Extract code_full (includes decorators and leading comments if present)
    code_full_parts = []
    if leading_comment_start is not None:
        code_full_parts.append(_slice_lines(source_lines, leading_comment_start, leading_comment_end))
    if decorator_block:
        code_full_parts.append(decorator_block)
    code_full_parts.append(_slice_lines(source_lines, def_line, end_line_inclusive))
    code_full = "\n".join(code_full_parts) if code_full_parts else func_code
    
    # Build spans
    decorator_span = None
    if decorator_start_line is not None and decorator_end_line is not None:
        decorator_span = {'start': decorator_start_line, 'end': decorator_end_line}
    
    leading_comment_span = None
    if leading_comment_start is not None and leading_comment_end is not None:
        leading_comment_span = {'start': leading_comment_start, 'end': leading_comment_end}
    
    signature_span = {'start': def_line, 'end': header_end_line}
    
    # Build chunk with backward-compatible fields first
    chunk = {
        # Backward-compatible fields (must remain)
        "file_path": file_path,
        "function_name": func_node.name,
        "class_name": class_name,
        "line_start": start_line_inclusive,  # Updated to include envelope
        "line_end": end_line_inclusive,  # Now inclusive
        "signature": signature,  # Normalized for search
        "code": func_code,  # Def + body only (backward compatible)
        "docstring": docstring,
        "leading_comment": leading_comment,
        "error_messages": error_messages,
        "log_levels": log_levels,
        
        # New fields for perfect extraction
        "def_line": def_line,
        "start_line_inclusive": start_line_inclusive,
        "end_line_inclusive": end_line_inclusive,
        "signature_original": signature_original,
        "decorators": decorator_lines_list,
        "decorator_block": decorator_block,
        "code_full": code_full,
        "leading_comment_span": leading_comment_span,
        "decorator_span": decorator_span,
        "signature_span": signature_span,
        "extraction_warnings": extraction_warnings,
    }
    
    # Generate chunk ID using stable subset (backward compatible fields only)
    # This ensures chunk_id doesn't change when new fields are added
    stable_chunk = {
        "file_path": chunk["file_path"],
        "function_name": chunk["function_name"],
        "class_name": chunk["class_name"],
        "line_start": chunk["line_start"],
        "line_end": chunk["line_end"],
        "signature": chunk["signature"],
        "code": chunk["code"],
        "docstring": chunk["docstring"],
        "leading_comment": chunk["leading_comment"],
        "error_messages": chunk["error_messages"],
        "log_levels": chunk["log_levels"],
    }
    
    chunk_json = json.dumps(stable_chunk, sort_keys=True, ensure_ascii=False)
    if PY2:
        if isinstance(chunk_json, unicode):
            chunk_json = chunk_json.encode('utf-8')
    else:
        chunk_json = chunk_json.encode('utf-8')
    
    chunk_id = hashlib.sha256(chunk_json).hexdigest()[:16]
    chunk["chunk_id"] = chunk_id
    
    return chunk


def _extract_functions_from_node(node, file_path, source_lines, class_name=None, chunks=None, 
                                 error_index=None, stats=None, boundary_map=None, source_text=None):
    """
    Recursively extract functions from AST node, tracking class context.
    
    Args:
        node: AST node to process
        file_path: Full file path
        source_lines: List of source lines (0-indexed)
        class_name: Class name if method, None if module-level
        chunks: List to append chunks to
        error_index: Dict to build error index in
        stats: Dict to update statistics in
        boundary_map: Optional pre-computed boundary map from _build_function_boundary_map
        source_text: Optional source text (for boundary map fallback)
    """
    if chunks is None:
        chunks = []
    if error_index is None:
        error_index = {}
    if stats is None:
        stats = {'functions_found': 0, 'errors_found': 0}
    
    # Extract functions at this level
    # Build function types tuple (Python 2.7 doesn't have AsyncFunctionDef)
    function_types = (ast.FunctionDef,)
    if HAS_ASYNC_FUNCTION:
        function_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    if isinstance(node, function_types):
        chunk = extract_function_chunk(file_path, node, source_lines, class_name, boundary_map, source_text)
        chunks.append(chunk)
        stats['functions_found'] += 1
        
        # Build error index
        for error_info in chunk['error_messages']:
            error_msg = error_info['message']
            if error_msg:
                # Normalize error message (lowercase for indexing, but keep original)
                error_key = error_msg.lower().strip()
                if error_key not in error_index:
                    error_index[error_key] = []
                error_index[error_key].append({
                    'chunk_id': chunk['chunk_id'],
                    'original_message': error_msg,  # Keep original for exact matching
                    'log_level': error_info['log_level'],
                    'source_type': error_info['source_type']
                })
                stats['errors_found'] += 1
    
    # Recursively process child nodes
    if isinstance(node, ast.ClassDef):
        # Enter class context
        new_class_name = node.name
        # Process class body
        for child in node.body:
            _extract_functions_from_node(child, file_path, source_lines, new_class_name,
                                        chunks, error_index, stats, boundary_map, source_text)
    elif hasattr(node, 'body'):
        # Process body of function/module/etc
        for child in node.body:
            _extract_functions_from_node(child, file_path, source_lines, class_name,
                                        chunks, error_index, stats, boundary_map, source_text)
    elif hasattr(node, 'orelse'):
        # Handle if/else, try/except, etc.
        for child in node.orelse:
            _extract_functions_from_node(child, file_path, source_lines, class_name,
                                        chunks, error_index, stats, boundary_map, source_text)
    elif hasattr(node, 'handlers'):
        # Handle try/except handlers
        for handler in node.handlers:
            if hasattr(handler, 'body'):
                for child in handler.body:
                    _extract_functions_from_node(child, file_path, source_lines, class_name,
                                                chunks, error_index, stats, boundary_map, source_text)
    
    return chunks, error_index, stats


def index_codebase(root_path, output_path, include_exts=None, exclude_dirs=None, 
                   max_file_bytes=DEFAULT_MAX_FILE_BYTES, progress_cb=None):
    """
    Index entire codebase, extracting functions and error messages.
    
    Returns index dictionary with:
    - chunks: list of all function chunks
    - error_index: mapping from error message -> [chunk_ids]
    - custom_error_glossary: mapping of custom exception classes to definitions and usages
    - stats: indexing statistics
    """
    chunks = []
    error_index = {}  # error_message -> [chunk_ids]
    all_custom_exceptions = []  # Collect all custom exception class definitions
    all_exception_usages = []  # Collect all custom exception usages
    stats = {
        'files_processed': 0,
        'files_failed': 0,
        'functions_found': 0,
        'errors_found': 0,
        'custom_exceptions_found': 0,
        'start_time': time.time(),
    }
    
    if include_exts is None:
        include_exts = DEFAULT_INCLUDE_EXTS
    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDE_DIRS
    
    for file_path in safe_walk_files([root_path], include_exts=include_exts,
                                      exclude_dir_names=exclude_dirs,
                                      max_file_bytes=max_file_bytes):
        try:
            source = _safe_read_file(file_path)
            if source is None:
                stats['files_failed'] += 1
                continue
            
            source_lines = source.splitlines()
            
            # Parse AST
            try:
                tree = ast.parse(source, filename=file_path)
            except SyntaxError:
                stats['files_failed'] += 1
                continue
            
            # Collect custom exception classes from this file
            file_custom_exceptions = _collect_custom_exceptions_from_file(file_path, source_lines, tree)
            all_custom_exceptions.extend(file_custom_exceptions)
            stats['custom_exceptions_found'] += len(file_custom_exceptions)
            
            # Collect custom exception usages from this file (need all exceptions found so far)
            # We'll do a second pass after all files are processed, but collect what we can now
            file_exception_usages = _collect_custom_exception_usages_from_file(
                file_path, source_lines, tree, all_custom_exceptions
            )
            all_exception_usages.extend(file_exception_usages)
            
            # Build function boundary map using tokenize (with fallback)
            boundary_map = _build_function_boundary_map(source_lines, source)
            
            # Extract functions recursively (tracks class context properly)
            file_chunks, file_error_index, file_stats = _extract_functions_from_node(
                tree, file_path, source_lines, class_name=None,
                boundary_map=boundary_map, source_text=source
            )
            
            chunks.extend(file_chunks)
            stats['functions_found'] += file_stats['functions_found']
            stats['errors_found'] += file_stats['errors_found']
            
            # Merge error index
            for error_key, error_list in file_error_index.items():
                if error_key not in error_index:
                    error_index[error_key] = []
                error_index[error_key].extend(error_list)
            
            stats['files_processed'] += 1
            
            # Progress callback
            if progress_cb and stats['files_processed'] % 100 == 0:
                try:
                    progress_cb(stats)
                except Exception:
                    pass
        
        except Exception as e:
            print("ERROR: Failed to process {}: {}".format(file_path, e), file=sys.stderr)
            stats['files_failed'] += 1
            continue
    
    stats['elapsed_seconds'] = time.time() - stats['start_time']
    
    # Second pass: Re-scan files to find any usages of exceptions that were defined later
    # This ensures we catch all usages even if exception was defined after it was used
    print("Scanning for custom exception usages...", file=sys.stderr)
    for file_path in safe_walk_files([root_path], include_exts=include_exts,
                                      exclude_dir_names=exclude_dirs,
                                      max_file_bytes=max_file_bytes):
        try:
            source = _safe_read_file(file_path)
            if source is None:
                continue
            
            source_lines = source.splitlines()
            try:
                tree = ast.parse(source, filename=file_path)
            except SyntaxError:
                continue
            
            # Find usages with all exceptions now known
            file_exception_usages = _collect_custom_exception_usages_from_file(
                file_path, source_lines, tree, all_custom_exceptions
            )
            
            # Add new usages (avoid duplicates)
            existing_usage_keys = set()
            for usage in all_exception_usages:
                key = (usage.get('exception_class'), usage.get('file_path'), usage.get('line_number'))
                existing_usage_keys.add(key)
            
            for usage in file_exception_usages:
                key = (usage.get('exception_class'), usage.get('file_path'), usage.get('line_number'))
                if key not in existing_usage_keys:
                    all_exception_usages.append(usage)
        except Exception:
            continue
    
    # Build custom error glossary (now that we have all exceptions and usages)
    custom_error_glossary = build_custom_error_glossary(all_custom_exceptions, all_exception_usages)
    
    # Build index
    index = {
        "schema_version": "1.0",
        "created_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        "chunks": chunks,
        "error_index": error_index,
        "custom_error_glossary": custom_error_glossary,
        "stats": stats,
        "total_chunks": len(chunks),
        "total_errors": stats['errors_found'],
    }
    
    # Save index (create directory if needed)
    try:
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(os.path.abspath(output_path))
        if output_dir and not os.path.exists(output_dir):
            # Python 2.7 doesn't have exist_ok parameter, so check manually
            try:
                os.makedirs(output_dir)
            except OSError:
                # Directory might have been created by another process
                if not os.path.exists(output_dir):
                    raise
        
        with open(output_path, 'wb') as f:
            json_str = json.dumps(index, indent=2, ensure_ascii=False)
            if PY2:
                if isinstance(json_str, unicode):
                    json_bytes = json_str.encode('utf-8')
                else:
                    json_bytes = json_str
            else:
                json_bytes = json_str.encode('utf-8')
            f.write(json_bytes)
    except (IOError, OSError) as e:
        print("ERROR: Failed to write index: {}".format(e), file=sys.stderr)
        return None
    
    return index


def main():
    parser = argparse.ArgumentParser(
        description='Index codebase for log analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Index Python files only:
  python tools/ingest.py --root /opt/memjet --out /index.json
  
  # Index with progress updates:
  python tools/ingest.py --root /opt/memjet --out /index.json --progress
        """
    )
    # Default root: always use /opt/memjet (printer filesystem)
    default_root = '/opt/memjet'
    
    # Default output: save to /index.json (root of filesystem where script lives)
    default_out = '/index.json'
    
    parser.add_argument('--root', default=default_root, 
                       help='Root directory to index (default: /opt/memjet)')
    parser.add_argument('--out', default=default_out, 
                       help='Output index file path (default: /index.json)')
    parser.add_argument('--include-ext', nargs='+', default=['.py'],
                       help='File extensions to include (default: .py)')
    parser.add_argument('--exclude-dir', nargs='+', default=None,
                       help='Directory names to exclude (default: common build/cache dirs)')
    parser.add_argument('--max-file-bytes', type=int, default=DEFAULT_MAX_FILE_BYTES,
                       help='Maximum file size to process (default: 10MB)')
    parser.add_argument('--progress', action='store_true', default=True,
                       help='Show progress updates during indexing (default: enabled)')
    
    args = parser.parse_args()
    
    # Resolve root path to absolute path
    args.root = os.path.abspath(args.root)
    
    if not os.path.isdir(args.root):
        print("ERROR: Root path is not a directory: {}".format(args.root), file=sys.stderr)
        print("Current working directory: {}".format(os.getcwd()), file=sys.stderr)
        sys.exit(1)
    
    print("Indexing codebase: {}".format(args.root))
    print("Output: {}".format(args.out))
    print("=" * 80)
    
    def progress_callback(stats):
        if args.progress:
            print("Progress: {} files, {} functions, {} errors...".format(
                stats['files_processed'], stats['functions_found'], stats['errors_found']
            ))
    
    index = index_codebase(
        root_path=args.root,
        output_path=args.out,
        include_exts=args.include_ext,
        exclude_dirs=args.exclude_dir,
        max_file_bytes=args.max_file_bytes,
        progress_cb=progress_callback if args.progress else None
    )
    
    if index is None:
        sys.exit(1)
    
    stats = index['stats']
    custom_glossary = index.get('custom_error_glossary', {})
    print()
    print("=" * 80)
    print("Indexing complete!")
    print("  Files processed: {:,}".format(stats['files_processed']))
    print("  Files failed: {:,}".format(stats['files_failed']))
    print("  Functions found: {:,}".format(stats['functions_found']))
    print("  Errors found: {:,}".format(stats['errors_found']))
    print("  Custom exceptions found: {:,}".format(stats.get('custom_exceptions_found', 0)))
    print("  Total chunks: {:,}".format(index['total_chunks']))
    print("  Elapsed time: {:.2f} seconds".format(stats['elapsed_seconds']))
    if custom_glossary:
        print("  Custom error glossary: {} exception classes".format(len(custom_glossary)))
    print("  Index saved to: {}".format(args.out))
    print("=" * 80)
    
    sys.exit(0)


if __name__ == '__main__':
    main()

