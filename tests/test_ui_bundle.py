from __future__ import absolute_import

import os
import sys
import unittest

# Ensure src/ is importable when running tests directly.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
SRC_DIR = os.path.join(REPO_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from arrow_log_helper import ui_bundle  # noqa: E402
from arrow_log_helper import analyzer  # noqa: E402


class UIBundleTest(unittest.TestCase):
    def test_build_ui_bundle_minimal(self):
        """Test build_ui_bundle with minimal/mock data."""
        analysis_result = {
            "selected_line": "test log line",
            "parsed": {
                "component": "TestComponent",
                "message": "test message",
            },
            "search_message": "test search",
            "matches": [],
            "scan_stats": {
                "files_scanned": 0,
                "hits_found": 0,
                "elapsed_seconds": 0.0,
            },
        }
        
        bundle = ui_bundle.build_ui_bundle(analysis_result, None)
        
        # Assert required keys
        self.assertIn("input", bundle)
        self.assertIn("parsed", bundle)
        self.assertIn("scan", bundle)
        self.assertIn("matches", bundle)
        self.assertIn("selected", bundle)
        
        # Assert structure
        self.assertEqual(bundle["input"]["selected_line"], "test log line")
        self.assertEqual(bundle["parsed"]["component"], "TestComponent")
        self.assertEqual(len(bundle["matches"]), 0)
        self.assertIsNone(bundle["selected"])

    def test_build_ui_bundle_with_matches(self):
        """Test build_ui_bundle with matches and selected index."""
        analysis_result = {
            "selected_line": "test log",
            "parsed": {
                "component": "TestComp",
            },
            "search_message": "waitComplete",
            "matches": [
                {
                    "path": "/path/to/file.py",
                    "line_no": 42,
                    "line_text": "    logger.info('waitComplete for localhost')",
                    "match_type": "exact_message",
                    "score": 0.95,
                    "enclosure_type": "def",
                    "name": "do_periodic_idle",
                    "signature": "def do_periodic_idle(logger):",
                    "start_line": 40,
                    "end_line": 50,
                },
                {
                    "path": "/path/to/other.py",
                    "line_no": 100,
                    "line_text": "    print('waitComplete')",
                    "match_type": "exact_message",
                    "score": 0.85,
                    "enclosure_type": "none",
                    "name": None,
                    "signature": None,
                    "context_preview": "some context",
                },
            ],
            "scan_stats": {
                "files_scanned": 10,
                "hits_found": 2,
                "elapsed_seconds": 0.5,
            },
        }
        
        bundle = ui_bundle.build_ui_bundle(analysis_result, 0)
        
        # Assert matches processed
        self.assertEqual(len(bundle["matches"]), 2)
        
        # Assert first match has computed fields
        match0 = bundle["matches"][0]
        self.assertEqual(match0["confidence_percent"], 95)  # 0.95 * 100
        self.assertEqual(match0["location_short"], "file.py:42")
        self.assertEqual(match0["enclosure_display_name"], "def do_periodic_idle(logger):")
        self.assertIn("Function/Enclosure:", match0["summary_text"])
        self.assertIn("Match info:", match0["summary_text"])
        
        # Assert selected match is first one
        self.assertIsNotNone(bundle["selected"])
        self.assertEqual(bundle["selected"]["path"], "/path/to/file.py")
        
        # Test selecting second match
        bundle2 = ui_bundle.build_ui_bundle(analysis_result, 1)
        self.assertEqual(bundle2["selected"]["path"], "/path/to/other.py")
        self.assertEqual(bundle2["selected"]["confidence_percent"], 85)

    def test_build_ui_bundle_no_selection(self):
        """Test build_ui_bundle with matches but no selection."""
        analysis_result = {
            "selected_line": "test",
            "parsed": {},
            "search_message": "test",
            "matches": [
                {
                    "path": "file.py",
                    "line_no": 1,
                    "line_text": "test",
                    "match_type": "exact",
                    "score": 0.9,
                },
            ],
            "scan_stats": {},
        }
        
        bundle = ui_bundle.build_ui_bundle(analysis_result, None)
        self.assertEqual(len(bundle["matches"]), 1)
        self.assertIsNone(bundle["selected"])

    def test_confidence_percent_computation(self):
        """Test confidence_percent is computed correctly."""
        analysis_result = {
            "selected_line": "test",
            "parsed": {},
            "search_message": "test",
            "matches": [
                {"path": "f.py", "line_no": 1, "line_text": "t", "match_type": "exact", "score": 0.0},
                {"path": "f.py", "line_no": 2, "line_text": "t", "match_type": "exact", "score": 0.5},
                {"path": "f.py", "line_no": 3, "line_text": "t", "match_type": "exact", "score": 1.0},
                {"path": "f.py", "line_no": 4, "line_text": "t", "match_type": "exact", "score": 0.876},
            ],
            "scan_stats": {},
        }
        
        bundle = ui_bundle.build_ui_bundle(analysis_result, None)
        matches = bundle["matches"]
        self.assertEqual(matches[0]["confidence_percent"], 0)  # 0.0 -> 0
        self.assertEqual(matches[1]["confidence_percent"], 50)  # 0.5 -> 50
        self.assertEqual(matches[2]["confidence_percent"], 100)  # 1.0 -> 100
        self.assertEqual(matches[3]["confidence_percent"], 88)  # 0.876 -> 88 (rounded)

    def test_location_short_formatting(self):
        """Test location_short is formatted correctly."""
        analysis_result = {
            "selected_line": "test",
            "parsed": {},
            "search_message": "test",
            "matches": [
                {"path": "/long/path/to/file.py", "line_no": 42, "line_text": "t", "match_type": "exact", "score": 0.9},
                {"path": "relative.py", "line_no": 100, "line_text": "t", "match_type": "exact", "score": 0.9},
            ],
            "scan_stats": {},
        }
        
        bundle = ui_bundle.build_ui_bundle(analysis_result, None)
        matches = bundle["matches"]
        self.assertEqual(matches[0]["location_short"], "file.py:42")
        self.assertEqual(matches[1]["location_short"], "relative.py:100")

    def test_enclosure_display_name(self):
        """Test enclosure_display_name formatting."""
        analysis_result = {
            "selected_line": "test",
            "parsed": {},
            "search_message": "test",
            "matches": [
                {
                    "path": "f.py",
                    "line_no": 1,
                    "line_text": "t",
                    "match_type": "exact",
                    "score": 0.9,
                    "enclosure_type": "def",
                    "name": "test_func",
                    "signature": "def test_func(arg1, arg2):",
                },
                {
                    "path": "f.py",
                    "line_no": 2,
                    "line_text": "t",
                    "match_type": "exact",
                    "score": 0.9,
                    "enclosure_type": "def",
                    "name": "test_func2",
                    "signature": None,
                },
                {
                    "path": "f.py",
                    "line_no": 3,
                    "line_text": "t",
                    "match_type": "exact",
                    "score": 0.9,
                    "enclosure_type": "class",
                    "name": "TestClass",
                    "signature": None,
                },
                {
                    "path": "f.py",
                    "line_no": 4,
                    "line_text": "t",
                    "match_type": "exact",
                    "score": 0.9,
                    "enclosure_type": "none",
                    "name": None,
                    "signature": None,
                },
            ],
            "scan_stats": {},
        }
        
        bundle = ui_bundle.build_ui_bundle(analysis_result, None)
        matches = bundle["matches"]
        self.assertEqual(matches[0]["enclosure_display_name"], "def test_func(arg1, arg2):")
        self.assertEqual(matches[1]["enclosure_display_name"], "def test_func2(...)")
        self.assertEqual(matches[2]["enclosure_display_name"], "class TestClass")
        self.assertEqual(matches[3]["enclosure_display_name"], "<none>")

    def test_pretty_json(self):
        """Test pretty_json function."""
        obj = {
            "key1": "value1",
            "key2": [1, 2, 3],
            "key3": {"nested": "data"},
        }
        
        result = ui_bundle.pretty_json(obj)
        
        # Should be valid JSON
        import json
        parsed = json.loads(result)
        self.assertEqual(parsed["key1"], "value1")
        
        # Should be indented (contains newlines)
        self.assertIn("\n", result)
        
        # Should have sorted keys
        self.assertTrue(result.index("key1") < result.index("key2"))
        self.assertTrue(result.index("key2") < result.index("key3"))

    def test_pretty_json_with_special_types(self):
        """Test pretty_json handles sets, bytes, etc."""
        obj = {
            "a_set": set([1, 2, 3]),
            "a_bytes": b"test bytes",
        }
        
        result = ui_bundle.pretty_json(obj)
        # Should not raise, should produce valid JSON
        import json
        parsed = json.loads(result)
        self.assertIn("a_set", parsed)
        self.assertIn("a_bytes", parsed)

    def test_build_ui_bundle_with_real_fixture(self):
        """Test with real analyzer output if fixtures available."""
        fixture_root = os.path.join(REPO_ROOT, "tests", "fixtures", "sample_repo")
        if not os.path.isdir(fixture_root):
            self.skipTest("Fixture root not available")
        
        log_line = "2025-12-19T05:22:06.895453+11:00 RS20300529 Kareela0: <E> [#4] PeriodicIdle: waitComplete for localhost:9210:Dyn-ultron:VALVE"
        
        result = analyzer.analyze(
            log_line,
            settings={
                "roots": [fixture_root],
                "exclude_dirs": ["__pycache__"],
                "max_results": 5,
            },
        )
        
        bundle = ui_bundle.build_ui_bundle(result, 0)
        
        # Assert structure
        self.assertIn("input", bundle)
        self.assertIn("matches", bundle)
        
        # If matches found, verify they have computed fields
        if bundle["matches"]:
            match = bundle["matches"][0]
            self.assertIn("confidence_percent", match)
            self.assertIn("location_short", match)
            self.assertIn("summary_text", match)


if __name__ == "__main__":
    unittest.main()

