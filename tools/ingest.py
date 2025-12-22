#!/usr/bin/env python2
"""
Codebase ingestion for printer log analysis.

Indexes functions and extracts error messages for fast lookup.
Python 2.7.5 compatible, stdlib only, read-only operation.

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


def _extract_leading_comment_block(lines, def_line_idx, max_window=30):
    """
    Extract leading comment/docstring block above function definition.
    Looks for triple-quoted strings (docstrings) or # comments above the def line.
    Returns (text, start_line, end_line) or (None, None, None).
    """
    if def_line_idx <= 0:
        return (None, None, None)
    
    comment_lines = []
    start_idx = None
    end_idx = None
    blank_gap = 0
    max_blank_gap = 1  # Allow at most 1 blank line gap
    
    # Walk upward from def line
    for k in range(def_line_idx - 1, max(-1, def_line_idx - max_window - 1), -1):
        if k < 0:
            break
        
        line = lines[k] if k < len(lines) else ""
        stripped = line.lstrip()
        
        if not stripped:
            blank_gap += 1
            if blank_gap > max_blank_gap:
                break
            continue
        
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


def extract_function_chunk(file_path, func_node, source_lines, class_name=None):
    """
    Extract function as chunk with full metadata including signature.
    
    Handles:
    - Function signature (from def line, may be multi-line)
    - Leading comment/docstring blocks above function (may contain signature info)
    - Function docstring (inside function body)
    - Error messages from logging, exceptions, prints
    """
    # Get function signature
    signature = _extract_signature_from_ast(func_node, source_lines)
    
    # Get function code bounds
    start_line = func_node.lineno
    # Python 2.7 AST doesn't have end_lineno, so we need to estimate
    # or find the next def/class at same or lower indentation
    end_line = start_line
    if hasattr(func_node, 'end_lineno'):
        end_line = func_node.end_lineno
    else:
        # Estimate end line by finding next def/class at same or lower indent
        func_indent = len(source_lines[start_line - 1]) - len(source_lines[start_line - 1].lstrip())
        for i in range(start_line, min(start_line + 500, len(source_lines))):
            line = source_lines[i]
            if not line.strip():
                continue
            line_indent = len(line) - len(line.lstrip())
            if line_indent <= func_indent:
                stripped = line.lstrip()
                if stripped.startswith('def ') or stripped.startswith('class ') or stripped.startswith('async def '):
                    end_line = i
                    break
        else:
            # Didn't find next def/class, use function body estimate
            if func_node.body:
                # Rough estimate: last line of body
                end_line = start_line + len(func_node.body) * 2  # rough estimate
                end_line = min(end_line, len(source_lines))
    
    # Extract leading comment/docstring block above function
    leading_comment, comment_start, comment_end = _extract_leading_comment_block(
        source_lines, start_line - 1, max_window=30
    )
    
    # Extract docstring from function body
    docstring = _extract_docstring_from_ast(func_node)
    
    # Extract error messages
    error_messages, log_levels = _collect_all_errors_from_function(func_node)
    
    # Get function code
    func_code = "\n".join(source_lines[start_line - 1:end_line])
    
    # Build chunk
    chunk = {
        "file_path": file_path,
        "function_name": func_node.name,
        "class_name": class_name,
        "line_start": start_line,
        "line_end": end_line,
        "signature": signature,
        "code": func_code,
        "docstring": docstring,
        "leading_comment": leading_comment,
        "error_messages": error_messages,
        "log_levels": log_levels,
    }
    
    # Generate chunk ID (deterministic hash)
    chunk_json = json.dumps(chunk, sort_keys=True, ensure_ascii=False)
    if PY2:
        if isinstance(chunk_json, unicode):
            chunk_json = chunk_json.encode('utf-8')
    else:
        chunk_json = chunk_json.encode('utf-8')
    
    chunk_id = hashlib.sha256(chunk_json).hexdigest()[:16]
    chunk["chunk_id"] = chunk_id
    
    return chunk


def _extract_functions_from_node(node, file_path, source_lines, class_name=None, chunks=None, 
                                 error_index=None, stats=None):
    """
    Recursively extract functions from AST node, tracking class context.
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
        chunk = extract_function_chunk(file_path, node, source_lines, class_name)
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
                                        chunks, error_index, stats)
    elif hasattr(node, 'body'):
        # Process body of function/module/etc
        for child in node.body:
            _extract_functions_from_node(child, file_path, source_lines, class_name,
                                        chunks, error_index, stats)
    elif hasattr(node, 'orelse'):
        # Handle if/else, try/except, etc.
        for child in node.orelse:
            _extract_functions_from_node(child, file_path, source_lines, class_name,
                                        chunks, error_index, stats)
    elif hasattr(node, 'handlers'):
        # Handle try/except handlers
        for handler in node.handlers:
            if hasattr(handler, 'body'):
                for child in handler.body:
                    _extract_functions_from_node(child, file_path, source_lines, class_name,
                                                chunks, error_index, stats)
    
    return chunks, error_index, stats


def index_codebase(root_path, output_path, include_exts=None, exclude_dirs=None, 
                   max_file_bytes=DEFAULT_MAX_FILE_BYTES, progress_cb=None):
    """
    Index entire codebase, extracting functions and error messages.
    
    Returns index dictionary with:
    - chunks: list of all function chunks
    - error_index: mapping from error message -> [chunk_ids]
    - stats: indexing statistics
    """
    chunks = []
    error_index = {}  # error_message -> [chunk_ids]
    stats = {
        'files_processed': 0,
        'files_failed': 0,
        'functions_found': 0,
        'errors_found': 0,
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
            
            # Extract functions recursively (tracks class context properly)
            file_chunks, file_error_index, file_stats = _extract_functions_from_node(
                tree, file_path, source_lines, class_name=None
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
    
    # Build index
    index = {
        "schema_version": "1.0",
        "created_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        "chunks": chunks,
        "error_index": error_index,
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
    print()
    print("=" * 80)
    print("Indexing complete!")
    print("  Files processed: {:,}".format(stats['files_processed']))
    print("  Files failed: {:,}".format(stats['files_failed']))
    print("  Functions found: {:,}".format(stats['functions_found']))
    print("  Errors found: {:,}".format(stats['errors_found']))
    print("  Total chunks: {:,}".format(index['total_chunks']))
    print("  Elapsed time: {:.2f} seconds".format(stats['elapsed_seconds']))
    print("  Index saved to: {}".format(args.out))
    print("=" * 80)
    
    sys.exit(0)


if __name__ == '__main__':
    main()

