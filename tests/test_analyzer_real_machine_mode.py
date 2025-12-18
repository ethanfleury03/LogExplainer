from __future__ import absolute_import

import os
import sys
import unittest


# Ensure src/ is importable when running tests directly.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
SRC_DIR = os.path.join(REPO_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


from arrow_log_helper import analyzer  # noqa: E402


E_LINE = "2025-12-19T05:22:06.895453+11:00 RS20300529 Kareela0: <E> [#4] PeriodicIdle: waitComplete for localhost:9210:Dyn-ultron:VALVE"


class AnalyzerRealMachineModeTest(unittest.TestCase):
    def _fixture_root(self):
        return os.path.join(REPO_ROOT, "tests", "fixtures", "sample_repo")

    def test_message_only_returns_multiple_signatures(self):
        res = analyzer.analyze(
            E_LINE,
            settings={
                "roots": [self._fixture_root()],
                "exclude_dirs": ["__pycache__"],
                "case_insensitive": False,
                "max_results": None,
                "max_seconds": None,
                "max_files_scanned": None,
                "context_fallback": 10,
            },
        )
        matches = res.get("matches") or []
        # The message substring appears in two different defs in module_a.py.
        self.assertGreaterEqual(len(matches), 2)
        sigs = [m.get("signature") for m in matches if m.get("signature")]
        self.assertIn("def do_periodic_idle(logger):", sigs)
        self.assertIn("def do_periodic_idle_second(logger):", sigs)


if __name__ == "__main__":
    unittest.main()


