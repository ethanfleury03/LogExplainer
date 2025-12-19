#!/usr/bin/env python3
"""
READ-ONLY logging audit tool for Python repositories.

Scans a repository for logging patterns, configuration points, and generates
actionable findings in human-readable Markdown reports or JSON for automation.

Features:
- Detects stdlib logging, structlog, and generic logger usage
- Identifies logging configuration points (basicConfig, dictConfig, fileConfig, structlog.configure)
- Tracks print() usage and identifies files mixing print() with logging
- Detects JSON logging configuration
- Provides actionable findings for logging improvements

Guarantee:
- This script only READS files.
- It never writes files, creates directories, or modifies anything.
- Output is printed to STDOUT only (users can redirect output themselves).

Usage:
    python tools/dev/repo_scan.py --root /path/to/repo [--format md|json]
    python tools/dev/repo_scan.py --root /path/to/repo > report.md
"""

from __future__ import print_function

import argparse
import ast
import json
import os
import re
import sys
import time
from collections import defaultdict, Counter
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Set

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


class LoggingASTVisitor(ast.NodeVisitor):
    """AST visitor to extract logging patterns from Python code."""
    
    def __init__(self, file_content: str):
        self.file_content = file_content
        self.lines = file_content.splitlines()
        
        # Import tracking
        self.has_stdlib_logging = False
        self.has_structlog = False
        self.has_loguru = False
        
        # Logger variable tracking (for structlog detection)
        self.structlog_loggers = set()  # Variable names assigned from structlog.get_logger()
        self.stdlib_loggers = set()  # Variable names assigned from logging.getLogger()
        
        # Counts
        self.stdlib_imports = 0
        self.structlog_imports = 0
        self.loguru_imports = 0
        self.stdlib_getlogger_calls = 0
        self.structlog_getlogger_calls = 0
        
        # Logging calls by category
        self.stdlib_calls = defaultdict(int)  # level -> count
        self.structlog_calls = defaultdict(int)  # level -> count
        self.generic_calls = defaultdict(int)  # level -> count
        self.print_calls = 0
        
        # Config detection
        self.config_calls = []  # List of (line_no, config_type)
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
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node):
        """Track from ... import statements."""
        if node.module == "logging":
            self.has_stdlib_logging = True
            self.stdlib_imports += 1
        elif node.module == "structlog":
            self.has_structlog = True
            self.structlog_imports += 1
        elif node.module == "loguru":
            self.has_loguru = True
            self.loguru_imports += 1
        self.generic_visit(node)
    
    def visit_Assign(self, node):
        """Track logger variable assignments."""
        # Check if assignment is from logging.getLogger() or structlog.get_logger()
        if isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Attribute):
                # logging.getLogger(...)
                if (isinstance(call.func.value, ast.Name) and 
                    call.func.value.id == "logging" and
                    call.func.attr == "getLogger"):
                    self.stdlib_getlogger_calls += 1
                    # Track variable names
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            self.stdlib_loggers.add(target.id)
                
                # structlog.get_logger(...)
                elif (isinstance(call.func.value, ast.Name) and
                      call.func.value.id == "structlog" and
                      call.func.attr == "get_logger"):
                    self.structlog_getlogger_calls += 1
                    # Track variable names
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            self.structlog_loggers.add(target.id)
        
        self.generic_visit(node)
    
    def visit_Call(self, node):
        """Track function calls (logging, print, config)."""
        # Print calls
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            self.print_calls += 1
            return
        
        # Logging method calls (logger.info, logging.info, etc.)
        if isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            if attr_name in ("debug", "info", "warning", "error", "critical", "exception"):
                line_no = node.lineno
                
                # Check if it's logging.info(...) - direct stdlib call
                if (isinstance(node.func.value, ast.Name) and 
                    node.func.value.id == "logging"):
                    self.stdlib_calls[attr_name] += 1
                    return
                
                # Check if it's a known structlog logger variable
                if isinstance(node.func.value, ast.Name):
                    var_name = node.func.value.id
                    if var_name in self.structlog_loggers:
                        self.structlog_calls[attr_name] += 1
                        return
                    elif var_name in self.stdlib_loggers:
                        self.stdlib_calls[attr_name] += 1
                        return
                
                # Check if file has structlog import and this looks like structlog usage
                if self.has_structlog:
                    # Heuristic: if file uses structlog and this is a logger call, likely structlog
                    # But be conservative - only if we've seen structlog.get_logger() calls
                    if self.structlog_loggers:
                        self.structlog_calls[attr_name] += 1
                        return
                
                # Generic logger call (unknown logger variable)
                self.generic_calls[attr_name] += 1
        
        # Config calls
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == "basicConfig":
                if (isinstance(node.func.value, ast.Name) and 
                    node.func.value.id == "logging"):
                    self.config_calls.append((node.lineno, "basicConfig"))
            elif node.func.attr == "dictConfig":
                if (isinstance(node.func.value, ast.Attribute) and
                    isinstance(node.func.value.value, ast.Name) and
                    node.func.value.value.id == "logging" and
                    node.func.value.attr == "config"):
                    self.config_calls.append((node.lineno, "dictConfig"))
            elif node.func.attr == "fileConfig":
                if (isinstance(node.func.value, ast.Attribute) and
                    isinstance(node.func.value.value, ast.Name) and
                    node.func.value.value.id == "logging" and
                    node.func.value.attr == "config"):
                    self.config_calls.append((node.lineno, "fileConfig"))
            elif node.func.attr == "configure":
                if (isinstance(node.func.value, ast.Name) and
                    node.func.value.id == "structlog"):
                    self.config_calls.append((node.lineno, "structlog.configure"))
        
        self.generic_visit(node)
    
    def check_json_formatting(self):
        """Check for JSON formatting indicators in config locations and file content."""
        json_indicators = [
            "JSONFormatter", "pythonjsonlogger", "jsonlogger", 
            "JSONRenderer", "orjson"
        ]
        
        # Check config call lines and surrounding context (5 lines before/after)
        for line_no, config_type in self.config_calls:
            start_line = max(0, line_no - 6)  # 5 lines before (0-indexed)
            end_line = min(len(self.lines), line_no + 5)  # 5 lines after
            
            for i in range(start_line, end_line):
                if i < len(self.lines):
                    line = self.lines[i]
                    for indicator in json_indicators:
                        if indicator in line:
                            self.json_formatting_indicators.append(indicator)
                            break
        
        # Also check entire file for structlog JSONRenderer in processors
        if self.has_structlog:
            file_content_lower = self.file_content.lower()
            # Check for JSONRenderer in structlog.configure or processor lists
            if "jsonrenderer" in file_content_lower or "json_renderer" in file_content_lower:
                # Look for structlog.configure or processor assignments
                if "structlog.configure" in self.file_content or "processors" in file_content_lower:
                    self.json_formatting_indicators.append("JSONRenderer")


class RepoScanner:
    """Scans repository for logging patterns and code metrics."""
    
    def __init__(self, root: str, ignore_dirs: Optional[set] = None):
        self.root = Path(root).resolve()
        self.ignore_dirs = ignore_dirs or DEFAULT_IGNORE_DIRS
        # Scan coverage tracking
        self.scan_coverage = {
            "python_files_discovered": 0,
            "python_files_scanned": 0,
            "python_files_skipped": {
                "ignored_path": [],
                "decode_error": [],
                "read_error": []
            }
        }
        self.logging_stats = {
            "stdlib_logging": {"imports": 0, "get_logger": 0, "calls": defaultdict(int)},
            "structlog": {"imports": 0, "get_logger": 0, "calls": defaultdict(int)},
            "loguru": {"imports": 0, "get_logger": 0, "calls": defaultdict(int)},
            "generic_logging": {"calls": defaultdict(int)},
            "print_calls": 0,
            "framework_mentions": defaultdict(int),
        }
        self.file_logging_counts = defaultdict(int)
        self.file_print_counts = defaultdict(int)
        self.file_has_both_print_and_logger = []  # Files with both print() and logger calls
        self.level_counts = Counter()
        self.logging_configs = []
        self.scan_timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        
    def should_ignore_for_content_scan(self, path: Path) -> bool:
        """Check if path should be ignored for content scanning (not counting)."""
        parts = path.parts
        for part in parts:
            if part in self.ignore_dirs:
                return True
        return False
    
    def analyze_python_file(self, filepath: Path, content: str) -> Dict[str, Any]:
        """Analyze a Python file using AST."""
        rel_path = str(filepath.relative_to(self.root))
        
        try:
            tree = ast.parse(content, filename=str(filepath))
        except SyntaxError:
            # Skip files with syntax errors
            return {
                "path": rel_path,
                "logging_calls": 0,
                "print_calls": 0,
                "error": "syntax_error"
            }
        
        visitor = LoggingASTVisitor(content)
        visitor.visit(tree)
        visitor.check_json_formatting()
        
        # Aggregate counts
        total_logging_calls = (
            sum(visitor.stdlib_calls.values()) +
            sum(visitor.structlog_calls.values()) +
            sum(visitor.generic_calls.values())
        )
        
        # Update global stats
        self.logging_stats["stdlib_logging"]["imports"] += visitor.stdlib_imports
        self.logging_stats["structlog"]["imports"] += visitor.structlog_imports
        self.logging_stats["loguru"]["imports"] += visitor.loguru_imports
        self.logging_stats["stdlib_logging"]["get_logger"] += visitor.stdlib_getlogger_calls
        self.logging_stats["structlog"]["get_logger"] += visitor.structlog_getlogger_calls
        self.logging_stats["print_calls"] += visitor.print_calls
        
        # Count calls by level
        for level, count in visitor.stdlib_calls.items():
            self.logging_stats["stdlib_logging"]["calls"][level] += count
            self.level_counts[level] += count
        
        for level, count in visitor.structlog_calls.items():
            self.logging_stats["structlog"]["calls"][level] += count
            self.level_counts[level] += count
        
        for level, count in visitor.generic_calls.items():
            self.logging_stats["generic_logging"]["calls"][level] += count
            self.level_counts[level] += count
        
        # Track per-file counts
        if total_logging_calls > 0:
            self.file_logging_counts[rel_path] = total_logging_calls
        if visitor.print_calls > 0:
            self.file_print_counts[rel_path] = visitor.print_calls
        
        # Config detection
        file_has_json_formatting = bool(visitor.json_formatting_indicators)
        for line_no, config_type in visitor.config_calls:
            cfg_entry = {
                "file": rel_path,
                "line": line_no,
                "config_type": config_type
            }
            if file_has_json_formatting:
                cfg_entry["has_json_formatting"] = True
            self.logging_configs.append(cfg_entry)
        
        # Framework mentions (string-based, not AST)
        content_lower = content.lower()
        if "uvicorn" in content_lower:
            self.logging_stats["framework_mentions"]["uvicorn"] += 1
        if "gunicorn" in content_lower:
            self.logging_stats["framework_mentions"]["gunicorn"] += 1
        if "fastapi" in content_lower and "logger" in content_lower:
            self.logging_stats["framework_mentions"]["fastapi"] += 1
        
        return {
            "path": rel_path,
            "logging_calls": total_logging_calls,
            "print_calls": visitor.print_calls
        }
    
    def scan(self):
        """Perform the full repository scan."""
        if not self.root.exists():
            raise ValueError(f"Root directory does not exist: {self.root}")
        
        # Walk the directory tree
        for root_dir, dirs, files in os.walk(self.root):
            root_path = Path(root_dir)
            
            # Skip __pycache__ directories entirely
            if "__pycache__" in dirs:
                dirs[:] = [d for d in dirs if d != "__pycache__"]
            
            # Filter out ignored directories for content scanning
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs and not self.should_ignore_for_content_scan(root_path / d)]
            
            # Scan Python files for content
            for filename in files:
                if filename.endswith(".py"):
                    filepath = root_path / filename
                    rel_path = str(filepath.relative_to(self.root))
                    
                    # Count all discovered Python files
                    self.scan_coverage["python_files_discovered"] += 1
                    
                    # Skip if in ignored directory
                    if self.should_ignore_for_content_scan(filepath):
                        self.scan_coverage["python_files_skipped"]["ignored_path"].append(rel_path)
                        continue
                    
                    # Read and analyze
                    try:
                        content = filepath.read_text(encoding="utf-8", errors="replace")
                    except UnicodeDecodeError as e:
                        self.scan_coverage["python_files_skipped"]["decode_error"].append(rel_path)
                        continue
                    except Exception as e:
                        self.scan_coverage["python_files_skipped"]["read_error"].append(rel_path)
                        continue
                    
                    self.scan_coverage["python_files_scanned"] += 1
                    
                    # Analyze with AST
                    result = self.analyze_python_file(filepath, content)
                    
                    # Track files with both print() and logger calls
                    if result["print_calls"] > 0 and result["logging_calls"] > 0:
                        self.file_has_both_print_and_logger.append({
                            "file": rel_path,
                            "print_calls": result["print_calls"],
                            "logging_calls": result["logging_calls"]
                        })
    
    def get_report_data(self) -> Dict[str, Any]:
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
        
        return {
            "meta": {
                "repo_path": str(self.root),
                "scan_timestamp": self.scan_timestamp,
                "exclusions": sorted(self.ignore_dirs)
            },
            "scan_coverage": {
                "python_files_discovered": self.scan_coverage["python_files_discovered"],
                "python_files_scanned": self.scan_coverage["python_files_scanned"],
                "python_files_skipped": {
                    "ignored_path": len(self.scan_coverage["python_files_skipped"]["ignored_path"]),
                    "decode_error": len(self.scan_coverage["python_files_skipped"]["decode_error"]),
                    "read_error": len(self.scan_coverage["python_files_skipped"]["read_error"])
                },
                "skipped_files_detail": {
                    "ignored_path": self.scan_coverage["python_files_skipped"]["ignored_path"][:20],  # Limit for report
                    "decode_error": self.scan_coverage["python_files_skipped"]["decode_error"][:20],
                    "read_error": self.scan_coverage["python_files_skipped"]["read_error"][:20]
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
                "loguru": {
                    "imports": self.logging_stats["loguru"]["imports"],
                    "get_logger_calls": self.logging_stats["loguru"]["get_logger"],
                    "method_calls": dict(self.logging_stats["loguru"]["calls"])
                },
                "generic_logging": {
                    "method_calls": dict(self.logging_stats["generic_logging"]["calls"])
                },
                "print_calls": self.logging_stats["print_calls"],
                "framework_mentions": dict(self.logging_stats["framework_mentions"]),
                "top_logging_files": [{"file": f, "count": c} for f, c in top_logging_files],
                "top_print_files": [{"file": f, "count": c} for f, c in top_print_files]
            },
            "log_levels": dict(self.level_counts),
            "logging_config": {
                "config_locations": self.logging_configs,
                "has_json_formatting": has_json_formatting,
                "json_config_locations": json_configs
            },
            "actionable_findings": {
                "multiple_basic_config": multiple_basic_config,
                "basic_config_count": basic_config_count,
                "high_print_counts_outside_scripts": high_print_files[:20],
                "files_with_both_print_and_logger": files_with_both[:20],
                "json_logging_enabled": has_json_formatting,
                "json_logging_locations": json_configs
            }
        }
    
    def format_markdown(self, data: Dict[str, Any]) -> str:
        """Format report data as Markdown."""
        lines = []
        
        # Header
        lines.append("# Logging Audit Report")
        lines.append("")
        lines.append(f"**Repo Path:** `{data['meta']['repo_path']}`")
        lines.append(f"**Scan Timestamp:** {data['meta']['scan_timestamp']}")
        lines.append("")
        
        # Scan Coverage
        coverage = data["scan_coverage"]
        lines.append("## Scan Coverage")
        lines.append("")
        lines.append("| Metric | Count |")
        lines.append("|--------|-------|")
        lines.append(f"| Python files discovered | {coverage['python_files_discovered']} |")
        lines.append(f"| Python files successfully scanned | {coverage['python_files_scanned']} |")
        lines.append(f"| Python files skipped (ignored path) | {coverage['python_files_skipped']['ignored_path']} |")
        lines.append(f"| Python files skipped (decode error) | {coverage['python_files_skipped']['decode_error']} |")
        lines.append(f"| Python files skipped (read error) | {coverage['python_files_skipped']['read_error']} |")
        lines.append("")
        
        # Show ignored directories
        exclusions = data['meta']['exclusions']
        if exclusions:
            lines.append(f"**Ignored directories:** {', '.join(exclusions[:20])}{'...' if len(exclusions) > 20 else ''}")
            lines.append("")
        
        # Show sample skipped files if any
        skipped_detail = coverage["skipped_files_detail"]
        if skipped_detail["ignored_path"]:
            lines.append("**Sample skipped files (ignored path):**")
            for f in skipped_detail["ignored_path"][:5]:
                lines.append(f"- `{f}`")
            if len(skipped_detail["ignored_path"]) > 5:
                lines.append(f"- ... and {len(skipped_detail['ignored_path']) - 5} more")
            lines.append("")
        
        if skipped_detail["decode_error"]:
            lines.append("**Sample skipped files (decode error):**")
            for f in skipped_detail["decode_error"][:5]:
                lines.append(f"- `{f}`")
            if len(skipped_detail["decode_error"]) > 5:
                lines.append(f"- ... and {len(skipped_detail['decode_error']) - 5} more")
            lines.append("")
        
        if skipped_detail["read_error"]:
            lines.append("**Sample skipped files (read error):**")
            for f in skipped_detail["read_error"][:5]:
                lines.append(f"- `{f}`")
            if len(skipped_detail["read_error"]) > 5:
                lines.append(f"- ... and {len(skipped_detail['read_error']) - 5} more")
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
        lines.append(f"| Imports | {stdlib['imports']} |")
        lines.append(f"| `getLogger()` calls | {stdlib['get_logger_calls']} |")
        lines.append(f"| Total method calls | {sum(stdlib['method_calls'].values())} |")
        lines.append("")
        
        # structlog
        structlog_data = data["logging_usage"]["structlog"]
        if structlog_data["imports"] > 0 or sum(structlog_data["method_calls"].values()) > 0:
            lines.append("### structlog")
            lines.append("")
            lines.append("| Metric | Count |")
            lines.append("|--------|-------|")
            lines.append(f"| Imports | {structlog_data['imports']} |")
            lines.append(f"| `get_logger()` calls | {structlog_data['get_logger_calls']} |")
            lines.append(f"| Total method calls | {sum(structlog_data['method_calls'].values())} |")
            lines.append("")
        
        # Generic logger calls
        generic_data = data["logging_usage"]["generic_logging"]
        if sum(generic_data["method_calls"].values()) > 0:
            lines.append("### Generic Logger Calls")
            lines.append("")
            lines.append("| Metric | Count |")
            lines.append("|--------|-------|")
            lines.append(f"| Total method calls | {sum(generic_data['method_calls'].values())} |")
            lines.append("")
            lines.append("*Note: Logger calls where the logger variable source could not be determined.*")
            lines.append("")
        
        # loguru
        loguru_data = data["logging_usage"]["loguru"]
        if loguru_data["imports"] > 0:
            lines.append("### loguru")
            lines.append("")
            lines.append("| Metric | Count |")
            lines.append("|--------|-------|")
            lines.append(f"| Imports | {loguru_data['imports']} |")
            lines.append(f"| Logger usage | {loguru_data['get_logger_calls']} |")
            lines.append("")
        
        # Print statements
        lines.append("### Non-Logging Output")
        lines.append("")
        lines.append("| Type | Count |")
        lines.append("|------|-------|")
        lines.append(f"| `print()` calls | {data['logging_usage']['print_calls']} |")
        lines.append("")
        
        # Framework mentions
        if data["logging_usage"]["framework_mentions"]:
            lines.append("### Framework String Mentions / Imports")
            lines.append("")
            lines.append("| Framework | Count |")
            lines.append("|-----------|-------|")
            lines.append("*Note: String mentions or imports, not necessarily logger usage.*")
            lines.append("")
            for fw, count in sorted(data["logging_usage"]["framework_mentions"].items()):
                lines.append(f"| {fw} | {count} |")
            lines.append("")
        
        # Top files by logging calls
        if data["logging_usage"]["top_logging_files"]:
            lines.append("### Top 10 Files by Logging Calls")
            lines.append("")
            lines.append("| File | Calls |")
            lines.append("|------|-------|")
            for item in data["logging_usage"]["top_logging_files"]:
                lines.append(f"| `{item['file']}` | {item['count']} |")
            lines.append("")
        
        # Top files by print calls
        if data["logging_usage"]["top_print_files"]:
            lines.append("### Top 10 Files by Print Calls")
            lines.append("")
            lines.append("| File | Calls |")
            lines.append("|------|-------|")
            for item in data["logging_usage"]["top_print_files"]:
                lines.append(f"| `{item['file']}` | {item['count']} |")
            lines.append("")
        
        # Log Level Distribution
        lines.append("## Log Level Distribution")
        lines.append("")
        lines.append("| Level | Count |")
        lines.append("|-------|-------|")
        for level in ["debug", "info", "warning", "error", "critical", "exception"]:
            count = data["log_levels"].get(level, 0)
            if count > 0:
                lines.append(f"| {level.upper()} | {count} |")
        lines.append("")
        
        # Logger Configuration
        lines.append("## Logger Configuration Overview")
        lines.append("")
        if data["logging_config"]["config_locations"]:
            lines.append("### Configuration Locations")
            lines.append("")
            lines.append("| File | Line | Type |")
            lines.append("|------|------|------|")
            for cfg in data["logging_config"]["config_locations"]:
                json_marker = " (JSON)" if cfg.get("has_json_formatting") else ""
                lines.append(f"| `{cfg['file']}` | {cfg['line']} | {cfg['config_type']}{json_marker} |")
            lines.append("")
            
            # Framework config references
            if data["logging_usage"]["framework_mentions"]:
                lines.append("### Framework Config References")
                lines.append("")
                lines.append("| Framework | File Mentions |")
                lines.append("|-----------|---------------|")
                for fw, count in sorted(data["logging_usage"]["framework_mentions"].items()):
                    lines.append(f"| {fw} | {count} |")
                lines.append("")
        else:
            lines.append("No explicit logging configuration found.")
        lines.append("")
        
        # Actionable Findings
        lines.append("## Actionable Findings")
        lines.append("")
        findings = data["actionable_findings"]
        
        # Multiple basicConfig
        if findings["multiple_basic_config"]:
            lines.append(f"⚠️ **Multiple `basicConfig()` calls detected:** {findings['basic_config_count']}")
            lines.append("")
            lines.append("Having multiple `basicConfig()` calls can cause configuration conflicts. Consider consolidating to a single configuration point.")
            lines.append("")
            basic_configs = [cfg for cfg in data["logging_config"]["config_locations"] if cfg["config_type"] == "basicConfig"]
            for cfg in basic_configs:
                lines.append(f"- `{cfg['file']}:{cfg['line']}`")
            lines.append("")
        
        # High print() counts outside scripts/
        if findings["high_print_counts_outside_scripts"]:
            lines.append("⚠️ **High `print()` usage outside scripts/ directories:**")
            lines.append("")
            lines.append("| File | Print Calls |")
            lines.append("|------|-------------|")
            for item in findings["high_print_counts_outside_scripts"]:
                lines.append(f"| `{item['file']}` | {item['count']} |")
            lines.append("")
            lines.append("Consider replacing `print()` calls with proper logging in production code.")
            lines.append("")
        
        # Files with both print() and logger calls
        if findings["files_with_both_print_and_logger"]:
            lines.append("⚠️ **Files using both `print()` and logger calls:**")
            lines.append("")
            lines.append("| File | Print Calls | Logger Calls |")
            lines.append("|------|-------------|-------------|")
            for item in findings["files_with_both_print_and_logger"]:
                lines.append(f"| `{item['file']}` | {item['print_calls']} | {item['logging_calls']} |")
            lines.append("")
            lines.append("Consider standardizing on logging for consistent output handling.")
            lines.append("")
        
        # JSON logging status
        if findings["json_logging_enabled"]:
            lines.append("✅ **JSON logging is enabled:**")
            lines.append("")
            for cfg in findings["json_logging_locations"]:
                lines.append(f"- `{cfg['file']}:{cfg['line']}` ({cfg['config_type']})")
            lines.append("")
        else:
            lines.append("ℹ️ **JSON logging not detected**")
            lines.append("")
            lines.append("Consider enabling JSON formatting for structured logging, especially in production environments.")
            lines.append("")
        
        return "\n".join(lines)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Logging audit tool for Python repositories (STRICTLY READ-ONLY)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan ArrowSystems backend (output to stdout):
  python tools/dev/repo_scan.py --root C:/Users/ethan/ArrowSystems/backend
  
  # Save output to file (redirect stdout):
  python tools/dev/repo_scan.py --root /path/to/repo > report.md
  
  # JSON output:
  python tools/dev/repo_scan.py --root /path/to/repo --format json > report.json

Note: This script is STRICTLY READ-ONLY. It never writes files or creates directories.
      Redirect stdout yourself if you want to save the output.
        """
    )
    parser.add_argument(
        "--root",
        type=str,
        required=True,
        help="Root directory to scan (REQUIRED)"
    )
    parser.add_argument(
        "--format",
        choices=["md", "json"],
        default="md",
        help="Output format: 'md' for Markdown (default), 'json' for JSON"
    )
    
    args = parser.parse_args()
    
    # Resolve root directory
    root = Path(args.root).resolve()
    
    if not root.exists():
        print(f"Error: Root directory does not exist: {root}", file=sys.stderr)
        return 1
    
    # Perform scan
    scanner = RepoScanner(str(root))
    try:
        scanner.scan()
    except Exception as e:
        print(f"Error during scan: {e}", file=sys.stderr)
        return 1
    
    # Get report data
    report_data = scanner.get_report_data()
    
    # Format output
    if args.format == "json":
        output = json.dumps(report_data, indent=2, ensure_ascii=False)
    else:
        output = scanner.format_markdown(report_data)
    
    # Write to stdout with UTF-8 encoding
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stdout.write(output)
        sys.stdout.flush()
    except (UnicodeEncodeError, AttributeError):
        # Fallback for Python 2 or systems without reconfigure
        print(output.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
