from __future__ import absolute_import, print_function

import argparse
import os
import sys

# Prevent pycache creation on target machine
sys.dont_write_bytecode = True

TEST_LOG_LINE = "2025-12-19T05:22:06.895453+11:00 RS20300529 Kareela0: <E> [#4] PeriodicIdle: waitComplete for localhost:9210:Dyn-ultron:VALVE"


def _repo_root():
    return os.path.abspath(os.path.dirname(__file__))


def _ensure_src_on_syspath(repo_root):
    src_dir = os.path.join(repo_root, "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    return src_dir


def _print_startup(repo_root, src_dir):
    # Keep this short and predictable; technicians often want a quick sanity line.
    try:
        sys.stderr.write("Python: %s\n" % (sys.version.replace("\n", " "),))
    except Exception:
        pass
    try:
        sys.stderr.write("Starting Arrow Log Helper from: %s\n" % (repo_root,))
        sys.stderr.write("Using src path: %s\n" % (src_dir,))
    except Exception:
        pass


def _parse_args(argv):
    """Parse command line arguments."""
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument(
        "--test",
        action="store_true",
        default=False,
        help="Launch GUI with a pre-filled demo log line (no auto-run).",
    )
    return ap.parse_args(argv)


def _print_help():
    msg = "\n".join(
        [
            "Arrow Log Helper (scaffold)",
            "",
            "Usage:",
            "  python RUN_ME.py",
            "  python RUN_ME.py --test  # Launch with pre-filled demo log",
            "",
            "Dev / CI:",
            "  ARROW_LOG_HELPER_NO_GUI=1 python RUN_ME.py",
            "",
        ]
    )
    try:
        sys.stdout.write(msg)
    except Exception:
        pass


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    # Basic help support without adding dependencies or a full CLI.
    if "-h" in argv or "--help" in argv:
        _print_help()
        return 0

    # Parse arguments
    try:
        args = _parse_args(argv)
    except SystemExit:
        # argparse already printed help/error
        return 1

    repo_root = _repo_root()
    src_dir = _ensure_src_on_syspath(repo_root)
    _print_startup(repo_root, src_dir)

    if os.environ.get("ARROW_LOG_HELPER_NO_GUI") == "1":
        # Dev-only: allow smoke checks on machines without a display.
        sys.stdout.write("NO_GUI mode\n")
        return 0

    # Determine prefill log
    prefill_log = TEST_LOG_LINE if args.test else None

    # Launch via the package entrypoint so safety bootstrap + write firewall is installed.
    from arrow_log_helper import __main__ as alh_main

    # Pass prefill_log through environment variable (simple approach)
    if prefill_log:
        os.environ["ARROW_LOG_HELPER_PREFILL_LOG"] = prefill_log

    return int(alh_main.main([]) or 0)


if __name__ == "__main__":
    sys.exit(main())


