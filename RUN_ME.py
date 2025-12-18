from __future__ import absolute_import, print_function

import os
import sys


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


def _print_help():
    msg = "\n".join(
        [
            "Arrow Log Helper (scaffold)",
            "",
            "Usage:",
            "  python RUN_ME.py",
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

    repo_root = _repo_root()
    src_dir = _ensure_src_on_syspath(repo_root)
    _print_startup(repo_root, src_dir)

    if os.environ.get("ARROW_LOG_HELPER_NO_GUI") == "1":
        # Dev-only: allow smoke checks on machines without a display.
        sys.stdout.write("NO_GUI mode\n")
        return 0

    from arrow_log_helper import gui

    return int(gui.main([]) or 0)


if __name__ == "__main__":
    sys.exit(main())


