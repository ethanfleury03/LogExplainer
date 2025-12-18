from __future__ import absolute_import, print_function

import os
import pprint
import sys


def _ensure_src_on_syspath():
    # Allow running directly as: python tools/dev/run_parse_demo.py
    # from the repo root (LogExplainer/).
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
    src_dir = os.path.join(repo_root, "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    return repo_root, src_dir


def main():
    repo_root, src_dir = _ensure_src_on_syspath()
    from arrow_log_helper import parse_log

    sample_block = "\n".join(
        [
            "Random header line",
            "2025-12-19T05:22:06.751222+11:00 RS20300529 Kareela0: <I> [#4] EngineConductor: Changing state from EngineConductor::State::IDLE to EngineConductor::State::SERVICING on periodic idle maint",
            "2025-12-19T05:22:06.895453+11:00 RS20300529 Kareela0: <E> [#4] PeriodicIdle: waitComplete for localhost:9210:Dyn-ultron:VALVE",
            "",
        ]
    )

    result = parse_log.analyze_pasted_text(sample_block, normalize_numbers=False)

    print("Repo root: %s" % (repo_root,))
    print("Using src: %s" % (src_dir,))
    print("")
    print("Selected line:")
    print(result.get("selected_line", ""))
    print("")
    print("Result dict:")
    pprint.pprint(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())


