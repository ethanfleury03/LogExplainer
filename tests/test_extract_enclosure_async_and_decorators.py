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


class ExtractEnclosureAsyncDecoratorsTest(unittest.TestCase):
    def _fixture_path(self):
        return os.path.join(REPO_ROOT, "tests", "fixtures", "async_decorator_test.py")

    def test_async_def_with_decorator_regression(self):
        """
        Regression test: match inside async def with decorator should return
        async def startup_event(), not earlier defs like _extract_document_sources.
        """
        fixture_path = self._fixture_path()
        if not os.path.exists(fixture_path):
            self.skipTest("Fixture file not found: %s" % (fixture_path,))

        # The match line is inside async def startup_event()
        # In the fixture, the logger.error line is around line 20-21
        # Let's find the exact line
        with open(fixture_path, "rb") as f:
            lines = f.readlines()
        
        match_line_no = None
        for i, line in enumerate(lines, 1):
            if b"[RAG] Index download failed" in line:
                match_line_no = i
                break
        
        self.assertIsNotNone(match_line_no, "Could not find match line in fixture")
        
        enc = extract_enclosure.extract_enclosure(fixture_path, match_line_no)
        
        # Assert correct enclosure
        self.assertEqual(enc.get("enclosure_type"), "async_def", 
                        "Expected async_def, got %s" % (enc.get("enclosure_type"),))
        self.assertEqual(enc.get("name"), "startup_event",
                        "Expected startup_event, got %s" % (enc.get("name"),))
        
        # Assert containment
        start_line = enc.get("start_line")
        end_line = enc.get("end_line")
        self.assertIsNotNone(start_line, "start_line should not be None")
        self.assertIsNotNone(end_line, "end_line should not be None")
        self.assertLessEqual(start_line, match_line_no,
                            "start_line (%d) should be <= match_line_no (%d)" % (start_line, match_line_no))
        self.assertGreaterEqual(end_line, match_line_no,
                               "end_line (%d) should be >= match_line_no (%d)" % (end_line, match_line_no))
        
        # Assert decorator is included
        block = enc.get("block", "")
        self.assertIn("@app.on_event", block,
                     "Block should include decorator @app.on_event")
        self.assertIn("async def startup_event", block,
                     "Block should include async def startup_event")
        
        # Assert earlier defs are NOT included
        self.assertNotIn("_extract_document_sources", block,
                        "Block should NOT include earlier def _extract_document_sources")
        self.assertNotIn("another_function", block,
                        "Block should NOT include earlier def another_function")

    def test_two_defs_before_match(self):
        """
        Test that when there are two defs before the match, the correct one is selected.
        This ensures the backwards scan finds the nearest containing def.
        """
        import tempfile
        test_content = """def first_function():
    x = 1
    return x

def second_function():
    logger.error("match string here")
    y = 2
    return y

def third_function():
    z = 3
    return z
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            temp_path = f.name

        try:
            # Match is on line 6 (inside second_function)
            match_line_no = 6
            enc = extract_enclosure.extract_enclosure(temp_path, match_line_no)
            
            # Should return second_function, not first_function or third_function
            self.assertEqual(enc.get("enclosure_type"), "def")
            self.assertEqual(enc.get("name"), "second_function")
            self.assertIn("second_function", enc.get("block", ""))
            self.assertNotIn("first_function", enc.get("block", ""))
            self.assertNotIn("third_function", enc.get("block", ""))
            
            # Validate containment
            self.assertLessEqual(enc.get("start_line"), match_line_no)
            self.assertGreaterEqual(enc.get("end_line"), match_line_no)
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass

    def test_decorator_above_async_def(self):
        """Test that decorator above async def is included in start_line."""
        import tempfile
        test_content = """@app.on_event("startup")
async def startup_event():
    logger.error("[RAG] Index download failed...")
    return True
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            temp_path = f.name

        try:
            # Match is on line 3 (inside async def)
            match_line_no = 3
            enc = extract_enclosure.extract_enclosure(temp_path, match_line_no)
            
            # Should return async def with decorator
            self.assertEqual(enc.get("enclosure_type"), "async_def")
            self.assertEqual(enc.get("name"), "startup_event")
            # start_line should include decorator (line 1)
            self.assertEqual(enc.get("start_line"), 1)
            self.assertIn("@app.on_event", enc.get("block", ""))
            self.assertIn("async def startup_event", enc.get("block", ""))
            
            # Validate containment
            self.assertLessEqual(enc.get("start_line"), match_line_no)
            self.assertGreaterEqual(enc.get("end_line"), match_line_no)
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()

