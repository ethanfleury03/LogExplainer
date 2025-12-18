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


EXAMPLE_I = (
    "2025-12-19T05:22:06.751222+11:00 RS20300529 Kareela0: <I> [#4] "
    "EngineConductor: Changing state from EngineConductor::State::IDLE to "
    "EngineConductor::State::SERVICING on periodic idle maint"
)

EXAMPLE_E = (
    "2025-12-19T05:22:06.895453+11:00 RS20300529 Kareela0: <E> [#4] "
    "PeriodicIdle: waitComplete for localhost:9210:Dyn-ultron:VALVE"
)


class ParseLogTest(unittest.TestCase):
    def test_full_example_parses_component_level_message(self):
        out = parse_log.analyze_pasted_text(EXAMPLE_I)
        self.assertEqual(out.get("level"), "I")
        self.assertEqual(out.get("component"), "EngineConductor")
        self.assertTrue(out.get("message"))

    def test_block_selects_first_error_line(self):
        block = "\n".join(
            [
                " ",
                EXAMPLE_I,
                EXAMPLE_E,
                "2025-12-19T05:22:06.999999+11:00 RS20300529 Kareela0: <E> [#1] Other: later",
            ]
        )
        out = parse_log.analyze_pasted_text(block)
        self.assertIn("<E>", out.get("selected_line", ""))
        self.assertEqual(out.get("level"), "E")
        self.assertEqual(out.get("component"), "PeriodicIdle")

    def test_weird_line_no_timestamp_still_returns_keys(self):
        weird = "PeriodicIdle: valve failed on localhost:9210 code 12345"
        out = parse_log.analyze_pasted_text(weird)
        self.assertTrue(out.get("message"))
        self.assertTrue(out.get("key_normalized"))


if __name__ == "__main__":
    unittest.main()


