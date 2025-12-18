from __future__ import absolute_import, print_function

import argparse
import os
import sys


def _ensure_src_on_syspath():
    # Allow running directly as: python tools/dev/run_search_demo.py
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
    src_dir = os.path.join(repo_root, "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    return repo_root


def build_parser(default_root):
    p = argparse.ArgumentParser(
        prog="run_search_demo",
        description="Dev-only demo: parse log text then search a sample repo (read-only).",
    )
    p.add_argument(
        "--roots",
        action="append",
        default=[default_root],
        help="Repeatable. Search roots (default: tests/fixtures/sample_repo).",
    )
    p.add_argument(
        "--log",
        default=None,
        help="Log snippet or block. If omitted, uses a hardcoded sample with <E>.",
    )
    p.add_argument(
        "--max-results",
        type=int,
        default=None,
        help="Maximum results to return (omit for unlimited).",
    )
    p.add_argument(
        "--case-insensitive",
        action="store_true",
        default=False,
        help="Case-insensitive matching.",
    )
    p.add_argument(
        "--with-extract",
        action="store_true",
        default=False,
        help="Also extract enclosing def/class for the top match and print the block.",
    )
    return p


def main(argv=None):
    repo_root = _ensure_src_on_syspath()

    default_root = os.path.join(repo_root, "tests", "fixtures", "sample_repo")
    args = build_parser(default_root).parse_args(argv)

    from arrow_log_helper import analyzer
    from arrow_log_helper import config_defaults

    sample_block = "\n".join(
        [
            "Random header line",
            "2025-12-19T05:22:06.751222+11:00 RS20300529 Kareela0: <I> [#4] EngineConductor: Changing state from EngineConductor::State::IDLE to EngineConductor::State::SERVICING on periodic idle maint",
            "2025-12-19T05:22:06.895453+11:00 RS20300529 Kareela0: <E> [#4] PeriodicIdle: waitComplete for localhost:9210:Dyn-ultron:VALVE",
            "",
        ]
    )

    roots = args.roots or [default_root]
    exclude_dirs = list(getattr(config_defaults, "DEFAULT_EXCLUDE_DIRS", []))

    log_text = args.log if args.log is not None else sample_block
    result = analyzer.analyze(
        log_text,
        settings={
            "roots": roots,
            "exclude_dirs": exclude_dirs,
            "case_insensitive": bool(args.case_insensitive),
            "max_results": args.max_results,
            "max_file_bytes": getattr(config_defaults, "DEFAULT_MAX_FILE_BYTES", 10 * 1024 * 1024),
            "max_seconds": None,
            "max_files_scanned": None,
            "context_fallback": 50,
        },
    )
    matches = result.get("matches") or []
    stats = result.get("scan_stats") or {}

    print("Selected line:")
    print(result.get("selected_line", ""))
    print("")
    print("search_message: %s" % (result.get("search_message", ""),))
    print("")
    print("Matches:")
    shown = 0
    for m in matches:
        shown += 1
        if shown > 25:
            break
        print(
            "  %s:%s  |  %s"
            % (
                m.get("path", "?"),
                m.get("line_no", "?"),
                m.get("signature") or "<no def> (context)",
            )
        )

    if args.with_extract and matches:
        top = matches[0]
        print("")
        print("Top detail:")
        print("  match_type: %s" % (top.get("match_type"),))
        print("  signature: %s" % (top.get("signature"),))
        if not top.get("signature"):
            print("")
            print(top.get("context_preview") or "")
    print("")
    print("Scan stats:")
    for k in sorted(stats.keys()):
        print("  %s: %s" % (k, stats.get(k)))

    return 0


if __name__ == "__main__":
    sys.exit(main())


