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


class ExtractEnclosureMetadataTest(unittest.TestCase):
    """Regression test for decorator + async def + docstring + containment validation."""
    
    def _fixture_path(self):
        return os.path.join(REPO_ROOT, "tests", "fixtures", "rag_api_snippet.py")
    
    def test_startup_event_enclosure_with_metadata(self):
        """
        Regression test: Ensure enclosure extraction returns correct async def startup_event()
        with decorator, docstring, and validates containment.
        """
        fixture_path = self._fixture_path()
        if not os.path.exists(fixture_path):
            self.skipTest("Fixture file not found: %s" % (fixture_path,))
        
        # Find the match line (logger.error with RAG message)
        with open(fixture_path, "rb") as f:
            lines = f.readlines()
        
        match_line_no = None
        for i, line in enumerate(lines, 1):
            if b"[RAG] Index download failed" in line:
                match_line_no = i
                break
        
        self.assertIsNotNone(match_line_no, "Could not find match line in fixture")
        
        # Call the public API (same as GUI/analyzer uses)
        enc = extract_enclosure.extract_enclosure(fixture_path, match_line_no)
        
        # Assert enclosure type
        self.assertEqual(enc.get("enclosure_type"), "async_def",
                        "Expected async_def, got %s" % (enc.get("enclosure_type"),))
        
        # Assert function name
        self.assertEqual(enc.get("name"), "startup_event",
                        "Expected startup_event, got %s" % (enc.get("name"),))
        
        # Assert def_line_text (clean, no decorators)
        def_line_text = enc.get("def_line_text")
        self.assertIsNotNone(def_line_text, "def_line_text should not be None")
        self.assertTrue(def_line_text.startswith("async def startup_event"),
                       "def_line_text should start with 'async def startup_event', got: %s" % (def_line_text,))
        self.assertNotIn("@", def_line_text, "def_line_text should not contain decorators")
        
        # Assert decorator_lines
        decorator_lines = enc.get("decorator_lines", [])
        self.assertEqual(len(decorator_lines), 1,
                        "Expected 1 decorator line, got %d" % (len(decorator_lines),))
        self.assertIn("@app.on_event", decorator_lines[0],
                     "decorator_lines should contain @app.on_event")
        self.assertIn('"startup"', decorator_lines[0],
                     "decorator_lines should contain 'startup'")
        
        # Assert docstring
        docstring_text = enc.get("docstring_text")
        self.assertIsNotNone(docstring_text, "docstring_text should not be None")
        self.assertIn("FastAPI startup event handler", docstring_text,
                      "docstring_text should contain 'FastAPI startup event handler'")
        self.assertIsNotNone(enc.get("docstring_start_line"), "docstring_start_line should not be None")
        self.assertIsNotNone(enc.get("docstring_end_line"), "docstring_end_line should not be None")
        
        # Assert containment validation flag
        contains_match = enc.get("enclosure_contains_match")
        self.assertTrue(contains_match,
                       "enclosure_contains_match should be True, got %s" % (contains_match,))
        
        # Assert containment (start_line <= match_line_no <= end_line)
        start_line = enc.get("start_line")
        end_line = enc.get("end_line")
        self.assertIsNotNone(start_line, "start_line should not be None")
        self.assertIsNotNone(end_line, "end_line should not be None")
        self.assertLessEqual(start_line, match_line_no,
                            "start_line (%d) should be <= match_line_no (%d)" % (start_line, match_line_no))
        self.assertGreaterEqual(end_line, match_line_no,
                               "end_line (%d) should be >= match_line_no (%d)" % (end_line, match_line_no))
        
        # Assert line numbers
        def_line_no = enc.get("def_line_no")
        self.assertIsNotNone(def_line_no, "def_line_no should not be None")
        decorator_start_line = enc.get("decorator_start_line")
        self.assertIsNotNone(decorator_start_line, "decorator_start_line should not be None")
        self.assertEqual(decorator_start_line, def_line_no - 1,
                        "decorator_start_line should be one line before def_line_no")
        
        # Assert start_line includes decorator
        self.assertLessEqual(decorator_start_line, start_line,
                            "start_line should include decorator line")
        self.assertEqual(start_line, decorator_start_line,
                        "start_line should equal decorator_start_line when decorator exists")
        
        # Assert earlier functions are NOT included
        block = enc.get("block", "")
        self.assertNotIn("some_other_function", block,
                        "Block should NOT include earlier def some_other_function")
        self.assertNotIn("_extract_document_sources", block,
                        "Block should NOT include earlier def _extract_document_sources")
        
        # Assert signature extraction (should return clean def line, no decorators)
        signature = extract_enclosure.extract_signature_only(enc)
        self.assertIsNotNone(signature, "signature should not be None")
        self.assertIn("async def startup_event", signature)
        self.assertNotIn("@app.on_event", signature,
                        "signature should not include decorators")


if __name__ == "__main__":
    unittest.main()

