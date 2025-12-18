from __future__ import absolute_import

import os
import sys
import unittest


# Ensure src/ is importable when running tests directly.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
SRC_DIR = os.path.join(REPO_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


from arrow_log_helper import extract_enclosure  # noqa: E402
from arrow_log_helper import parse_log  # noqa: E402
from arrow_log_helper import search_code  # noqa: E402


SAMPLE_BLOCK = "\n".join(
    [
        "header",
        "2025-12-19T05:22:06.895453+11:00 RS20300529 Kareela0: <E> [#4] PeriodicIdle: waitComplete for localhost:9210:Dyn-ultron:VALVE",
    ]
)


class ExtractEnclosureTest(unittest.TestCase):
    def _fixture_root(self):
        return os.path.join(REPO_ROOT, "tests", "fixtures", "sample_repo")

    def test_extract_def(self):
        parsed = parse_log.analyze_pasted_text(SAMPLE_BLOCK)
        res, stats = search_code.search_message_exact_in_roots(
            roots=[self._fixture_root()],
            message=parsed.get("search_message"),
            include_exts=[".py"],
            exclude_dir_names=["__pycache__"],
            case_insensitive=False,
            max_results=5,
        )
        self.assertTrue(res, msg="Expected at least 1 match in fixtures")
        top = res[0]

        enc = extract_enclosure.extract_enclosure(top.get("path"), top.get("line_no"))
        self.assertEqual(enc.get("enclosure_type"), "def")
        self.assertIn("def do_periodic_idle", enc.get("block", ""))
        self.assertIn("PeriodicIdle: waitComplete for localhost:9210:Dyn-ultron:VALVE", enc.get("block", ""))

    def test_fallback_window(self):
        path = os.path.join(self._fixture_root(), "top_level_only.py")
        # logger.error is on line 4 in this fixture (after future import + comment).
        enc = extract_enclosure.extract_enclosure(path, 4, context_fallback=2)
        self.assertEqual(enc.get("enclosure_type"), "none")
        self.assertIn("very_unique_marker_123456", enc.get("block", ""))


if __name__ == "__main__":
    unittest.main()


