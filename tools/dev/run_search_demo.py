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
        default=10,
        help="Maximum results to return.",
    )
    p.add_argument(
        "--case-insensitive",
        action="store_true",
        default=False,
        help="Case-insensitive matching.",
    )
    return p


def main(argv=None):
    repo_root = _ensure_src_on_syspath()

    default_root = os.path.join(repo_root, "tests", "fixtures", "sample_repo")
    args = build_parser(default_root).parse_args(argv)

    from arrow_log_helper import parse_log
    from arrow_log_helper import search_code
    from arrow_log_helper import config_defaults

    sample_block = "\n".join(
        [
            "Random header line",
            "2025-12-19T05:22:06.751222+11:00 RS20300529 Kareela0: <I> [#4] EngineConductor: Changing state from EngineConductor::State::IDLE to EngineConductor::State::SERVICING on periodic idle maint",
            "2025-12-19T05:22:06.895453+11:00 RS20300529 Kareela0: <E> [#4] PeriodicIdle: waitComplete for localhost:9210:Dyn-ultron:VALVE",
            "",
        ]
    )

    log_text = args.log if args.log is not None else sample_block
    parsed = parse_log.analyze_pasted_text(log_text, normalize_numbers=False)

    roots = args.roots or [default_root]
    include_exts = list(getattr(config_defaults, "DEFAULT_INCLUDE_EXT", [".py"]))
    exclude_dirs = list(getattr(config_defaults, "DEFAULT_EXCLUDE_DIRS", []))

    matches = search_code.search_in_roots(
        roots=roots,
        key_exact=parsed.get("key_exact"),
        key_normalized=parsed.get("key_normalized"),
        tokens=parsed.get("tokens") or [],
        component=parsed.get("component"),
        include_exts=include_exts,
        exclude_dir_names=exclude_dirs,
        case_insensitive=bool(args.case_insensitive),
        max_results=int(args.max_results),
        follow_symlinks=False,
        max_file_bytes=getattr(config_defaults, "DEFAULT_MAX_FILE_BYTES", search_code.DEFAULT_MAX_FILE_BYTES),
    )

    print("Selected line:")
    print(parsed.get("selected_line", ""))
    print("")
    print("key_exact: %s" % (parsed.get("key_exact", ""),))
    print("key_normalized: %s" % (parsed.get("key_normalized", ""),))
    print("")
    print("Matches:")
    for m in matches:
        print(
            "  %.2f %-10s %s:%s  %s"
            % (
                float(m.get("score", 0.0)),
                m.get("match_type", "?"),
                m.get("path", "?"),
                m.get("line_no", "?"),
                m.get("line_text", ""),
            )
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())


