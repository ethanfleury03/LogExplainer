#!/usr/bin/env python
"""
STRICTLY READ-ONLY production logging audit tool for Python repositories.

Scans production code (excludes tests) for logging patterns and generates
a human-readable Markdown report to STDOUT only.

Python 2.7.5 Compatibility:
- Uses only Python 2.7 AST node types (ast.Str, ast.Num, ast.Name, etc.)
- No Python 3-only nodes (ast.Constant, ast.NameConstant, ast.JoinedStr)
- Handles unicode/str safely for Python 2.7
- All aggregation code paths accept (template, kind, level, file_path, line_no) format

Features:
- Detects stdlib logging, structlog, and generic logger usage (production code only)
- Quantifies error logging (total calls + unique message templates)
- Identifies logging configuration points and entry-point risks
- Tracks print() usage in production code
- Detects JSON logging configuration
- Provides actionable findings for logging improvements

ABSOLUTE SAFETY GUARANTEE:
- This script ONLY READS files.
- It NEVER writes, creates, modifies, renames, or deletes ANY files or directories.
- Output is printed to STDOUT ONLY (no --out flag, no file writing).
- No temp files, no logging to disk, no filesystem modifications.

Usage:
    python tools/dev/repo_scan.py --root /path/to/repo
    python tools/dev/repo_scan.py --root /path/to/repo > report.md  # Redirect stdout yourself
"""

from __future__ import print_function

import argparse
import ast
import fnmatch
import json
import os
import re
import sys
import time
from collections import defaultdict, Counter

# Prevent bytecode generation
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
if hasattr(sys, "dont_write_bytecode"):
    sys.dont_write_bytecode = True


# Default ignore directories (for content scanning, not counting)
DEFAULT_IGNORE_DIRS = {
    ".git", ".svn", ".hg", ".idea", ".vscode",
    "node_modules", "venv", ".venv", "env", ".env",
    "dist", "build", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".next", "out",
    "proc", "run", "sys", "target", "tmp", "var/tmp",
    ".cache", "models", "latest_model", "storage", "logs"
}

# Script-like directory markers (for print classification)
SCRIPT_PATH_MARKERS = ("/scripts/", "\\scripts\\", "/bin/", "\\bin\\")


class LoggingASTVisitor(ast.NodeVisitor):
    """AST visitor to extract logging patterns from Python code."""
    
    def __init__(self, file_content, file_path=""):
        self.file_content = file_content
        self.lines = file_content.splitlines()
        self.file_path = file_path
        
        # Import tracking
        self.has_stdlib_logging = False
        self.has_structlog = False
        self.has_loguru = False
        self.has_traceback = False
        
        # Import aliases (for tracking custom get_logger functions)
        self.import_aliases = {}  # alias_name -> (module, original_name)
        
        # Logger variable tracking (enhanced)
        self.structlog_loggers = set()  # Variable names assigned from structlog.get_logger()
        self.stdlib_loggers = set()  # Variable names assigned from logging.getLogger()
        self.framework_loggers = set()  # Framework logger variable names
        self.attribute_loggers = {}  # (obj_name, attr) -> logger_type
        
        # Unknown logger variable tracking (for diagnostics)
        self.unknown_logger_vars = defaultdict(int)  # var_name -> call_count
        self.unknown_logger_var_files = defaultdict(set)  # var_name -> set of files
        
        # Counts
        self.stdlib_imports = 0
        self.structlog_imports = 0
        self.loguru_imports = 0
        self.stdlib_getlogger_calls = 0
        self.structlog_getlogger_calls = 0
        
        # Logging calls by category
        self.stdlib_calls = defaultdict(int)  # level -> count
        self.structlog_calls = defaultdict(int)  # level -> count
        self.framework_calls = defaultdict(int)  # level -> count
        self.generic_calls = defaultdict(int)  # level -> count
        self.print_calls = 0
        self.print_calls_in_scripts = 0
        self.print_calls_outside_scripts = 0
        
        # Exception/stack trace tracking
        self.exception_calls = 0  # logger.exception()
        self.exc_info_calls = 0  # logger.error(..., exc_info=True)
        self.traceback_calls = 0  # traceback.print_exc / format_exc
        self.bare_except_blocks = []  # List of (line_no, file_context)
        
        # Error template tracking
        self.error_templates = []  # List of (template, kind, level, line_no) for error/exception/critical calls
        
        # Config detection with context
        self.config_calls = []  # List of (line_no, config_type, is_guarded)
        self.json_formatting_indicators = []
        
    def visit_Import(self, node):
        """Track import statements."""
        for alias in node.names:
            if alias.name == "logging":
                self.has_stdlib_logging = True
                self.stdlib_imports += 1
            elif alias.name == "structlog":
                self.has_structlog = True
                self.structlog_imports += 1
            elif alias.name == "loguru":
                self.has_loguru = True
                self.loguru_imports += 1
            elif alias.name == "traceback":
                self.has_traceback = True
            # Track aliases
            if alias.asname:
                self.import_aliases[alias.asname] = (alias.name, alias.name)
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node):
        """Track from ... import statements."""
        if node.module == "logging":
            self.has_stdlib_logging = True
            self.stdlib_imports += 1
            # Track getLogger imports from logging
            for alias in node.names:
                if alias.name == "getLogger":
                    if alias.asname:
                        self.import_aliases[alias.asname] = (node.module, alias.name)
                    else:
                        self.import_aliases["getLogger"] = (node.module, alias.name)
        elif node.module == "structlog":
            self.has_structlog = True
            self.structlog_imports += 1
            # Track get_logger imports from structlog
            for alias in node.names:
                if alias.name == "get_logger":
                    if alias.asname:
                        self.import_aliases[alias.asname] = (node.module, alias.name)
                    else:
                        self.import_aliases["get_logger"] = (node.module, alias.name)
        elif node.module == "loguru":
            self.has_loguru = True
            self.loguru_imports += 1
        elif node.module == "traceback":
            self.has_traceback = True
        
        # Track import aliases (e.g., from backend.logging_config import get_logger as get_logger_alias)
        if node.module:
            for alias in node.names:
                if alias.asname:
                    self.import_aliases[alias.asname] = (node.module, alias.name)
                else:
                    self.import_aliases[alias.name] = (node.module, alias.name)
        
        self.generic_visit(node)
    
    def visit_Assign(self, node):
        """Track logger variable assignments (enhanced to track more patterns)."""
        if isinstance(node.value, ast.Call):
            call = node.value
            logger_type = None
            
            # Check direct calls: logging.getLogger(...)
            if isinstance(call.func, ast.Attribute):
                if (isinstance(call.func.value, ast.Name) and 
                    call.func.value.id == "logging" and
                    call.func.attr == "getLogger"):
                    self.stdlib_getlogger_calls += 1
                    logger_type = "stdlib"
                    
                    # Check for framework loggers
                    if (len(call.args) > 0 and 
                        isinstance(call.args[0], ast.Str)):
                        logger_name = call.args[0].s
                        if logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", 
                                         "gunicorn", "gunicorn.error", "gunicorn.access"):
                            logger_type = "framework"
                
                # structlog.get_logger(...)
                elif (isinstance(call.func.value, ast.Name) and
                      call.func.value.id == "structlog" and
                      call.func.attr == "get_logger"):
                    self.structlog_getlogger_calls += 1
                    logger_type = "structlog"
            
            # Check imported get_logger/getLogger functions
            elif isinstance(call.func, ast.Name):
                func_name = call.func.id
                if func_name in self.import_aliases:
                    module, orig_name = self.import_aliases[func_name]
                    # Check if it's from logging or structlog
                    if module == "logging" and orig_name == "getLogger":
                        self.stdlib_getlogger_calls += 1
                        logger_type = "stdlib"
                    elif module == "structlog" and orig_name == "get_logger":
                        self.structlog_getlogger_calls += 1
                        logger_type = "structlog"
                    # Heuristic: if it's from a logging config module, treat as stdlib
                    elif "log" in module.lower() or "log" in orig_name.lower():
                        logger_type = "stdlib"
            
            # Track variable names
            if logger_type:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if logger_type == "stdlib":
                            self.stdlib_loggers.add(target.id)
                        elif logger_type == "structlog":
                            self.structlog_loggers.add(target.id)
                        elif logger_type == "framework":
                            self.framework_loggers.add(target.id)
                    
                    # Track attribute assignments: self.logger = ..., self._log = ..., self.foo._log = ...
                    elif isinstance(target, ast.Attribute):
                        # Handle nested attributes: self.foo._log -> extract final attr name
                        attr_chain = []
                        current = target
                        while isinstance(current, ast.Attribute):
                            attr_chain.insert(0, current.attr)
                            current = current.value
                        
                        # If base is 'self' or a simple name, track it
                        if isinstance(current, ast.Name):
                            obj_name = current.id
                            # Store with final attribute name (e.g., "_log", "log", "_logger")
                            final_attr = attr_chain[-1] if attr_chain else None
                            if final_attr:
                                self.attribute_loggers[(obj_name, final_attr)] = logger_type
        
        self.generic_visit(node)
    
    def visit_Print(self, node):
        """Track Python 2 print statements (print "x" syntax)."""
        # Python 2 print statement: print "x" or print >>sys.stderr, "x"
        self.print_calls += 1
        # Check if file path contains script-like markers
        if self.file_path:
            file_path_lower = self.file_path.lower()
            is_script = any(marker in file_path_lower for marker in SCRIPT_PATH_MARKERS)
            if is_script:
                self.print_calls_in_scripts += 1
            else:
                self.print_calls_outside_scripts += 1
        else:
            self.print_calls_outside_scripts += 1
        self.generic_visit(node)
    
    def visit_Call(self, node):
        """Track function calls (logging, print, config, exceptions)."""
        # Print calls - split by script-like paths
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            self.print_calls += 1
            # Check if file path contains script-like markers
            if self.file_path:
                file_path_lower = self.file_path.lower()
                is_script = any(marker in file_path_lower for marker in SCRIPT_PATH_MARKERS)
                if is_script:
                    self.print_calls_in_scripts += 1
                else:
                    self.print_calls_outside_scripts += 1
            else:
                self.print_calls_outside_scripts += 1
            return
        
        # Traceback calls
        if isinstance(node.func, ast.Attribute):
            if (isinstance(node.func.value, ast.Name) and 
                node.func.value.id == "traceback" and
                node.func.attr in ("print_exc", "format_exc")):
                self.traceback_calls += 1
                return
        
        # Logging method calls (logger.info, logging.info, etc.)
        # Support aliases: warn -> warning, fatal -> critical
        if isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            # Normalize aliases
            if attr_name == "warn":
                attr_name = "warning"
            elif attr_name == "fatal":
                attr_name = "critical"
            
            if attr_name in ("debug", "info", "warning", "error", "critical", "exception"):
                line_no = node.lineno
                
                # Track exception() calls (separate from error level)
                if attr_name == "exception":
                    self.exception_calls += 1
                    # Count as EXCEPTION level, not ERROR
                    level_to_count = "exception"
                else:
                    level_to_count = attr_name
                
                # Extract error template for error/exception/critical calls
                if level_to_count in ("error", "exception", "critical"):
                    template, kind = self._extract_error_template(node)
                    self.error_templates.append((template, kind, level_to_count, line_no))
                
                # Check for exc_info=True in keyword arguments
                for kw in node.keywords:
                    if kw.arg == "exc_info":
                        # Handle boolean values (Python 2.7: True/False/None are ast.Name nodes)
                        if isinstance(kw.value, ast.Name) and kw.value.id == "True":
                            self.exc_info_calls += 1
                
                # Check if it's logging.info(...) - direct stdlib call
                if (isinstance(node.func.value, ast.Name) and 
                    node.func.value.id == "logging"):
                    self.stdlib_calls[level_to_count] += 1
                    return
                
                # Framework logger detection
                if isinstance(node.func.value, ast.Attribute):
                    # app.logger.* (Flask-style)
                    if (isinstance(node.func.value.value, ast.Name) and
                        node.func.value.value.id in ("app", "current_app") and
                        node.func.value.attr == "logger"):
                        self.framework_calls[level_to_count] += 1
                        return
                    
                    # fastapi.logger.*
                    if (isinstance(node.func.value.value, ast.Name) and
                        node.func.value.value.id == "fastapi" and
                        node.func.value.attr == "logger"):
                        self.framework_calls[level_to_count] += 1
                        return
                
                # Check if it's a known logger variable
                if isinstance(node.func.value, ast.Name):
                    var_name = node.func.value.id
                    if var_name in self.structlog_loggers:
                        self.structlog_calls[level_to_count] += 1
                        return
                    elif var_name in self.stdlib_loggers:
                        self.stdlib_calls[level_to_count] += 1
                        return
                    elif var_name in self.framework_loggers:
                        self.framework_calls[level_to_count] += 1
                        return
                
                # Check attribute access: self.logger.*, self._log.*, self.foo._log.*
                if isinstance(node.func.value, ast.Attribute):
                    # Extract attribute chain (e.g., self.foo._log -> ["self", "foo", "_log"])
                    attr_chain = []
                    current = node.func.value
                    while isinstance(current, ast.Attribute):
                        attr_chain.insert(0, current.attr)
                        current = current.value
                    
                    # If base is a Name (like 'self'), resolve the final attribute
                    if isinstance(current, ast.Name):
                        obj_name = current.id
                        final_attr = attr_chain[-1] if attr_chain else None
                        if final_attr:
                            logger_type = self.attribute_loggers.get((obj_name, final_attr))
                            if logger_type == "stdlib":
                                self.stdlib_calls[level_to_count] += 1
                                return
                            elif logger_type == "structlog":
                                self.structlog_calls[level_to_count] += 1
                                return
                            elif logger_type == "framework":
                                self.framework_calls[level_to_count] += 1
                                return
                
                # Generic logger call (unknown logger variable) - track variable name and file
                if isinstance(node.func.value, ast.Name):
                    var_name = node.func.value.id
                    self.unknown_logger_vars[var_name] += 1
                    if self.file_path:
                        self.unknown_logger_var_files[var_name].add(self.file_path)
                elif isinstance(node.func.value, ast.Attribute):
                    # Track attribute access patterns (e.g., self._log, self.foo._log)
                    var_name = self._stringify_attribute_chain(node.func.value)
                    if var_name:
                        self.unknown_logger_vars[var_name] += 1
                        if self.file_path:
                            self.unknown_logger_var_files[var_name].add(self.file_path)
                
                self.generic_calls[level_to_count] += 1
        
        # Config calls with context detection
        if isinstance(node.func, ast.Attribute):
            is_guarded = self._is_config_guarded(node)
            
            if node.func.attr == "basicConfig":
                if (isinstance(node.func.value, ast.Name) and 
                    node.func.value.id == "logging"):
                    self.config_calls.append((node.lineno, "basicConfig", is_guarded))
            elif node.func.attr == "dictConfig":
                if (isinstance(node.func.value, ast.Attribute) and
                    isinstance(node.func.value.value, ast.Name) and
                    node.func.value.value.id == "logging" and
                    node.func.value.attr == "config"):
                    self.config_calls.append((node.lineno, "dictConfig", is_guarded))
            elif node.func.attr == "fileConfig":
                if (isinstance(node.func.value, ast.Attribute) and
                    isinstance(node.func.value.value, ast.Name) and
                    node.func.value.value.id == "logging" and
                    node.func.value.attr == "config"):
                    self.config_calls.append((node.lineno, "fileConfig", is_guarded))
            elif node.func.attr == "configure":
                if (isinstance(node.func.value, ast.Name) and
                    node.func.value.id == "structlog"):
                    self.config_calls.append((node.lineno, "structlog.configure", is_guarded))
        
        self.generic_visit(node)
    
    def _is_config_guarded(self, node):
        """Check if config call is guarded (inside function or if __name__ == '__main__')."""
        # Walk up the AST to find if we're inside a function/class or if __name__ == "__main__"
        parent = getattr(node, 'parent', None)
        in_function = False
        in_class = False
        in_if_main = False
        
        # Simple heuristic: check if line is indented
        line_no = node.lineno - 1  # Convert to 0-indexed
        if line_no >= len(self.lines):
            return False
        
        line = self.lines[line_no]
        is_indented = line.strip() and (line.startswith(' ') or line.startswith('\t'))
        
        # Check if we're in an if __name__ == "__main__" block
        # Look backwards for if __name__ == "__main__"
        for i in range(max(0, line_no - 20), line_no):
            check_line = self.lines[i].strip()
            if 'if __name__' in check_line and '__main__' in check_line:
                in_if_main = True
                break
        
        # If indented, likely inside function/class (guarded)
        # If not indented but in if __name__ == "__main__", also guarded
        # Otherwise, it's at module level (import-time, not guarded)
        return is_indented or in_if_main
    
    def visit_ExceptHandler(self, node):
        """Track bare except blocks."""
        if node.type is None:  # Bare except:
            self.bare_except_blocks.append(node.lineno)
        self.generic_visit(node)
    
    def _extract_error_template(self, node):
        """Extract error message template from a logging call node. Returns (template, kind) where kind is 'static', 'dynamic', or 'unknown'."""
        # Check for msg= keyword argument first
        msg_expr = None
        for kw in node.keywords:
            if kw.arg == "msg":
                msg_expr = kw.value
                break
        
        # Use msg= if present, otherwise first positional arg
        if msg_expr is not None:
            first_arg = msg_expr
        elif node.args:
            first_arg = node.args[0]
        else:
            return ("<unknown>", "unknown")
        
        # String literal (Python 2.7: use ast.Str)
        # This covers printf-style: logger.error("Failed %s", x) -> template = "Failed %s"
        if isinstance(first_arg, ast.Str):
            template = first_arg.s
            kind = "static"
        # Translation wrapper: _("msg") or gettext("msg") or ugettext("msg")
        # Also handle nested: _("%s" % x) -> dynamic
        elif isinstance(first_arg, ast.Call) and isinstance(first_arg.func, ast.Name):
            if first_arg.func.id in ("_", "gettext", "ugettext") and first_arg.args:
                # Check if first arg is a string literal
                if isinstance(first_arg.args[0], ast.Str):
                    template = first_arg.args[0].s
                    kind = "static"
                # Check if it's a % formatting: _("%s" % x)
                elif isinstance(first_arg.args[0], ast.BinOp) and isinstance(first_arg.args[0].op, ast.Mod):
                    if isinstance(first_arg.args[0].left, ast.Str):
                        template = first_arg.args[0].left.s
                        kind = "dynamic"  # Has dynamic part (% x)
                    else:
                        return ("<dynamic>", "dynamic")
                else:
                    return ("<dynamic>", "dynamic")
            else:
                return ("<dynamic>", "dynamic")
        # % formatting: "x %s" % value -> template = "x %s"
        elif isinstance(first_arg, ast.BinOp) and isinstance(first_arg.op, ast.Mod):
            if isinstance(first_arg.left, ast.Str):
                template = first_arg.left.s
                kind = "static"
            else:
                return ("<dynamic>", "dynamic")
        # .format() calls: "x {}".format(value) -> template = "x {}"
        elif isinstance(first_arg, ast.Call) and isinstance(first_arg.func, ast.Attribute):
            if first_arg.func.attr == "format" and isinstance(first_arg.func.value, ast.Str):
                template = first_arg.func.value.s
                kind = "static"
            else:
                return ("<dynamic>", "dynamic")
        # Variable reference: logger.error(msg) -> "<var:msg>"
        elif isinstance(first_arg, ast.Name):
            template = "<var:{}>".format(first_arg.id)
            kind = "dynamic"
        # Attribute reference: logger.error(self.msg) -> "<attr:self.msg>"
        elif isinstance(first_arg, ast.Attribute):
            attr_str = self._stringify_attribute_chain(first_arg)
            template = "<attr:{}>".format(attr_str) if attr_str else "<dynamic>"
            kind = "dynamic"
        # String concatenation (BinOp with Add)
        elif isinstance(first_arg, ast.BinOp) and isinstance(first_arg.op, ast.Add):
            # Try to extract literals, but mark as dynamic if complex
            try:
                parts = []
                has_non_literal = self._extract_string_parts(first_arg, parts)
                if parts and not has_non_literal:
                    template = "".join(parts)
                    kind = "static"
                elif parts:
                    # Mixed literals and non-literals -> normalize to {} placeholders
                    template = "{}".join(parts) if len(parts) > 1 else "{}"
                    kind = "dynamic"
                else:
                    return ("<dynamic>", "dynamic")
            except:
                return ("<dynamic>", "dynamic")
        else:
            # No extractable template
            return ("<unknown>", "unknown")
        
        # Normalize whitespace (collapse runs of spaces)
        template = re.sub(r'\s+', ' ', template.strip())
        return (template, kind)
    
    def _extract_string_parts(self, node, parts):
        """Helper to extract string parts from string concatenation. Returns True if non-literal parts found."""
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            has_non_literal_left = self._extract_string_parts(node.left, parts)
            has_non_literal_right = self._extract_string_parts(node.right, parts)
            return has_non_literal_left or has_non_literal_right
        elif isinstance(node, ast.Str):
            parts.append(node.s)
            return False
        else:
            # Non-literal part found
            parts.append("{}")
            return True
    
    def _stringify_attribute_chain(self, node):
        """Convert attribute chain to string (e.g., self.foo._log -> 'self.foo._log')."""
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.insert(0, current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.insert(0, current.id)
            return ".".join(parts)
        return None
    
    def check_json_formatting(self):
        """Check for JSON formatting indicators in config locations and file content."""
        json_indicators = [
            "JSONFormatter", "pythonjsonlogger", "jsonlogger", 
            "JSONRenderer", "orjson", "JSONRenderer"
        ]
        
        # Check config call lines and surrounding context (10 lines before/after)
        for config_tuple in self.config_calls:
            line_no = config_tuple[0]  # (line_no, config_type, is_guarded)
            start_line = max(0, line_no - 11)  # 10 lines before (0-indexed)
            end_line = min(len(self.lines), line_no + 10)  # 10 lines after
            
            for i in range(start_line, end_line):
                if i < len(self.lines):
                    line = self.lines[i]
                    for indicator in json_indicators:
                        if indicator.lower() in line.lower():
                            self.json_formatting_indicators.append(indicator)
                            break
        
        # Also check entire file for structlog JSONRenderer in processors
        if self.has_structlog:
            file_content_lower = self.file_content.lower()
            # Check for JSONRenderer in structlog.configure or processor lists
            if "jsonrenderer" in file_content_lower or "json_renderer" in file_content_lower:
                # Look for structlog.configure or processor assignments
                if "structlog.configure" in self.file_content or "processors" in file_content_lower:
                    if "JSONRenderer" not in self.json_formatting_indicators:
                        self.json_formatting_indicators.append("JSONRenderer")
        
        # Check for pythonjsonlogger / JSONFormatter imports
        if "JSONFormatter" in self.file_content or "pythonjsonlogger" in self.file_content.lower():
            if "JSONFormatter" not in self.json_formatting_indicators:
                self.json_formatting_indicators.append("JSONFormatter")


class RepoScanner:
    """Scans repository for logging patterns and code metrics."""
    
    def __init__(self, root, ignore_dirs=None, include_cache_metrics=False):
        self.root = os.path.abspath(os.path.realpath(root))
        self.ignore_dirs = ignore_dirs or DEFAULT_IGNORE_DIRS
        self.include_cache_metrics = include_cache_metrics
        # Scan coverage tracking
        self.scan_coverage = {
            "python_files_discovered": 0,
            "python_files_scanned": 0,
            "python_files_scanned_ast": 0,  # Files successfully parsed with AST
            "python_files_scanned_regex": 0,  # Files scanned with regex fallback
            "python_files_skipped": {
                "test_file": [],  # Test files (test_*.py, *_test.py, in test dirs)
                "self_file": [],  # Scanner script itself
                "ignored_path": [],  # Other ignored paths
                "decode_error": [],
                "read_error": [],
                "parse_error": []
            }
        }
        self.logging_stats = {
            "stdlib_logging": {"imports": 0, "get_logger": 0, "calls": defaultdict(int)},
            "structlog": {"imports": 0, "get_logger": 0, "calls": defaultdict(int)},
            "framework_logging": {"calls": defaultdict(int)},  # Framework logger calls
            "generic_logging": {"calls": defaultdict(int)},
            "loguru": {"imports": 0, "get_logger": 0, "calls": defaultdict(int)},
            "print_calls": 0,
            "print_calls_in_scripts": 0,
            "print_calls_outside_scripts": 0,
        }
        self.total_lines = 0
        self.non_empty_lines = 0
        self.file_logging_counts = defaultdict(int)
        self.file_print_counts = defaultdict(int)
        self.file_has_both_print_and_logger = []  # Files with both print() and logger calls
        self.level_counts = Counter()
        self.logging_configs = []
        
        # Exception/stack trace tracking
        self.exception_stats = {
            "exception_calls": 0,  # logger.exception()
            "exc_info_calls": 0,  # logger.error(..., exc_info=True)
            "traceback_calls": 0,  # traceback.print_exc / format_exc
            "bare_except_blocks": [],  # List of (file, line_no)
        }
        
        # Unknown logger variable tracking
        self.unknown_logger_vars = defaultdict(int)  # var_name -> total_call_count
        self.unknown_logger_var_files = defaultdict(set)  # var_name -> set of files
        
        # Error template tracking (production only)
        self.error_templates = []  # List of (template, kind, level, file_path, line_no)
        self.error_template_counts = Counter()  # template -> count
        self.error_template_files = defaultdict(set)  # template -> set of files
        
        # Cache metrics (optional)
        self.cache_metrics = {
            "pycache_dirs": 0,
            "pyc_total": 0,
            "pyc_outside_pycache": 0,
        }
        
        self.scan_timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        
    def should_ignore_for_content_scan(self, path):
        """Check if path should be ignored for content scanning (not counting)."""
        # Convert to relative path and split
        try:
            rel_path = os.path.relpath(path, self.root)
        except ValueError:
            # Paths on different drives (Windows)
            return True
        parts = rel_path.replace("\\", "/").split("/")
        for part in parts:
            if part in self.ignore_dirs:
                return True
        return False
    
    def is_test_file(self, filepath):
        """Check if file is a test file (always exclude from production audit)."""
        try:
            rel_path = os.path.relpath(filepath, self.root)
        except ValueError:
            return False
        rel_path_lower = rel_path.lower()
        filename = os.path.basename(filepath).lower()
        # Split path into parts
        path_parts = [p.lower() for p in rel_path.replace("\\", "/").split("/") if p]
        
        # Check for test directories and non-production dirs (exact matches in path parts)
        test_dir_patterns = {"tests", "test", "__tests__", "fixtures", "testdata", "sample_repo", 
                             "test_rigs", "rigs", "fixture"}
        if any(part in test_dir_patterns for part in path_parts):
            return True
        
        # Check for test file patterns (case-insensitive, more robust)
        # test_*.py pattern
        if filename.startswith("test_") and filename.endswith(".py"):
            return True
        # *_test.py pattern
        if filename.endswith("_test.py"):
            return True
        # test*.py pattern (catches testLoggingCompatibility.py, etc.)
        if fnmatch.fnmatch(filename, "test*.py"):
            return True
        
        # Check for fixture/fixtures in path
        if "fixture" in rel_path_lower:
            return True
        
        return False
    
    def is_self_file(self, filepath):
        """Check if file is the scanner itself (always exclude)."""
        try:
            rel_path = os.path.relpath(filepath, self.root)
        except ValueError:
            return False
        normalized = rel_path.replace("\\", "/")
        filename = os.path.basename(filepath)
        # Exclude the scanner script itself
        return normalized == "tools/dev/repo_scan.py" or filename == "repo_scan.py" or filename == "temp.py"
    
    def analyze_python_file(self, filepath, content):
        """Analyze a Python file using AST. Defensive check: should never be called for excluded files."""
        try:
            rel_path = os.path.relpath(filepath, self.root)
        except ValueError:
            rel_path = filepath
        
        # Defensive check: ensure this file should be analyzed (should never trigger if exclusion works)
        if self.is_self_file(filepath) or self.is_test_file(filepath) or self.should_ignore_for_content_scan(filepath):
            # This should never happen, but if it does, return zero counts
            return {
                "path": rel_path,
                "logging_calls": 0,
                "print_calls": 0,
                "total_lines": 0,
                "non_empty_lines": 0,
                "error": "excluded_file"
            }
        
        # Count LOC (total lines and non-empty lines)
        total_lines = len(content.splitlines())
        non_empty_lines = sum(1 for line in content.splitlines() if line.strip())
        
        try:
            tree = ast.parse(content, filename=filepath)
        except (SyntaxError, ValueError) as e:
            # Try regex fallback for parse errors (Python 3 syntax in Python 2.7 environment)
            return self._analyze_with_regex_fallback(filepath, content, rel_path, total_lines, non_empty_lines)
        
        visitor = LoggingASTVisitor(content, rel_path)
        visitor.visit(tree)
        visitor.check_json_formatting()
        
        # Mark as AST-scanned
        self.scan_coverage["python_files_scanned_ast"] += 1
        
        # Aggregate counts (including framework calls)
        total_logging_calls = (
            sum(visitor.stdlib_calls.values()) +
            sum(visitor.structlog_calls.values()) +
            sum(visitor.framework_calls.values()) +
            sum(visitor.generic_calls.values())
        )
        
        # Update global stats
        self.logging_stats["stdlib_logging"]["imports"] += visitor.stdlib_imports
        self.logging_stats["structlog"]["imports"] += visitor.structlog_imports
        self.logging_stats["loguru"]["imports"] += visitor.loguru_imports
        self.logging_stats["stdlib_logging"]["get_logger"] += visitor.stdlib_getlogger_calls
        self.logging_stats["structlog"]["get_logger"] += visitor.structlog_getlogger_calls
        self.logging_stats["print_calls"] += visitor.print_calls
        self.logging_stats["print_calls_in_scripts"] = self.logging_stats.get("print_calls_in_scripts", 0) + visitor.print_calls_in_scripts
        self.logging_stats["print_calls_outside_scripts"] = self.logging_stats.get("print_calls_outside_scripts", 0) + visitor.print_calls_outside_scripts
        
        # Count calls by level
        for level, count in visitor.stdlib_calls.items():
            self.logging_stats["stdlib_logging"]["calls"][level] += count
            self.level_counts[level] += count
        
        for level, count in visitor.structlog_calls.items():
            self.logging_stats["structlog"]["calls"][level] += count
            self.level_counts[level] += count
        
        for level, count in visitor.framework_calls.items():
            self.logging_stats["framework_logging"]["calls"][level] += count
            self.level_counts[level] += count
        
        for level, count in visitor.generic_calls.items():
            self.logging_stats["generic_logging"]["calls"][level] += count
            self.level_counts[level] += count
        
        # Track exception/stack trace stats
        self.exception_stats["exception_calls"] += visitor.exception_calls
        self.exception_stats["exc_info_calls"] += visitor.exc_info_calls
        self.exception_stats["traceback_calls"] += visitor.traceback_calls
        for line_no in visitor.bare_except_blocks:
            self.exception_stats["bare_except_blocks"].append((rel_path, line_no))
        
        # Track error templates (production only)
        # Format: (template, kind, level, line_no) where kind is 'static', 'dynamic', or 'unknown'
        for template, kind, level, line_no in visitor.error_templates:
            self.error_templates.append((template, kind, level, rel_path, line_no))
            # Only count static templates in unique template counts
            if kind == "static" and template not in ("<dynamic>", "<unknown>"):
                self.error_template_counts[template] += 1
                self.error_template_files[template].add(rel_path)
        
        # Track unknown logger variables
        for var_name, count in visitor.unknown_logger_vars.items():
            self.unknown_logger_vars[var_name] += count
            self.unknown_logger_var_files[var_name].add(rel_path)
        
        # Track per-file counts
        if total_logging_calls > 0:
            self.file_logging_counts[rel_path] = total_logging_calls
        if visitor.print_calls > 0:
            self.file_print_counts[rel_path] = visitor.print_calls
        
        # Config detection (now includes is_guarded)
        file_has_json_formatting = bool(visitor.json_formatting_indicators)
        for config_tuple in visitor.config_calls:
            line_no, config_type, is_guarded = config_tuple
            cfg_entry = {
                "file": rel_path,
                "line": line_no,
                "config_type": config_type,
                "is_guarded": is_guarded,
                "entry_point_likelihood": "guarded" if is_guarded else "import-time"
            }
            if file_has_json_formatting:
                cfg_entry["has_json_formatting"] = True
            self.logging_configs.append(cfg_entry)
        
        return {
            "path": rel_path,
            "logging_calls": total_logging_calls,
            "print_calls": visitor.print_calls,
            "total_lines": total_lines,
            "non_empty_lines": non_empty_lines
        }
    
    def _analyze_with_regex_fallback(self, filepath, content, rel_path, total_lines, non_empty_lines):
        """Regex-based fallback for files that fail to parse with AST (Python 3 syntax in Py2.7)."""
        # Mark as regex-scanned
        self.scan_coverage["python_files_scanned_regex"] += 1
        
        # Regex patterns for logger calls (include warn/fatal aliases)
        logger_pattern = re.compile(r'\b([A-Za-z_][A-Za-z0-9_\.]*?)\.(debug|info|warning|warn|error|critical|fatal|exception)\s*\(')
        print_pattern = re.compile(r'\bprint\s*\(')
        
        logging_calls = 0
        print_calls = 0
        error_templates_found = []
        
        lines = content.splitlines()
        for line_num, line in enumerate(lines, 1):
            # Count print calls (regex fallback only - AST handles separately)
            # Count print() function calls
            print_matches = print_pattern.findall(line)
            print_calls += len(print_matches)
            # Count Python 2 print statements: print "x" or print >>f, "x"
            # Pattern: print followed by optional >>target, then string literal
            # Only count if not already matched as print()
            if not print_matches and re.search(r'\bprint\s+(>>\s*\w+\s*,\s*)?["\']', line):
                print_calls += 1
            
            # Find logger calls
            for match in logger_pattern.finditer(line):
                logger_base, level = match.groups()
                logging_calls += 1
                
                # Normalize aliases: warn -> warning, fatal -> critical
                if level == "warn":
                    level = "warning"
                elif level == "fatal":
                    level = "critical"
                
                # Extract error templates for error-like calls
                if level in ("error", "exception", "critical"):
                    # Try to extract first string literal from the call
                    call_start = match.end()
                    paren_content = self._extract_call_content(line[call_start:])
                    if paren_content:
                        template = self._extract_template_from_string(paren_content)
                        if template:
                            error_templates_found.append((template, level, line_num))
        
        # Update global stats (classify as unknown/generic)
        # Normalize aliases: warn -> warning, fatal -> critical
        level_counts = defaultdict(int)
        for match in logger_pattern.finditer(content):
            _, level = match.groups()
            if level == "warn":
                level = "warning"
            elif level == "fatal":
                level = "critical"
            if level == "exception":
                level_counts["exception"] += 1
            else:
                level_counts[level] += 1
        
        for level, count in level_counts.items():
            self.logging_stats["generic_logging"]["calls"][level] += count
            self.level_counts[level] += count
        
        # Track error templates (format: template, kind, level, file_path, line_no)
        for template, level, line_no in error_templates_found:
            # Regex fallback returns simple template string, treat as dynamic
            self.error_templates.append((template, "dynamic", level, rel_path, line_no))
            # Don't count regex-extracted templates as static
        
        # Update print counts (check script-like markers)
        self.logging_stats["print_calls"] += print_calls
        file_path_lower = rel_path.lower()
        is_script = any(marker in file_path_lower for marker in SCRIPT_PATH_MARKERS)
        if is_script:
            self.logging_stats["print_calls_in_scripts"] += print_calls
        else:
            self.logging_stats["print_calls_outside_scripts"] += print_calls
        
        # Track per-file counts
        if logging_calls > 0:
            self.file_logging_counts[rel_path] = logging_calls
        if print_calls > 0:
            self.file_print_counts[rel_path] = print_calls
        
        return {
            "path": rel_path,
            "logging_calls": logging_calls,
            "print_calls": print_calls,
            "total_lines": total_lines,
            "non_empty_lines": non_empty_lines,
            "error": "regex_fallback"
        }
    
    def _extract_call_content(self, text):
        """Extract content inside first function call parentheses."""
        depth = 0
        start = -1
        for i, char in enumerate(text):
            if char == '(':
                if depth == 0:
                    start = i + 1
                depth += 1
            elif char == ')':
                depth -= 1
                if depth == 0 and start >= 0:
                    return text[start:i].strip()
        return ""
    
    def _extract_template_from_string(self, content):
        """Extract template from string content (handles quotes, %, .format, f-strings)."""
        # Remove leading/trailing whitespace
        content = content.strip()
        
        # Try to find first string literal (single or double quotes)
        # Pattern: "..." or '...' possibly with f/F prefix
        string_pattern = re.compile(r'[fF]?["\']([^"\']*)["\']')
        match = string_pattern.match(content)
        if match:
            template = match.group(1)
            # Normalize f-string placeholders {expr} to <expr>
            template = re.sub(r'\{[^}]*\}', '<expr>', template)
            return template
        
        # Try % formatting: "msg %s" % value
        mod_pattern = re.compile(r'["\']([^"\']*)["\']\s*%')
        match = mod_pattern.match(content)
        if match:
            return match.group(1)
        
        # Try .format(): "msg {}".format(...)
        format_pattern = re.compile(r'["\']([^"\']*)["\']\s*\.format\s*\(')
        match = format_pattern.match(content)
        if match:
            return match.group(1)
        
        return "<unknown>"
    
    def scan(self):
        """Perform the full repository scan."""
        if not os.path.exists(self.root):
            raise ValueError("Root directory does not exist: {}".format(self.root))
        
        # Walk the directory tree
        for root_dir, dirs, files in os.walk(self.root):
            # Track cache metrics if enabled
            if self.include_cache_metrics:
                if "__pycache__" in dirs:
                    self.cache_metrics["pycache_dirs"] += 1
                for filename in files:
                    if filename.endswith(".pyc"):
                        self.cache_metrics["pyc_total"] += 1
                        # Check if it's outside __pycache__
                        if "__pycache__" not in root_dir:
                            self.cache_metrics["pyc_outside_pycache"] += 1
            
            # Skip __pycache__ directories entirely for content scanning
            if "__pycache__" in dirs:
                dirs[:] = [d for d in dirs if d != "__pycache__"]
            
            # Filter out ignored directories for content scanning
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs and not self.should_ignore_for_content_scan(os.path.join(root_dir, d))]
            
            # Scan Python files for content
            for filename in files:
                if filename.endswith(".py"):
                    filepath = os.path.join(root_dir, filename)
                    try:
                        rel_path = os.path.relpath(filepath, self.root)
                    except ValueError:
                        rel_path = filepath
                    
                    # Count all discovered Python files
                    self.scan_coverage["python_files_discovered"] += 1
                    
                    # Determine skip reason (single gate - files are excluded BEFORE analysis)
                    skip_reason = None
                    if self.is_self_file(filepath):
                        skip_reason = "self_file"
                    elif self.is_test_file(filepath):
                        skip_reason = "test_file"
                    elif self.should_ignore_for_content_scan(filepath):
                        skip_reason = "ignored_path"
                    
                    # Skip excluded files BEFORE reading/parsing/analyzing
                    if skip_reason:
                        self.scan_coverage["python_files_skipped"][skip_reason].append(rel_path)
                        continue
                    
                    # Read and analyze
                    try:
                        with open(filepath, 'rb') as f:
                            content = f.read().decode('utf-8', errors='replace')
                    except UnicodeDecodeError as e:
                        self.scan_coverage["python_files_skipped"]["decode_error"].append(rel_path)
                        continue
                    except Exception as e:
                        self.scan_coverage["python_files_skipped"]["read_error"].append(rel_path)
                        continue
                    
                    self.scan_coverage["python_files_scanned"] += 1
                    
                    # Analyze with AST
                    result = self.analyze_python_file(filepath, content)
                    
                    # Track LOC
                    if "total_lines" in result:
                        self.total_lines += result["total_lines"]
                    if "non_empty_lines" in result:
                        self.non_empty_lines += result["non_empty_lines"]
                    
                    # Track files with both print() and logger calls
                    if result["print_calls"] > 0 and result["logging_calls"] > 0:
                        self.file_has_both_print_and_logger.append({
                            "file": rel_path,
                            "print_calls": result["print_calls"],
                            "logging_calls": result["logging_calls"]
                        })
    
    def _build_unknown_logger_vars_data(self):
        """Build unknown logger vars data with correct example files mapping."""
        # Get top vars by call count
        top_vars = sorted(self.unknown_logger_vars.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Build var_files mapping for top vars only
        var_files = {}
        for var_name, _ in top_vars:
            files = sorted(list(self.unknown_logger_var_files.get(var_name, set())))
            var_files[var_name] = files[:5]
        
        return {
            "top_vars": top_vars,
            "var_files": var_files
        }
    
    def get_report_data(self):
        """Get structured report data."""
        # Get top files
        top_logging_files = sorted(self.file_logging_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        top_print_files = sorted(self.file_print_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Check for JSON formatting in configs
        json_configs = [cfg for cfg in self.logging_configs if cfg.get("has_json_formatting", False)]
        has_json_formatting = len(json_configs) > 0
        
        # Actionable findings
        basic_config_count = sum(1 for cfg in self.logging_configs if cfg["config_type"] == "basicConfig")
        multiple_basic_config = basic_config_count > 1
        
        # High print() counts outside scripts/ directory (threshold: 10+)
        high_print_files = []
        for file_path, count in self.file_print_counts.items():
            if count >= 10 and "scripts" not in file_path.lower():
                high_print_files.append({"file": file_path, "count": count})
        high_print_files.sort(key=lambda x: x["count"], reverse=True)
        
        # Files with both print() and logger calls
        files_with_both = sorted(self.file_has_both_print_and_logger, 
                                key=lambda x: x["print_calls"] + x["logging_calls"], 
                                reverse=True)
        
        # High unknown logger usage
        total_generic_calls = sum(self.logging_stats["generic_logging"]["calls"].values())
        total_all_calls = (
            sum(self.logging_stats["stdlib_logging"]["calls"].values()) +
            sum(self.logging_stats["structlog"]["calls"].values()) +
            total_generic_calls
        )
        high_unknown_usage = total_all_calls > 0 and (total_generic_calls / total_all_calls) > 0.1  # >10% unknown
        
        # Internal consistency validation: level distribution must equal total logger calls
        level_sum = sum(self.level_counts.values())
        consistency_check = {
            "level_sum": level_sum,
            "total_calls": total_all_calls,
            "matches": level_sum == total_all_calls,
            "difference": level_sum - total_all_calls
        }
        
        # Error template statistics (format: template, kind, level, file_path, line_no)
        dynamic_template_count = sum(1 for _, kind, _, _, _ in self.error_templates if kind == "dynamic")
        unknown_template_count = sum(1 for _, kind, _, _, _ in self.error_templates if kind == "unknown")
        total_error_calls = (
            self.level_counts.get("error", 0) +
            self.level_counts.get("exception", 0) +
            self.level_counts.get("critical", 0)
        )
        high_dynamic_errors = total_error_calls > 0 and (dynamic_template_count / total_error_calls) > 0.3  # >30% dynamic
        
        return {
            "meta": {
                "repo_path": str(self.root),
                "scan_timestamp": self.scan_timestamp,
                "exclusions": sorted(self.ignore_dirs),
                "total_lines": self.total_lines,
                "non_empty_lines": self.non_empty_lines
            },
            "scan_coverage": {
                "python_files_discovered": self.scan_coverage["python_files_discovered"],
                "python_files_scanned": self.scan_coverage["python_files_scanned"],
                "python_files_scanned_ast": self.scan_coverage.get("python_files_scanned_ast", 0),
                "python_files_scanned_regex": self.scan_coverage.get("python_files_scanned_regex", 0),
                "python_files_skipped": {
                    "test_file": len(self.scan_coverage["python_files_skipped"]["test_file"]),
                    "self_file": len(self.scan_coverage["python_files_skipped"]["self_file"]),
                    "ignored_path": len(self.scan_coverage["python_files_skipped"]["ignored_path"]),
                    "decode_error": len(self.scan_coverage["python_files_skipped"]["decode_error"]),
                    "read_error": len(self.scan_coverage["python_files_skipped"]["read_error"]),
                    "parse_error": len(self.scan_coverage["python_files_skipped"]["parse_error"])
                },
                "skipped_files_detail": {
                    "test_file": self.scan_coverage["python_files_skipped"]["test_file"][:20],
                    "self_file": self.scan_coverage["python_files_skipped"]["self_file"][:20],
                    "ignored_path": self.scan_coverage["python_files_skipped"]["ignored_path"][:20],
                    "decode_error": self.scan_coverage["python_files_skipped"]["decode_error"][:20],
                    "read_error": self.scan_coverage["python_files_skipped"]["read_error"][:20],
                    "parse_error": self.scan_coverage["python_files_skipped"]["parse_error"][:20]
                }
            },
            "logging_usage": {
                "stdlib_logging": {
                    "imports": self.logging_stats["stdlib_logging"]["imports"],
                    "get_logger_calls": self.logging_stats["stdlib_logging"]["get_logger"],
                    "method_calls": dict(self.logging_stats["stdlib_logging"]["calls"])
                },
                "structlog": {
                    "imports": self.logging_stats["structlog"]["imports"],
                    "get_logger_calls": self.logging_stats["structlog"]["get_logger"],
                    "method_calls": dict(self.logging_stats["structlog"]["calls"])
                },
                "framework_logging": {
                    "method_calls": dict(self.logging_stats["framework_logging"]["calls"])
                },
                "loguru": {
                    "imports": self.logging_stats["loguru"]["imports"],
                    "get_logger_calls": self.logging_stats["loguru"]["get_logger"],
                    "method_calls": dict(self.logging_stats["loguru"]["calls"])
                },
                "generic_logging": {
                    "method_calls": dict(self.logging_stats["generic_logging"]["calls"])
                },
                "print_calls": self.logging_stats["print_calls"],
                "print_calls_in_scripts": self.logging_stats.get("print_calls_in_scripts", 0),
                "print_calls_outside_scripts": self.logging_stats.get("print_calls_outside_scripts", 0),
                "top_logging_files": [{"file": f, "count": c} for f, c in top_logging_files],
                "top_print_files": [{"file": f, "count": c} for f, c in top_print_files]
            },
            "log_levels": dict(self.level_counts),
            "logging_config": {
                "config_locations": self.logging_configs,
                "has_json_formatting": has_json_formatting,
                "json_config_locations": json_configs
            },
            "exceptions": {
                "exception_calls": self.exception_stats["exception_calls"],
                "exc_info_calls": self.exception_stats["exc_info_calls"],
                "traceback_calls": self.exception_stats["traceback_calls"],
                "bare_except_blocks": self.exception_stats["bare_except_blocks"][:20]  # Top 20
            },
            "error_logging": {
                "total_error_calls": (
                    self.level_counts.get("error", 0) +
                    self.level_counts.get("exception", 0) +
                    self.level_counts.get("critical", 0)
                ),
                "error_calls": self.level_counts.get("error", 0),
                "exception_calls": self.level_counts.get("exception", 0),
                "critical_calls": self.level_counts.get("critical", 0),
                "error_with_exc_info": self.exception_stats["exc_info_calls"],
                "unique_templates": len(self.error_template_counts),
                "dynamic_templates": sum(1 for _, kind, _, _, _ in self.error_templates if kind == "dynamic"),
                "unknown_templates": sum(1 for _, kind, _, _, _ in self.error_templates if kind == "unknown"),
                "top_templates": [
                    {
                        "template": template,
                        "count": count,
                        "example_files": list(self.error_template_files[template])[:3]
                    }
                    for template, count in self.error_template_counts.most_common(20)
                ]
            },
            "_error_details": self.error_templates,  # Internal: full error details for top files calculation
            "unknown_logger_vars": self._build_unknown_logger_vars_data(),
            "actionable_findings": {
                "multiple_basic_config": multiple_basic_config,
                "basic_config_count": basic_config_count,
                "basic_config_locations": [cfg for cfg in self.logging_configs if cfg["config_type"] == "basicConfig"],
                "high_print_counts_outside_scripts": [f for f in high_print_files if "tests" not in f["file"].lower()][:20],
                "files_with_both_print_and_logger": files_with_both[:20],
                "json_logging_enabled": has_json_formatting,
                "json_logging_locations": json_configs,
                "structlog_configured_but_unused": (
                    self.logging_stats["structlog"]["get_logger"] > 0 and
                    sum(self.logging_stats["structlog"]["calls"].values()) == 0 and
                    any(cfg["config_type"] == "structlog.configure" for cfg in self.logging_configs)
                ),
                "high_unknown_logger_usage": high_unknown_usage,
                "unknown_logger_percentage": (total_generic_calls / total_all_calls * 100) if total_all_calls > 0 else 0,
                "high_dynamic_error_templates": high_dynamic_errors,
                "dynamic_error_percentage": (dynamic_template_count / total_error_calls * 100) if total_error_calls > 0 else 0,
                "unknown_error_percentage": (unknown_template_count / total_error_calls * 100) if total_error_calls > 0 else 0
            },
            "_consistency_check": consistency_check  # Internal validation
        }
        
        # Add cache metrics if enabled
        if self.include_cache_metrics:
            data["cache_metrics"] = self.cache_metrics
        
        return data
    
    def format_markdown(self, data):
        """Format report data as Markdown."""
        lines = []
        
        # Header
        lines.append("# Logging Audit Report")
        lines.append("")
        lines.append("**Repo Path:** `{}`".format(data['meta']['repo_path']))
        lines.append("**Scan Timestamp:** {}".format(data['meta']['scan_timestamp']))
        lines.append("")
        
        # LOC reporting
        if "total_lines" in data["meta"]:
            lines.append("**Total Lines (Physical):** " + str(data["meta"]["total_lines"]))
            lines.append("**Non-Empty Lines:** " + str(data["meta"]["non_empty_lines"]))
            lines.append("")
        
        # Production Scope / Exclusions summary
        lines.append("## Production Scope / Exclusions")
        lines.append("")
        lines.append("This audit scans **production code only**. The following are excluded:")
        lines.append("")
        lines.append("- Test files: `test_*.py`, `*_test.py`")
        lines.append("- Test directories: `tests/`, `test/`, `__tests__/`, `fixtures/`, `testdata/`, `sample_repo/`")
        lines.append("- Scanner script itself: `tools/dev/repo_scan.py`")
        lines.append("")
        skipped_count = (
            data["scan_coverage"]["python_files_skipped"].get("test_file", 0) +
            data["scan_coverage"]["python_files_skipped"].get("self_file", 0) +
            data["scan_coverage"]["python_files_skipped"].get("ignored_path", 0)
        )
        if skipped_count > 0:
            lines.append("**Total files excluded:** {}".format(skipped_count))
            lines.append("")
        
        # Scan Coverage
        coverage = data["scan_coverage"]
        lines.append("## Scan Coverage")
        lines.append("")
        lines.append("| Metric | Count |")
        lines.append("|--------|-------|")
        lines.append("| Python files discovered | {} |".format(coverage['python_files_discovered']))
        lines.append("| Python files successfully scanned | {} |".format(coverage['python_files_scanned']))
        if coverage.get('python_files_scanned_ast', 0) > 0 or coverage.get('python_files_scanned_regex', 0) > 0:
            lines.append("|   - Scanned with AST | {} |".format(coverage.get('python_files_scanned_ast', 0)))
            lines.append("|   - Scanned with regex fallback | {} |".format(coverage.get('python_files_scanned_regex', 0)))
        lines.append("| Python files skipped (test files) | {} |".format(coverage['python_files_skipped'].get('test_file', 0)))
        lines.append("| Python files skipped (scanner script) | {} |".format(coverage['python_files_skipped'].get('self_file', 0)))
        lines.append("| Python files skipped (ignored path) | {} |".format(coverage['python_files_skipped'].get('ignored_path', 0)))
        lines.append("| Python files skipped (decode error) | {} |".format(coverage['python_files_skipped'].get('decode_error', 0)))
        lines.append("| Python files skipped (read error) | {} |".format(coverage['python_files_skipped'].get('read_error', 0)))
        lines.append("| Python files skipped (parse error) | {} |".format(coverage['python_files_skipped'].get('parse_error', 0)))
        lines.append("")
        
        # Show ignored directories
        exclusions = data['meta']['exclusions']
        if exclusions:
            lines.append("**Ignored directories:** {}{}".format(', '.join(exclusions[:20]), '...' if len(exclusions) > 20 else ''))
            lines.append("")
        
        # Show sample skipped files if any
        skipped_detail = coverage["skipped_files_detail"]
        
        # Test files (most important to show)
        if skipped_detail.get("test_file"):
            lines.append("**Sample skipped files (test files):**")
            for f in skipped_detail["test_file"][:10]:
                lines.append("- `{}`".format(f))
            if len(skipped_detail["test_file"]) > 10:
                lines.append("- ... and {} more".format(len(skipped_detail['test_file']) - 10))
            lines.append("")
        
        # Self file
        if skipped_detail.get("self_file"):
            lines.append("**Skipped files (scanner script):**")
            for f in skipped_detail["self_file"]:
                lines.append("- `{}`".format(f))
            lines.append("")
        
        # Other ignored paths
        if skipped_detail.get("ignored_path"):
            lines.append("**Sample skipped files (ignored path):**")
            for f in skipped_detail["ignored_path"][:5]:
                lines.append("- `{}`".format(f))
            if len(skipped_detail["ignored_path"]) > 5:
                lines.append("- ... and {} more".format(len(skipped_detail['ignored_path']) - 5))
            lines.append("")
        
        if skipped_detail["decode_error"]:
            lines.append("**Sample skipped files (decode error):**")
            for f in skipped_detail["decode_error"][:5]:
                lines.append("- `{}`".format(f))
            if len(skipped_detail["decode_error"]) > 5:
                lines.append("- ... and {} more".format(len(skipped_detail['decode_error']) - 5))
            lines.append("")
        
        if skipped_detail["read_error"]:
            lines.append("**Sample skipped files (read error):**")
            for f in skipped_detail["read_error"][:5]:
                lines.append("- `{}`".format(f))
            if len(skipped_detail["read_error"]) > 5:
                lines.append("- ... and {} more".format(len(skipped_detail['read_error']) - 5))
            lines.append("")
        
        if skipped_detail.get("parse_error"):
            lines.append("**Sample skipped files (parse error):**")
            for f in skipped_detail["parse_error"][:5]:
                lines.append("- `{}`".format(f))
            if len(skipped_detail["parse_error"]) > 5:
                lines.append("- ... and {} more".format(len(skipped_detail['parse_error']) - 5))
            lines.append("")
        
        # Logging System Identification
        lines.append("## Logging System Identification")
        lines.append("")
        stdlib_total = sum(data["logging_usage"]["stdlib_logging"]["method_calls"].values())
        structlog_total = sum(data["logging_usage"]["structlog"]["method_calls"].values())
        generic_total = sum(data["logging_usage"]["generic_logging"]["method_calls"].values())
        
        systems_detected = []
        if stdlib_total > 0:
            systems_detected.append("stdlib logging")
        if structlog_total > 0:
            systems_detected.append("structlog")
        if generic_total > 0:
            systems_detected.append("unknown/generic")
        
        if systems_detected:
            lines.append("**Systems detected:** {}".format(', '.join(systems_detected)))
        else:
            lines.append("**Systems detected:** None (no logger calls found in production code)")
        lines.append("")
        lines.append("| System | Total Logger Calls |")
        lines.append("|--------|-------------------|")
        if stdlib_total > 0:
            lines.append("| stdlib logging | {} |".format(stdlib_total))
        if structlog_total > 0:
            lines.append("| structlog | {} |".format(structlog_total))
        if generic_total > 0:
            lines.append("| unknown/generic | {} |".format(generic_total))
        lines.append("")
        
        # Logging Usage Summary
        lines.append("## Logging Usage Summary")
        lines.append("")
        
        # Standard library logging
        stdlib = data["logging_usage"]["stdlib_logging"]
        lines.append("### Standard Library Logging (`logging` module)")
        lines.append("")
        lines.append("| Metric | Count |")
        lines.append("|--------|-------|")
        lines.append("| Imports | {} |".format(stdlib['imports']))
        lines.append("| `getLogger()` calls | {} |".format(stdlib['get_logger_calls']))
        lines.append("| Total method calls | {} |".format(sum(stdlib['method_calls'].values())))
        lines.append("")
        
        # structlog
        structlog_data = data["logging_usage"]["structlog"]
        if structlog_data["imports"] > 0 or sum(structlog_data["method_calls"].values()) > 0:
            lines.append("### structlog")
            lines.append("")
            lines.append("| Metric | Count |")
            lines.append("|--------|-------|")
            lines.append("| Imports | {} |".format(structlog_data['imports']))
            lines.append("| `get_logger()` calls | {} |".format(structlog_data['get_logger_calls']))
            lines.append("| Total method calls | {} |".format(sum(structlog_data['method_calls'].values())))
            lines.append("")
        
        # Framework logger calls
        framework_data = data["logging_usage"]["framework_logging"]
        if sum(framework_data["method_calls"].values()) > 0:
            lines.append("### Framework / Server Logger Usage")
            lines.append("")
            lines.append("| Metric | Count |")
            lines.append("|--------|-------|")
            lines.append("| Total method calls | {} |".format(sum(framework_data['method_calls'].values())))
            lines.append("")
            lines.append("*Note: Framework logger calls (uvicorn, gunicorn, Flask app.logger, FastAPI logger).*")
            lines.append("")
        
        # Generic/Unknown logger calls
        generic_data = data["logging_usage"]["generic_logging"]
        total_generic = sum(generic_data["method_calls"].values())
        if total_generic > 0:
            lines.append("### Generic/Unknown Logger Calls")
            lines.append("")
            lines.append("| Metric | Count |")
            lines.append("|--------|-------|")
            lines.append("| Total method calls | {} |".format(total_generic))
            lines.append("")
            lines.append("*Note: Logger calls where the logger variable source could not be determined.*")
            lines.append("")
        
        # Print statements - split by scripts/
        lines.append("### Print Calls")
        lines.append("")
        lines.append("| Location | Count |")
        lines.append("|----------|-------|")
        lines.append("| In `scripts/` directories | {} |".format(data['logging_usage'].get('print_calls_in_scripts', 0)))
        lines.append("| Outside `scripts/` | {} |".format(data['logging_usage'].get('print_calls_outside_scripts', 0)))
        lines.append("| **Total** | {} |".format(data['logging_usage']['print_calls']))
        lines.append("")
        
        # Production Error Logging Summary (KEY SECTION)
        if "error_logging" in data:
            error_data = data["error_logging"]
            lines.append("## Production Error Logging Summary")
            lines.append("")
            lines.append("**Total Error-Like Calls:** {}".format(error_data['total_error_calls']))
            lines.append("")
            lines.append("### Breakdown by Level")
            lines.append("")
            lines.append("| Level | Count |")
            lines.append("|-------|-------|")
            lines.append("| ERROR | {} |".format(error_data['error_calls']))
            lines.append("| EXCEPTION | {} |".format(error_data['exception_calls']))
            lines.append("| CRITICAL | {} |".format(error_data['critical_calls']))
            lines.append("")
            lines.append("**Error calls with `exc_info=True`:** {}".format(error_data['error_with_exc_info']))
            lines.append("")
            lines.append("### Error Message Templates")
            lines.append("")
            lines.append("- **Unique templates (excluding dynamic/unknown):** {}".format(error_data['unique_templates']))
            lines.append("- **Dynamic templates (f-strings, concatenation, etc.):** {}".format(error_data['dynamic_templates']))
            lines.append("- **Unknown templates (no extractable message):** {}".format(error_data['unknown_templates']))
            lines.append("")
            if error_data["top_templates"]:
                lines.append("### Top 20 Error Templates")
                lines.append("")
                lines.append("| Template | Count | Example Files |")
                lines.append("|----------|-------|---------------|")
                for item in error_data["top_templates"]:
                    examples = ", ".join(["`{}`".format(f) for f in item["example_files"][:3]])
                    if len(item["example_files"]) > 3:
                        examples += " (+{} more)".format(len(item['example_files']) - 3)
                    # Truncate long templates for readability
                    template_display = item["template"][:100] + "..." if len(item["template"]) > 100 else item["template"]
                    lines.append("| `{}` | {} | {} |".format(template_display, item['count'], examples))
                lines.append("")
        
        # Top Offenders
        lines.append("## Top Offenders")
        lines.append("")
        
        # Top files by logging calls
        if data["logging_usage"]["top_logging_files"]:
            lines.append("### Top 10 Files by Total Logger Calls")
            lines.append("")
            lines.append("| File | Calls |")
            lines.append("|------|-------|")
            for item in data["logging_usage"]["top_logging_files"]:
                lines.append("| `{}` | {} |".format(item['file'], item['count']))
            lines.append("")
        
        # Top files by error-like calls
        if "error_logging" in data:
            # Calculate top files by error calls (format: template, kind, level, file_path, line_no)
            file_error_counts = defaultdict(int)
            for template, kind, level, file_path, line_no in data.get("_error_details", []):
                if level in ("error", "exception", "critical"):
                    file_error_counts[file_path] += 1
            top_error_files = sorted(file_error_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            if top_error_files:
                lines.append("### Top 10 Files by Error-Like Logger Calls")
                lines.append("")
                lines.append("| File | Calls |")
                lines.append("|------|-------|")
                for file_path, count in top_error_files:
                    lines.append("| `{}` | {} |".format(file_path, count))
                lines.append("")
        
        # Top files by print calls
        if data["logging_usage"]["top_print_files"]:
            lines.append("### Top 10 Files by Print Calls")
            lines.append("")
            lines.append("| File | Calls |")
            lines.append("|------|-------|")
            for item in data["logging_usage"]["top_print_files"]:
                lines.append("| `{}` | {} |".format(item['file'], item['count']))
            lines.append("")
        
        # Log Level Distribution
        lines.append("## Log Level Distribution")
        lines.append("")
        total_logger_calls = sum(data["log_levels"].values())
        lines.append("| Level | Count |")
        lines.append("|-------|-------|")
        for level in ["debug", "info", "warning", "error", "critical", "exception"]:
            count = data["log_levels"].get(level, 0)
            if count > 0:
                lines.append("| {} | {} |".format(level.upper(), count))
        lines.append("| **Total** | **{}** |".format(total_logger_calls))
        lines.append("")
        lines.append("*Note: Total logger calls = {}. Level distribution sums must match this total.*".format(total_logger_calls))
        lines.append("")
        
        # Internal consistency check
        if "_consistency_check" in data:
            check = data["_consistency_check"]
            if not check["matches"]:
                lines.append("## WARNING: INTERNAL CONSISTENCY CHECK FAILED")
                lines.append("")
                lines.append("**WARNING:** The level distribution total does not match the total logger calls!")
                lines.append("")
                lines.append("- Level distribution sum: **{}**".format(check['level_sum']))
                lines.append("- Total logger calls: **{}**".format(check['total_calls']))
                lines.append("- Difference: **{}**".format(check['difference']))
                lines.append("")
                lines.append("This indicates a counting bug. Some files may be partially counted.")
                lines.append("Please report this issue.")
                lines.append("")
        
        # Additional consistency checks
        if "error_logging" in data:
            error_data = data["error_logging"]
            error_sum = error_data.get("error_calls", 0) + error_data.get("exception_calls", 0) + error_data.get("critical_calls", 0)
            if error_sum != error_data.get("total_error_calls", 0):
                lines.append("## WARNING: CONSISTENCY WARNING")
                lines.append("")
                lines.append("Error-like call breakdown does not match total:")
                lines.append("- ERROR + EXCEPTION + CRITICAL = **{}**".format(error_sum))
                lines.append("- Reported total = **{}**".format(error_data.get("total_error_calls", 0)))
                lines.append("")
        
        lines.append("")
        
        # Logger Configuration
        lines.append("## Logger Configuration Overview")
        lines.append("")
        if data["logging_config"]["config_locations"]:
            lines.append("### Configuration Locations")
            lines.append("")
            lines.append("| File | Line | Type | Entry Point | JSON |")
            lines.append("|------|------|------|-------------|------|")
            for cfg in data["logging_config"]["config_locations"]:
                json_marker = "Yes" if cfg.get("has_json_formatting") else "No"
                entry_point = cfg.get("entry_point_likelihood", "unknown")
                lines.append("| `{}` | {} | {} | {} | {} |".format(cfg['file'], cfg['line'], cfg['config_type'], entry_point, json_marker))
            lines.append("")
            lines.append("*Entry Point: 'import-time' = executed at module import (high risk), 'guarded' = inside function or if __name__ == '__main__' (lower risk)*")
            lines.append("")
        else:
            lines.append("No explicit logging configuration found.")
        lines.append("")
        
        # Exceptions & Stack Traces
        lines.append("## Exceptions & Stack Traces")
        lines.append("")
        exc_data = data["exceptions"]
        lines.append("| Method | Count |")
        lines.append("|--------|-------|")
        lines.append("| `logger.exception()` | {} |".format(exc_data['exception_calls']))
        lines.append("| `logger.error(..., exc_info=True)` | {} |".format(exc_data['exc_info_calls']))
        lines.append("| `traceback.print_exc()` / `traceback.format_exc()` | {} |".format(exc_data['traceback_calls']))
        lines.append("")
        
        if exc_data["bare_except_blocks"]:
            lines.append("### Bare `except:` Blocks")
            lines.append("")
            lines.append("| File | Line |")
            lines.append("|------|------|")
            for file_path, line_no in exc_data["bare_except_blocks"]:
                lines.append("| `{}` | {} |".format(file_path, line_no))
            lines.append("")
            lines.append("*Note: Bare except blocks may hide exceptions. Consider using `except Exception:` or specific exception types.*")
            lines.append("")
        
        # Actionable Findings
        lines.append("## Actionable Findings")
        lines.append("")
        findings = data["actionable_findings"]
        
        # Multiple basicConfig
        if findings["multiple_basic_config"]:
            lines.append("WARNING: **Multiple `basicConfig()` calls detected:** {}".format(findings['basic_config_count']))
            lines.append("")
            lines.append("Having multiple `basicConfig()` calls can cause configuration conflicts. Consider consolidating to a single configuration point.")
            lines.append("")
            lines.append("| File | Line | Entry Point Likelihood |")
            lines.append("|------|------|------------------------|")
            for cfg in findings["basic_config_locations"]:
                entry_point = cfg.get("entry_point_likelihood", "unknown")
                risk = "WARNING: High risk" if entry_point == "import-time" else "OK: Lower risk"
                lines.append("| `{}` | {} | {} ({}) |".format(cfg['file'], cfg['line'], entry_point, risk))
            lines.append("")
        
        # High print() counts outside scripts/
        if findings["high_print_counts_outside_scripts"]:
            lines.append("WARNING: **High `print()` usage outside scripts/ directories:**")
            lines.append("")
            lines.append("| File | Print Calls |")
            lines.append("|------|-------------|")
            for item in findings["high_print_counts_outside_scripts"]:
                lines.append("| `{}` | {} |".format(item['file'], item['count']))
            lines.append("")
            lines.append("Consider replacing `print()` calls with proper logging in production code.")
            lines.append("")
        
        # Files with both print() and logger calls
        if findings["files_with_both_print_and_logger"]:
            lines.append("WARNING: **Files using both `print()` and logger calls:**")
            lines.append("")
            lines.append("| File | Print Calls | Logger Calls |")
            lines.append("|------|-------------|-------------|")
            for item in findings["files_with_both_print_and_logger"]:
                lines.append("| `{}` | {} | {} |".format(item['file'], item['print_calls'], item['logging_calls']))
            lines.append("")
            lines.append("Consider standardizing on logging for consistent output handling.")
            lines.append("")
        
        # JSON logging status
        if findings["json_logging_enabled"]:
            lines.append("OK: **JSON logging is enabled:**")
            lines.append("")
            for cfg in findings["json_logging_locations"]:
                lines.append("- `{}:{}` ({})".format(cfg['file'], cfg['line'], cfg['config_type']))
            lines.append("")
        else:
            lines.append("INFO: **JSON logging not detected**")
            lines.append("")
            lines.append("Consider enabling JSON formatting for structured logging, especially in production environments.")
            lines.append("")
        
        # structlog configured but unused
        if findings.get("structlog_configured_but_unused"):
            lines.append("WARNING: **structlog configured but not used (or under-detected):**")
            lines.append("")
            lines.append("structlog.configure() was found, but no structlog method calls were detected.")
            lines.append("This may indicate:")
            lines.append("- structlog is configured but not actually used")
            lines.append("- Logger variable origin tracing needs improvement")
            lines.append("")
            lines.append("Consider standardizing on a single logging system or improving logger variable tracking.")
            lines.append("")
        
        # High unknown logger usage
        if findings.get("high_unknown_logger_usage"):
            lines.append("WARNING: **High unknown/generic logger usage detected:** {:.1f}%".format(findings.get('unknown_logger_percentage', 0)))
            lines.append("")
            lines.append("A significant portion of logger calls could not be classified as stdlib or structlog.")
            lines.append("This may indicate:")
            lines.append("- Logger variables are created dynamically or passed as parameters")
            lines.append("- Custom logging wrappers that need better tracking")
            lines.append("- Import patterns that need to be recognized")
            lines.append("")
        
        # High dynamic error templates
        if findings.get("high_dynamic_error_templates"):
            lines.append("WARNING: **High percentage of dynamic error templates:** {:.1f}%".format(findings.get('dynamic_error_percentage', 0)))
            lines.append("")
            lines.append("Many error messages use f-strings or string concatenation, making it difficult to")
            lines.append("track unique error patterns. Consider using structured logging with consistent")
            lines.append("error message templates for better observability.")
            lines.append("")
        
        # Unknown logger variable diagnostics
        if data.get("unknown_logger_vars", {}).get("top_vars"):
            lines.append("### Unknown Logger Variable Diagnostics")
            lines.append("")
            lines.append("Top unknown logger variable names by call count:")
            lines.append("")
            lines.append("| Variable Name | Call Count | Example Files |")
            lines.append("|---------------|------------|---------------|")
            for var_name, count in data["unknown_logger_vars"]["top_vars"]:
                example_files = data["unknown_logger_vars"]["var_files"].get(var_name, [])[:3]
                files_str = ", ".join(["`{}`".format(f) for f in example_files])
                if len(data["unknown_logger_vars"]["var_files"].get(var_name, [])) > 3:
                    files_str += " (+{} more)".format(len(data['unknown_logger_vars']['var_files'].get(var_name, [])) - 3)
                lines.append("| `{}` | {} | {} |".format(var_name, count, files_str))
            lines.append("")
        
        # Cache metrics (if enabled)
        if "cache_metrics" in data:
            lines.append("## Cache Metrics")
            lines.append("")
            cache = data["cache_metrics"]
            lines.append("| Metric | Count |")
            lines.append("|--------|-------|")
            lines.append("| `__pycache__/` directories | {} |".format(cache['pycache_dirs']))
            lines.append("| `*.pyc` files (total, including `__pycache__/`) | {} |".format(cache['pyc_total']))
            lines.append("| `*.pyc` files (outside `__pycache__/`) | {} |".format(cache['pyc_outside_pycache']))
            lines.append("")
        
        return "\n".join(lines)


def main():
    """Main entry point."""
    # Determine default root (script_dir/../..)
    script_path = os.path.abspath(os.path.realpath(__file__))
    script_dir = os.path.dirname(script_path)
    # Go up two levels: tools/dev -> tools -> repo root
    default_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
    
    parser = argparse.ArgumentParser(
        description="Logging audit tool for Python repositories (STRICTLY READ-ONLY)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan default repo (C:\\LogExplainer_clean):
  python tools/dev/repo_scan.py
  
  # Scan specific directory (output to stdout):
  python tools/dev/repo_scan.py --root /path/to/repo
  
  # Save output to file (redirect stdout):
  python tools/dev/repo_scan.py --root /path/to/repo > report.md

Note: This script is STRICTLY READ-ONLY. It never writes, creates, modifies, or deletes any files.
      All output goes to STDOUT only. Redirect stdout yourself if you want to save the output.
        """
    )
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="Root directory to scan (default: {})".format(default_root)
    )
    # No output flags - STDOUT only, strictly read-only (no file writing)
    parser.add_argument(
        "--include-cache-metrics",
        action="store_true",
        default=False,
        help="Include cache metrics (__pycache__ and *.pyc counts) in the report"
    )
    
    args = parser.parse_args()
    
    # Resolve root directory (use default if not provided)
    if args.root:
        # Normalize the path to handle any weird shell parsing
        root_str = str(args.root).strip().strip('"').strip("'")
        root = os.path.abspath(os.path.realpath(root_str))
    else:
        root = default_root
    
    if not os.path.exists(root):
        print("Error: Root directory does not exist: {}".format(root), file=sys.stderr)
        print("  (Resolved from: {})".format(args.root if args.root else 'default'), file=sys.stderr)
        return 1
    
    # Perform scan
    scanner = RepoScanner(root, include_cache_metrics=args.include_cache_metrics)
    try:
        scanner.scan()
    except Exception as e:
        print("Error during scan: {}".format(e), file=sys.stderr)
        return 1
    
    # Get report data
    report_data = scanner.get_report_data()
    
    # Format output as Markdown (STDOUT only - strictly read-only, no file writing)
    output = scanner.format_markdown(report_data)
    
    # Write to stdout with UTF-8 encoding (ONLY output method - no files)
    # Python 2.7: handle unicode output properly
    # Note: unicode is a built-in type in Python 2.7, not available in Python 3
    try:
        # Check Python version for proper handling
        try:
            unicode_type = unicode  # Python 2.7
            is_python2 = True
        except NameError:
            unicode_type = str  # Python 3
            is_python2 = False
        
        if is_python2:
            # Python 2.7: encode unicode to bytes for stdout
            if isinstance(output, unicode_type):
                sys.stdout.write(output.encode("utf-8", errors="replace"))
            else:
                sys.stdout.write(output)
        else:
            # Python 3: stdout expects str, not bytes
            if isinstance(output, bytes):
                sys.stdout.write(output.decode("utf-8", errors="replace"))
            else:
                sys.stdout.write(output)
        sys.stdout.flush()
    except (UnicodeEncodeError, UnicodeDecodeError, TypeError):
        # Fallback: try to print directly
        try:
            print(output)
        except (UnicodeEncodeError, TypeError):
            # Last resort: encode to ASCII with replacement
            try:
                unicode_type = unicode  # Python 2.7
            except NameError:
                unicode_type = str  # Python 3
            if isinstance(output, unicode_type):
                try:
                    print(output.encode("ascii", errors="replace"))
                except:
                    # Final fallback: just print as-is
                    print(str(output))
            else:
                print(output)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
