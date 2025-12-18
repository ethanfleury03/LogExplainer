from __future__ import absolute_import, print_function

import argparse
import sys


def build_parser():
    parser = argparse.ArgumentParser(
        prog="log_explainer",
        description="LogExplainer (V0 scaffolding only; no logic yet).",
    )

    parser.add_argument(
        "--roots",
        action="append",
        default=[],
        help="Repeatable. Search root directories (unused in V0).",
    )
    parser.add_argument(
        "--log",
        default=None,
        help="Log snippet or path (unused in V0).",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=20,
        help="Maximum results to return (unused in V0).",
    )
    parser.add_argument(
        "--case-insensitive",
        action="store_true",
        default=False,
        help="Case-insensitive search (unused in V0).",
    )
    parser.add_argument(
        "--include-ext",
        action="append",
        default=[],
        help="Repeatable. File extensions to include (unused in V0).",
    )
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help="Repeatable. Directory names to exclude (unused in V0).",
    )

    return parser


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    parser = build_parser()
    args = parser.parse_args(argv)

    print("Not implemented yet (scaffolding only).")
    print(args)

    # Exit code 2 to clearly indicate "not implemented" state.
    return 2


if __name__ == "__main__":
    sys.exit(main())


