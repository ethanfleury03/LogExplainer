#!/usr/bin/env python3
"""
READ-ONLY log inventory + literal catalog scanner.

Guarantee:
- This script only READS files.
- It never writes files, creates directories, or modifies anything.
- Output is printed to STDOUT as JSON (you may redirect it yourself if you want).

What it produces (in one JSON blob):
1) log_call_inventory:
   - Every detected logging call site (file, line, level/type, snippet)
2) literal_catalog:
   - All string literals found inside logging calls (grouped + deduped)
3) format_string_flags:
   - Calls likely dynamic (f-strings, % formatting, .format(), concatenation, template literals)

Notes:
- Python parsing uses `ast` for accuracy (logger.info(...), logging.error(...), print(...), etc.)
- Non-Python uses lightweight regex heuristics (console.log, LOG_ERROR, printf, etc.)
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, TextIO


# ---------------------------
# Config
# ---------------------------

DEFAULT_EXCLUDE_DIRS = {
    ".git", ".hg", ".svn",
    "__pycache__", ".mypy_cache", ".pytest_cache",
    "node_modules", "dist", "build", "out", "target",
    "venv", ".venv", "env", ".env",
    ".idea", ".vscode",
}

DEFAULT_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".c", ".cc", ".cpp", ".h", ".hpp",
    ".cs", ".java",
    ".go", ".rs",
    ".sh", ".bash", ".zsh",
}

DEFAULT_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10MB safety cap


# ---------------------------
# Data model
# ---------------------------

@dataclass
class ScanStats:
    root: str
    files_considered: int = 0
    files_scanned: int = 0
    files_skipped_excluded_dir: int = 0
    files_skipped_ext: int = 0
    files_skipped_too_big: int = 0
    files_skipped_unreadable: int = 0
    elapsed_seconds: float = 0.0


@dataclass
class LogCall:
    file: str
    line_no: int
    language: str
    kind: str              # e.g., python_logger, python_print, js_console, c_printf, generic_logger
    level: Optional[str]   # e.g., error/warn/info/debug/trace/fatal
    callee: Optional[str]  # extracted callee name if available
    snippet: str
    string_literals: List[str]
    is_dynamic: bool
    dynamic_reasons: List[str]


# ---------------------------
# Helpers (read-only)
# ---------------------------

def _is_excluded(path: Path, exclude_dirs: set[str]) -> bool:
    # Exclude if any directory component matches exclude list
    for part in path.parts:
        if part in exclude_dirs:
            return True
    return False


def _safe_read_text(path: Path) -> Optional[str]:
    try:
        # UTF-8 with replacement to keep scanning robust (read-only)
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _line_snippet(text: str, line_no: int, max_len: int = 240) -> str:
    lines = text.splitlines()
    if 1 <= line_no <= len(lines):
        s = lines[line_no - 1].strip("\n\r")
        if len(s) > max_len:
            return s[: max_len - 3] + "..."
        return s
    return ""


def _dedupe_preserve_order(items: Iterable[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# ---------------------------
# Python AST scanning
# ---------------------------

PY_LEVELS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "fatal", "trace"}


def _py_callee_to_str(node: ast.AST) -> Optional[str]:
    # Try to render a dotted name like logger.error or logging.error
    if isinstance(node, ast.Attribute):
        base = _py_callee_to_str(node.value)
        if base:
            return f"{base}.{node.attr}"
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _py_extract_string_literals_from_expr(node: ast.AST) -> Tuple[List[str], bool, List[str]]:
    """
    Returns: (literals, is_dynamic, dynamic_reasons)
    """
    lits: List[str] = []
    dynamic = False
    reasons: List[str] = []

    def walk(n: ast.AST) -> None:
        nonlocal dynamic

        # Plain literal strings
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            lits.append(n.value)
            return

        # f-strings
        if isinstance(n, ast.JoinedStr):
            dynamic = True
            reasons.append("python_fstring")
            # capture static parts too
            for v in n.values:
                walk(v)
            return

        # "%" formatting
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mod):
            dynamic = True
            reasons.append("python_percent_formatting")
            walk(n.left)
            # right side may include strings too
            walk(n.right)
            return

        # "+" string concatenation
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
            dynamic = True
            reasons.append("python_concat")
            walk(n.left)
            walk(n.right)
            return

        # .format(...)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "format":
            dynamic = True
            reasons.append("python_dot_format")
            walk(n.func.value)
            for a in n.args:
                walk(a)
            return

        # General recursion
        for child in ast.iter_child_nodes(n):
            walk(child)

    walk(node)
    return (_dedupe_preserve_order(lits), dynamic, _dedupe_preserve_order(reasons))


def _py_classify_call(func_str: str) -> Tuple[str, Optional[str]]:
    """
    Return (kind, level)
    """
    # print(...)
    if func_str == "print":
        return ("python_print", None)

    # logging.<level>(...) OR logger.<level>(...)
    parts = func_str.split(".")
    if len(parts) >= 2:
        level = parts[-1].lower()
        if level in PY_LEVELS:
            return ("python_logger", "warn" if level == "warning" else level)

    return ("python_call", None)


def scan_python_file(path: Path, text: str) -> List[LogCall]:
    out: List[LogCall] = []
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return out

    class V(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> Any:
            func_str = _py_callee_to_str(node.func) or ""
            kind, level = _py_classify_call(func_str)

            is_log_like = False

            # Consider:
            # - logger.<level>(...)
            # - logging.<level>(...)
            # - print(...)
            # - logger.log(level, ...)
            if kind in {"python_logger", "python_print"}:
                is_log_like = True
            elif func_str.endswith(".log") and len(node.args) >= 2:
                # logger.log(logging.ERROR, "msg")
                is_log_like = True
                kind = "python_logger_log"
                level = None

            if is_log_like:
                # Extract literals from all args (not keywords) because message might not be first
                literals: List[str] = []
                dynamic = False
                reasons: List[str] = []

                for a in node.args:
                    l, d, r = _py_extract_string_literals_from_expr(a)
                    literals.extend(l)
                    dynamic = dynamic or d
                    reasons.extend(r)

                literals = _dedupe_preserve_order(literals)
                reasons = _dedupe_preserve_order(reasons)

                # Also flag if there are non-literal args and at least one string literal => dynamic-ish
                if any(not (isinstance(a, ast.Constant) and isinstance(getattr(a, "value", None), str)) for a in node.args):
                    if literals:
                        dynamic = True
                        reasons = _dedupe_preserve_order(reasons + ["python_non_literal_args"])

                out.append(
                    LogCall(
                        file=str(path),
                        line_no=getattr(node, "lineno", 1),
                        language="python",
                        kind=kind,
                        level=level,
                        callee=func_str or None,
                        snippet=_line_snippet(text, getattr(node, "lineno", 1)),
                        string_literals=literals,
                        is_dynamic=dynamic,
                        dynamic_reasons=reasons,
                    )
                )

            self.generic_visit(node)

    V().visit(tree)
    return out


# ---------------------------
# Non-Python heuristic scanning (regex)
# ---------------------------

# Basic string literal regex per language family (best-effort)
RE_STR_DQ_SQ = re.compile(r'("([^"\\]|\\.)*"|\'([^\'\\]|\\.)*\')')
RE_TEMPLATE = re.compile(r'`([^`\\]|\\.)*`')  # JS template literal

# Common call patterns (best-effort)
RE_JS_CONSOLE = re.compile(r'\bconsole\.(log|info|warn|error|debug|trace)\s*\(', re.IGNORECASE)
RE_GENERIC_LOGGER = re.compile(r'\b(logger|log)\.(trace|debug|info|warn|warning|error|fatal|critical)\s*\(', re.IGNORECASE)

RE_C_PRINTF = re.compile(r'\b(printf|fprintf|syslog)\s*\(')
RE_C_LOG_MACRO = re.compile(r'\b(LOG|LOG_[A-Z]+|SPDLOG_[A-Z]+|QLOG|DLOG|ELOG|WLOG|ILOG)\s*\(')

def _extract_string_literals_regex(line: str) -> Tuple[List[str], bool, List[str]]:
    lits: List[str] = []
    dynamic = False
    reasons: List[str] = []

    for m in RE_STR_DQ_SQ.finditer(line):
        s = m.group(0)
        # strip quotes
        if len(s) >= 2 and s[0] == s[-1] and s[0] in {"'", '"'}:
            lits.append(s[1:-1])

    # JS template literals indicate dynamic often
    if RE_TEMPLATE.search(line):
        dynamic = True
        reasons.append("js_template_literal")
        # capture raw template content (without backticks) as a literal-ish
        for m in RE_TEMPLATE.finditer(line):
            raw = m.group(0)
            if len(raw) >= 2 and raw[0] == raw[-1] == "`":
                lits.append(raw[1:-1])

    # format indicators
    if "%" in line:
        # heuristic: percent formatting tokens
        if re.search(r'%[sdifoxX]', line):
            dynamic = True
            reasons.append("percent_format_token")
    if ".format(" in line:
        dynamic = True
        reasons.append("dot_format_call")
    if "+" in line and any(q in line for q in ['"', "'", "`"]):
        # very rough concat heuristic
        dynamic = True
        reasons.append("concat_operator")

    return (_dedupe_preserve_order(lits), dynamic, _dedupe_preserve_order(reasons))


def scan_text_file_heuristic(path: Path, text: str) -> List[LogCall]:
    out: List[LogCall] = []
    ext = path.suffix.lower()

    language = {
        ".js": "javascript", ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "typescript",
        ".c": "c", ".h": "c",
        ".cc": "cpp", ".cpp": "cpp", ".hpp": "cpp",
        ".cs": "csharp",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    }.get(ext, "unknown")

    lines = text.splitlines()

    for idx, line in enumerate(lines, start=1):
        kind = None
        level = None
        callee = None

        m = RE_JS_CONSOLE.search(line)
        if m:
            kind = "js_console"
            level = m.group(1).lower()
            callee = f"console.{m.group(1)}"

        if kind is None:
            m2 = RE_GENERIC_LOGGER.search(line)
            if m2:
                kind = "generic_logger"
                level = m2.group(2).lower()
                callee = f"{m2.group(1)}.{m2.group(2)}"

        if kind is None:
            if RE_C_PRINTF.search(line):
                kind = "c_printf_family"
                level = None
                callee = "printf/fprintf/syslog"
            elif RE_C_LOG_MACRO.search(line):
                kind = "c_log_macro"
                level = None
                callee = RE_C_LOG_MACRO.search(line).group(1)

        if kind is None:
            continue

        literals, dyn, reasons = _extract_string_literals_regex(line)
        out.append(
            LogCall(
                file=str(path),
                line_no=idx,
                language=language,
                kind=kind,
                level=level,
                callee=callee,
                snippet=line.strip(),
                string_literals=literals,
                is_dynamic=dyn,
                dynamic_reasons=reasons,
            )
        )

    return out


# ---------------------------
# Main scan
# ---------------------------

def iter_files(root: Path, exts: set[str], exclude_dirs: set[str], max_bytes: int, stats: ScanStats) -> Iterable[Path]:
    for p in root.rglob("*"):
        if _is_excluded(p, exclude_dirs):
            # Only count excluded dirs once-ish; keep it simple:
            if p.is_dir():
                stats.files_skipped_excluded_dir += 1
            continue
        if not p.is_file():
            continue

        stats.files_considered += 1

        if p.suffix.lower() not in exts:
            stats.files_skipped_ext += 1
            continue

        try:
            size = p.stat().st_size
        except Exception:
            stats.files_skipped_unreadable += 1
            continue

        if size > max_bytes:
            stats.files_skipped_too_big += 1
            continue

        yield p


def scan_repo(root: Path, exts: set[str], exclude_dirs: set[str], max_bytes: int) -> Dict[str, Any]:
    import time
    start_time = time.time()
    stats = ScanStats(root=str(root))

    calls: List[LogCall] = []

    for p in iter_files(root, exts, exclude_dirs, max_bytes, stats):
        text = _safe_read_text(p)
        if text is None:
            stats.files_skipped_unreadable += 1
            continue

        stats.files_scanned += 1

        if p.suffix.lower() == ".py":
            calls.extend(scan_python_file(p, text))
        else:
            calls.extend(scan_text_file_heuristic(p, text))

    stats.elapsed_seconds = time.time() - start_time

    # Build literal catalog
    literal_to_sites: Dict[str, List[Dict[str, Any]]] = {}
    for c in calls:
        for lit in c.string_literals:
            literal_to_sites.setdefault(lit, []).append(
                {"file": c.file, "line_no": c.line_no, "callee": c.callee, "level": c.level, "kind": c.kind}
            )

    # Summaries
    by_level: Dict[str, int] = {}
    by_kind: Dict[str, int] = {}
    dynamic_count = 0

    for c in calls:
        k = c.kind or "unknown"
        by_kind[k] = by_kind.get(k, 0) + 1
        if c.level:
            by_level[c.level] = by_level.get(c.level, 0) + 1
        if c.is_dynamic:
            dynamic_count += 1

    report = {
        "scan_stats": asdict(stats),
        "summary": {
            "log_calls_found": len(calls),
            "dynamic_calls_flagged": dynamic_count,
            "calls_by_kind": dict(sorted(by_kind.items(), key=lambda kv: (-kv[1], kv[0]))),
            "calls_by_level": dict(sorted(by_level.items(), key=lambda kv: (-kv[1], kv[0]))),
            "unique_string_literals_in_calls": len(literal_to_sites),
        },
        "log_call_inventory": [asdict(c) for c in calls],
        "literal_catalog": {
            # Keep catalog deterministic, but avoid huge output blowups if desired later
            "literals": [
                {"literal": lit, "count": len(sites), "sites": sites}
                for lit, sites in sorted(literal_to_sites.items(), key=lambda kv: (-len(kv[1]), kv[0]))
            ]
        },
    }
    return report


# ---------------------------
# Output writer (UTF-8 safe)
# ---------------------------

class OutputWriter:
    """UTF-8 safe output writer for Windows compatibility."""
    def __init__(self, out_path: Optional[str] = None):
        if out_path:
            self.fp: TextIO = open(out_path, "w", encoding="utf-8", newline="\n")
            self._close = True
        else:
            # Configure stdout for UTF-8
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                # Older Python or non-reconfigurable stdout; rely on errors="replace" in dumps
                pass
            self.fp = sys.stdout
            self._close = False

    def write(self, text: str) -> None:
        try:
            self.fp.write(text)
        except UnicodeEncodeError:
            # Fallback: replace problematic chars
            self.fp.write(text.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))

    def write_json(self, obj: Any, pretty: bool = False) -> None:
        """Write JSON with UTF-8 encoding safety."""
        if pretty:
            json_str = json.dumps(obj, indent=2, ensure_ascii=False)
        else:
            json_str = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
        self.write(json_str)

    def close(self) -> None:
        if self._close:
            self.fp.close()


# ---------------------------
# Summary mode builders
# ---------------------------

def build_summary_report(
    calls: List[LogCall],
    stats: ScanStats,
    root: Path,
    context_lines: int = 0,
    occurrences_per_message: int = 5,
    allowed_levels: Optional[set[str]] = None,
) -> Dict[str, Any]:
    """Build compact summary report with deduplication."""
    if allowed_levels is None:
        allowed_levels = {"error", "exception", "critical"}

    # Filter by level if specified
    filtered_calls = [
        c for c in calls
        if c.level is None or c.level.lower() in allowed_levels
    ]

    # Group by message text (exact literal string)
    message_to_occurrences: Dict[str, List[Dict[str, Any]]] = {}
    level_counts: Dict[str, int] = {}

    for c in filtered_calls:
        # Use first string literal as the message key (or snippet if no literals)
        if c.string_literals:
            msg_key = c.string_literals[0]
        else:
            # Fallback to snippet (truncated) for calls without string literals
            msg_key = c.snippet[:100].strip() if c.snippet else None
        if not msg_key:
            continue

        level = (c.level or "unknown").lower()
        level_counts[level] = level_counts.get(level, 0) + 1

        # Determine kind (literal vs template)
        kind = "template" if c.is_dynamic else "literal"

        # Build occurrence entry
        occ = {
            "path": str(c.file),
            "line_no": c.line_no,
            "enclosure": None,  # Will be filled if context_lines > 0
            "logger_call": c.callee or c.kind,
        }

        # Add context preview if requested
        if context_lines > 0:
            text = _safe_read_text(Path(c.file))
            if text:
                lines = text.splitlines()
                start = max(1, c.line_no - context_lines)
                end = min(len(lines), c.line_no + context_lines)
                context_preview = "\n".join(lines[start - 1:end])
                occ["context_preview"] = context_preview

        message_to_occurrences.setdefault(msg_key, []).append(occ)

    # Build messages list (deduped, sorted by count desc)
    messages = []
    for msg, occs in sorted(message_to_occurrences.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        # Determine kind from first occurrence
        first_call = next(
            (c for c in filtered_calls if
             (c.string_literals and c.string_literals[0] == msg) or
             (not c.string_literals and c.snippet[:100].strip() == msg)),
            None
        )
        kind = "template" if (first_call and first_call.is_dynamic) else "literal"
        level = (first_call.level or "unknown").lower() if first_call else "unknown"

        # Sample occurrences (limit to occurrences_per_message)
        sample = occs[:occurrences_per_message]

        messages.append({
            "message": msg,
            "kind": kind,
            "level": level,
            "count": len(occs),
            "unique_files": len(set(o["path"] for o in occs)),
            "occurrences_sample": sample,
        })

    return {
        "meta": {
            "tool": "logInv",
            "version": "1.0",
            "root": str(root),
            "generated_at": datetime.utcnow().isoformat() + "Z",
        },
        "scan": {
            "files_scanned": stats.files_scanned,
            "files_skipped_excluded_dir": stats.files_skipped_excluded_dir,
            "files_skipped_ext": stats.files_skipped_ext,
            "files_skipped_too_big": stats.files_skipped_too_big,
            "files_skipped_unreadable": stats.files_skipped_unreadable,
            "elapsed_seconds": getattr(stats, "elapsed_seconds", 0.0),
        },
        "stats": {
            "unique_messages": len(messages),
            "total_occurrences": sum(m["count"] for m in messages),
            "levels": level_counts,
        },
        "messages": messages,
    }


def build_jsonl_report(calls: List[LogCall], context_lines: int = 0, allowed_levels: Optional[set[str]] = None) -> Iterable[Dict[str, Any]]:
    """Build JSONL (one JSON object per line) report."""
    if allowed_levels is None:
        allowed_levels = {"error", "exception", "critical"}

    for c in calls:
        if c.level and c.level.lower() not in allowed_levels:
            continue

        rec = {
            "path": str(c.file),
            "line_no": c.line_no,
            "language": c.language,
            "kind": c.kind,
            "level": c.level,
            "callee": c.callee,
            "snippet": c.snippet,
            "message": c.string_literals[0] if c.string_literals else None,
            "is_dynamic": c.is_dynamic,
        }

        if context_lines > 0:
            text = _safe_read_text(Path(c.file))
            if text:
                lines = text.splitlines()
                start = max(1, c.line_no - context_lines)
                end = min(len(lines), c.line_no + context_lines)
                rec["context_preview"] = "\n".join(lines[start - 1:end])

        yield rec


def main() -> int:
    # READ-ONLY enforcement: prevent bytecode writes
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        sys.dont_write_bytecode = True
    except Exception:
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="Root folder to scan (read-only).")
    ap.add_argument("--max-file-bytes", type=int, default=DEFAULT_MAX_FILE_BYTES)
    ap.add_argument("--include-ext", default=",".join(sorted(DEFAULT_EXTS)),
                    help="Comma-separated extensions to scan (e.g. .py,.js,.cpp).")
    ap.add_argument("--exclude-dirs", default=",".join(sorted(DEFAULT_EXCLUDE_DIRS)),
                    help="Comma-separated directory names to exclude (e.g. .git,node_modules).")
    ap.add_argument("--pretty", action="store_true", help="Pretty-print JSON (ignored in summary mode).")
    ap.add_argument("--out", help="Output file path (UTF-8). If not provided, write to stdout.")
    ap.add_argument("--format", choices=["summary", "json", "jsonl"], default="summary",
                    help="Output format: summary (compact, deduped), json (full structured), jsonl (one record per line).")
    ap.add_argument("--context-lines", type=int, default=0,
                    help="Include N lines before/after matched line in context_preview (0 = disabled).")
    ap.add_argument("--occurrences-per-message", type=int, default=5,
                    help="Max sample occurrences per unique message in summary mode.")
    ap.add_argument("--levels", default="error,exception,critical",
                    help="Comma-separated log levels to include (e.g. error,warning,info,debug).")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.exists() or not root.is_dir():
        print(f"ERROR: --root must be an existing directory: {root}", file=sys.stderr)
        return 2

    exts = {e.strip() for e in args.include_ext.split(",") if e.strip()}
    exclude_dirs = {d.strip() for d in args.exclude_dirs.split(",") if d.strip()}
    allowed_levels = {l.strip().lower() for l in args.levels.split(",") if l.strip()}

    # Scan repository (read-only)
    report_data = scan_repo(root=root, exts=exts, exclude_dirs=exclude_dirs, max_bytes=args.max_file_bytes)
    calls = [LogCall(**d) for d in report_data["log_call_inventory"]]
    stats = ScanStats(**report_data["scan_stats"])

    # Build output based on format
    writer = OutputWriter(args.out)
    try:
        if args.format == "summary":
            summary = build_summary_report(
                calls=calls,
                stats=stats,
                root=root,
                context_lines=args.context_lines,
                occurrences_per_message=args.occurrences_per_message,
                allowed_levels=allowed_levels,
            )
            writer.write_json(summary, pretty=args.pretty)
        elif args.format == "jsonl":
            # JSONL: one JSON object per line
            for rec in build_jsonl_report(calls, context_lines=args.context_lines, allowed_levels=allowed_levels):
                writer.write_json(rec, pretty=False)
                writer.write("\n")
        else:  # json
            # Full JSON report (but respect context_lines)
            if args.context_lines == 0:
                # Remove context_preview from full report if not requested
                for c_dict in report_data["log_call_inventory"]:
                    c_dict.pop("context_preview", None)
            writer.write_json(report_data, pretty=args.pretty)
    finally:
        writer.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
