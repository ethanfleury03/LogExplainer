from __future__ import absolute_import

import os
import sys
import unittest


# Ensure src/ is importable when running tests directly.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
SRC_DIR = os.path.join(REPO_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


from arrow_log_helper import parse_log  # noqa: E402
from arrow_log_helper import search_code  # noqa: E402


SAMPLE_BLOCK = "\n".join(
    [
        "header",
        "2025-12-19T05:22:06.895453+11:00 RS20300529 Kareela0: <E> [#4] PeriodicIdle: waitComplete for localhost:9210:Dyn-ultron:VALVE",
    ]
)


class ProgressCallbackTest(unittest.TestCase):
    def _fixture_root(self):
        return os.path.join(REPO_ROOT, "tests", "fixtures", "sample_repo")

    def test_progress_cb_called(self):
        parsed = parse_log.analyze_pasted_text(SAMPLE_BLOCK)

        calls = {"n": 0}

        def cb(stats):
            calls["n"] += 1

        res, stats = search_code.search_message_exact_in_roots(
            roots=[self._fixture_root()],
            message=parsed.get("search_message"),
            include_exts=[".py"],
            exclude_dir_names=["__pycache__"],
            case_insensitive=False,
            max_results=10,
            progress_cb=cb,
            progress_every_n_files=1,
        )

        self.assertGreaterEqual(calls["n"], 2, msg="Expected start/end progress callbacks")


if __name__ == "__main__":
    unittest.main()


