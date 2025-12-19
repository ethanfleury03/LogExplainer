#!/usr/bin/env python3
"""
READ-ONLY repository scan tool for logging usage and code metrics.

Scans a repository for logging patterns, code health indicators, and generates
human-readable Markdown reports or JSON for automation.

Guarantee:
- This script only READS files.
- It never writes files, creates directories, or modifies anything under --root.
- Output is printed to STDOUT (you may redirect it yourself if you want).

Usage:
    python tools/dev/repo_scan.py --root /path/to/repo [--format md|json] [--out OUTPUT_FILE]
"""

from __future__ import print_function

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict, Counter
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

# Prevent bytecode generation
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
if hasattr(sys, "dont_write_bytecode"):
    sys.dont_write_bytecode = True


# Default ignore directories
DEFAULT_IGNORE_DIRS = {
    ".git", ".svn", ".hg", ".idea", ".vscode",
    "node_modules", "venv", ".venv", "env", ".env",
    "dist", "build", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".next", "out",
    "proc", "run", "sys", "target", "tmp", "var/tmp",
    ".cache", "models", "latest_model", "storage", "logs"
}


class RepoScanner:
    """Scans repository for logging patterns and code metrics."""
    
    def __init__(self, root: str, ignore_dirs: Optional[set] = None):
        self.root = Path(root).resolve()
        self.ignore_dirs = ignore_dirs or DEFAULT_IGNORE_DIRS
        self.stats = {
            "files_scanned": 0,
            "python_files": 0,
            "pycache_dirs": 0,
            "pyc_files": 0,
            "total_loc": 0,
        }
        self.logging_stats = {
            "stdlib_logging": {"imports": 0, "get_logger": 0, "calls": defaultdict(int)},
            "structlog": {"imports": 0, "get_logger": 0, "calls": defaultdict(int)},
            "loguru": {"imports": 0, "get_logger": 0, "calls": defaultdict(int)},
            "print_calls": 0,
            "framework_loggers": defaultdict(int),
        }
        self.file_logging_counts = defaultdict(int)
        self.file_print_counts = defaultdict(int)
        self.level_counts = Counter()
        self.logging_configs = []
        self.todo_fixme = {"total": 0, "by_file": defaultdict(int)}
        self.test_files = []
        self.largest_files = []
        self.scan_timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        
    def should_ignore(self, path: Path) -> bool:
        """Check if path should be ignored."""
        parts = path.parts
        for part in parts:
            if part in self.ignore_dirs:
                return True
        return False
    
    def scan_file(self, filepath: Path) -> Optional[Dict[str, Any]]:
        """Scan a single Python file for logging patterns."""
        try:
            rel_path = str(filepath.relative_to(self.root))
            
            # Skip if in ignored directory
            if self.should_ignore(filepath):
                return None
            
            # Count __pycache__ directories (but don't descend)
            if filepath.name == "__pycache__" and filepath.is_dir():
                self.stats["pycache_dirs"] += 1
                return None
            
            # Count .pyc files
            if filepath.suffix == ".pyc":
                self.stats["pyc_files"] += 1
                return None
            
            # Only scan .py files
            if filepath.suffix != ".py":
                return None
            
            if not filepath.is_file():
                return None
            
            self.stats["python_files"] += 1
            self.stats["files_scanned"] += 1
            
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return None
            
            # Count LOC (non-empty lines)
            lines = [l for l in content.splitlines() if l.strip()]
            loc = len(lines)
            self.stats["total_loc"] += loc
            
            # Track largest files
            self.largest_files.append((rel_path, loc))
            
            # Check for test files
            if "test" in filepath.parts[-1].lower() or "tests" in filepath.parts:
                self.test_files.append(rel_path)
            
            # Scan for logging patterns
            file_log_count = 0
            file_print_count = 0
            
            for line_num, line in enumerate(content.splitlines(), 1):
                # Standard library logging
                if re.search(r'\bimport\s+logging\b', line):
                    self.logging_stats["stdlib_logging"]["imports"] += 1
                if re.search(r'\blogging\.getLogger\b', line):
                    self.logging_stats["stdlib_logging"]["get_logger"] += 1
                
                # structlog
                if re.search(r'\bimport\s+structlog\b', line):
                    self.logging_stats["structlog"]["imports"] += 1
                if re.search(r'\bstructlog\.get_logger\b', line):
                    self.logging_stats["structlog"]["get_logger"] += 1
                
                # loguru
                if re.search(r'\bfrom\s+loguru\s+import\b', line) or re.search(r'\bimport\s+loguru\b', line):
                    self.logging_stats["loguru"]["imports"] += 1
                if re.search(r'\bloguru\.logger\b', line):
                    self.logging_stats["loguru"]["get_logger"] += 1
                
                # Logging method calls
                for level in ["debug", "info", "warning", "error", "critical", "exception"]:
                    # Standard patterns: logger.info(...), logging.info(...), logger.warning(...)
                    pattern = r'\.' + level + r'\s*\('
                    if re.search(pattern, line, re.IGNORECASE):
                        self.logging_stats["stdlib_logging"]["calls"][level] += 1
                        self.level_counts[level] += 1
                        file_log_count += 1
                
                # structlog patterns
                if re.search(r'\.(info|debug|warning|error|critical|exception)\s*\(', line, re.IGNORECASE):
                    # Check if it's likely structlog (has .bind or structured)
                    if ".bind(" in line or "structlog" in content.lower():
                        level_match = re.search(r'\.(info|debug|warning|error|critical|exception)\s*\(', line, re.IGNORECASE)
                        if level_match:
                            level = level_match.group(1).lower()
                            self.logging_stats["structlog"]["calls"][level] += 1
                            self.level_counts[level] += 1
                            file_log_count += 1
                
                # Framework loggers (uvicorn, gunicorn, fastapi)
                if re.search(r'\buvicorn\b', line, re.IGNORECASE):
                    self.logging_stats["framework_loggers"]["uvicorn"] += 1
                if re.search(r'\bgunicorn\b', line, re.IGNORECASE):
                    self.logging_stats["framework_loggers"]["gunicorn"] += 1
                if re.search(r'\bfastapi\b', line, re.IGNORECASE) and "logger" in line.lower():
                    self.logging_stats["framework_loggers"]["fastapi"] += 1
                
                # Print statements
                if re.search(r'\bprint\s*\(', line):
                    file_print_count += 1
                    self.logging_stats["print_calls"] += 1
                
                # TODO/FIXME comments
                if re.search(r'\bTODO\b|\bFIXME\b', line, re.IGNORECASE):
                    self.todo_fixme["total"] += 1
                    self.todo_fixme["by_file"][rel_path] += 1
                
                # Logging configuration detection
                if re.search(r'\b(dictConfig|basicConfig|structlog\.configure)\s*\(', line):
                    self.logging_configs.append({
                        "file": rel_path,
                        "line": line_num,
                        "config_type": "dictConfig" if "dictConfig" in line else ("basicConfig" if "basicConfig" in line else "structlog.configure")
                    })
            
            if file_log_count > 0:
                self.file_logging_counts[rel_path] = file_log_count
            if file_print_count > 0:
                self.file_print_counts[rel_path] = file_print_count
            
            return {
                "path": rel_path,
                "loc": loc,
                "logging_calls": file_log_count,
                "print_calls": file_print_count
            }
            
        except Exception as e:
            # Silently skip files that can't be read
            return None
    
    def scan(self):
        """Perform the full repository scan."""
        if not self.root.exists():
            raise ValueError(f"Root directory does not exist: {self.root}")
        
        # Walk the directory tree
        for root_dir, dirs, files in os.walk(self.root):
            root_path = Path(root_dir)
            
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs and not self.should_ignore(root_path / d)]
            
            # Count __pycache__ directories
            if "__pycache__" in dirs:
                self.stats["pycache_dirs"] += 1
                dirs.remove("__pycache__")  # Don't descend
            
            # Scan Python files
            for filename in files:
                if filename.endswith(".py"):
                    filepath = root_path / filename
                    self.scan_file(filepath)
    
    def get_report_data(self) -> Dict[str, Any]:
        """Get structured report data."""
        # Sort largest files
        self.largest_files.sort(key=lambda x: x[1], reverse=True)
        
        # Get top files
        top_logging_files = sorted(self.file_logging_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        top_print_files = sorted(self.file_print_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        top_todo_files = sorted(self.todo_fixme["by_file"].items(), key=lambda x: x[1], reverse=True)[:10]
        
        return {
            "meta": {
                "repo_path": str(self.root),
                "scan_timestamp": self.scan_timestamp,
                "exclusions": sorted(self.ignore_dirs)
            },
            "scan": {
                "total_files_scanned": self.stats["files_scanned"],
                "python_files": self.stats["python_files"],
                "total_loc": self.stats["total_loc"]
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
                "print_calls": self.logging_stats["print_calls"],
                "framework_loggers": dict(self.logging_stats["framework_loggers"]),
                "top_logging_files": [{"file": f, "count": c} for f, c in top_logging_files],
                "top_print_files": [{"file": f, "count": c} for f, c in top_print_files]
            },
            "log_levels": dict(self.level_counts),
            "logging_config": {
                "config_locations": self.logging_configs,
                "has_json_formatting": any("json" in str(cfg).lower() for cfg in self.logging_configs)
            },
            "repo_health": {
                "pycache_dirs": self.stats["pycache_dirs"],
                "pyc_files": self.stats["pyc_files"],
                "todo_fixme_total": self.todo_fixme["total"],
                "top_todo_files": [{"file": f, "count": c} for f, c in top_todo_files],
                "test_files_count": len(self.test_files),
                "largest_files": [{"file": f, "loc": l} for f, l in self.largest_files[:10]],
                "total_python_loc": self.stats["total_loc"]
            }
        }
    
    def format_markdown(self, data: Dict[str, Any]) -> str:
        """Format report data as Markdown."""
        lines = []
        
        # Header
        lines.append("# Repository Scan Report")
        lines.append("")
        lines.append(f"**Repo Path:** `{data['meta']['repo_path']}`")
        lines.append(f"**Scan Timestamp:** {data['meta']['scan_timestamp']}")
        lines.append(f"**Total Files Scanned:** {data['scan']['total_files_scanned']}")
        lines.append(f"**Python Files:** {data['scan']['python_files']}")
        lines.append(f"**Exclusions:** {', '.join(data['meta']['exclusions'][:10])}{'...' if len(data['meta']['exclusions']) > 10 else ''}")
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
        if structlog_data["imports"] > 0:
            lines.append("### structlog")
            lines.append("")
            lines.append("| Metric | Count |")
            lines.append("|--------|-------|")
            lines.append(f"| Imports | {structlog_data['imports']} |")
            lines.append(f"| `get_logger()` calls | {structlog_data['get_logger_calls']} |")
            lines.append(f"| Total method calls | {sum(structlog_data['method_calls'].values())} |")
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
        
        # Framework loggers
        if data["logging_usage"]["framework_loggers"]:
            lines.append("### Framework Logger Usage")
            lines.append("")
            lines.append("| Framework | Count |")
            lines.append("|-----------|-------|")
            for fw, count in sorted(data["logging_usage"]["framework_loggers"].items()):
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
            for cfg in data["logging_config"]["config_locations"][:10]:
                lines.append(f"| `{cfg['file']}` | {cfg['line']} | {cfg['config_type']} |")
            lines.append("")
            lines.append(f"**JSON Formatting Detected:** {'Yes' if data['logging_config']['has_json_formatting'] else 'No'}")
        else:
            lines.append("No explicit logging configuration found.")
        lines.append("")
        
        # Repo Health Snapshot
        lines.append("## Repo Health Snapshot")
        lines.append("")
        
        health = data["repo_health"]
        lines.append("### Bytecode Files (Read-Only Count)")
        lines.append("")
        lines.append("| Type | Count |")
        lines.append("|------|-------|")
        lines.append(f"| `__pycache__/` directories | {health['pycache_dirs']} |")
        lines.append(f"| `*.pyc` files | {health['pyc_files']} |")
        lines.append("")
        
        lines.append("### TODO/FIXME Comments")
        lines.append("")
        lines.append(f"**Total:** {health['todo_fixme_total']}")
        if health["top_todo_files"]:
            lines.append("")
            lines.append("| File | Count |")
            lines.append("|------|-------|")
            for item in health["top_todo_files"]:
                lines.append(f"| `{item['file']}` | {item['count']} |")
        lines.append("")
        
        lines.append("### Test Files")
        lines.append("")
        lines.append(f"**Total test files discovered:** {health['test_files_count']}")
        lines.append("")
        
        lines.append("### Largest Python Files (by LOC)")
        lines.append("")
        lines.append("| File | Lines of Code |")
        lines.append("|------|---------------|")
        for item in health["largest_files"]:
            lines.append(f"| `{item['file']}` | {item['loc']} |")
        lines.append("")
        
        lines.append(f"**Total Python LOC:** {health['total_python_loc']}")
        lines.append("")
        
        return "\n".join(lines)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Scan repository for logging usage and code metrics (READ-ONLY)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan ArrowSystems backend:
  python tools/dev/repo_scan.py --root C:/Users/ethan/ArrowSystems/backend
  
  # Markdown output (default):
  python tools/dev/repo_scan.py --root /path/to/repo
  
  # JSON output:
  python tools/dev/repo_scan.py --root /path/to/repo --format json --out report.json
  
  # Save Markdown report:
  python tools/dev/repo_scan.py --root /path/to/repo --out report.md
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
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output file path (default: stdout)"
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
    
    # Write output
    if args.out:
        try:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(output)
        except Exception as e:
            print(f"Error writing output file: {e}", file=sys.stderr)
            return 1
    else:
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

