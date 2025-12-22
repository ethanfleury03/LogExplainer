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


class DocstringExtractionTest(unittest.TestCase):
    def _fixture_path(self, filename):
        return os.path.join(REPO_ROOT, "tests", "fixtures", "sample_repo", filename)

    def test_async_def_with_decorator_and_docstring(self):
        """Test extraction of decorator, async def, and docstring."""
        fixture_path = self._fixture_path("docstring_cases.py")
        if not os.path.exists(fixture_path):
            self.skipTest("Fixture file not found: %s" % (fixture_path,))

        # Find the match line (logger.error inside startup_event_with_docstring)
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
        self.assertEqual(enc.get("enclosure_type"), "async_def")
        self.assertEqual(enc.get("name"), "startup_event_with_docstring")
        self.assertTrue(enc.get("enclosure_contains_match"), "Containment should be validated")
        
        # Assert decorators
        decorator_lines = enc.get("decorator_lines", [])
        self.assertEqual(len(decorator_lines), 1)
        self.assertIn("@app.on_event", decorator_lines[0])
        
        # Assert def line
        self.assertEqual(enc.get("def_line_text"), "async def startup_event_with_docstring():")
        self.assertIsNotNone(enc.get("def_line_no"))
        self.assertEqual(enc.get("decorator_start_line"), enc.get("def_line_no") - 1)
        
        # Assert docstring
        docstring = enc.get("docstring_text")
        self.assertIsNotNone(docstring, "Docstring should be extracted")
        self.assertIn("This is the real Python docstring", docstring)
        self.assertIsNotNone(enc.get("docstring_start_line"))
        self.assertIsNotNone(enc.get("docstring_end_line"))
        
        # Assert leading comment block
        leading_comment = enc.get("leading_comment_block")
        self.assertIsNotNone(leading_comment, "Leading comment should be extracted")
        self.assertIn("comment header above the function", leading_comment)
        self.assertIsNotNone(enc.get("leading_comment_start_line"))
        self.assertIsNotNone(enc.get("leading_comment_end_line"))
        
        # Validate containment
        self.assertLessEqual(enc.get("start_line"), match_line_no)
        self.assertGreaterEqual(enc.get("end_line"), match_line_no)

    def test_function_with_comment_header_no_docstring(self):
        """Test function with comment header but no docstring."""
        fixture_path = self._fixture_path("docstring_cases.py")
        if not os.path.exists(fixture_path):
            self.skipTest("Fixture file not found")
        
        # Find the match line in function_with_comment_header
        with open(fixture_path, "rb") as f:
            lines = f.readlines()
        
        match_line_no = None
        for i, line in enumerate(lines, 1):
            if b"Some error message" in line and match_line_no is None:
                match_line_no = i
                break
        
        self.assertIsNotNone(match_line_no)
        
        enc = extract_enclosure.extract_enclosure(fixture_path, match_line_no)
        
        self.assertEqual(enc.get("enclosure_type"), "def")
        self.assertEqual(enc.get("name"), "function_with_comment_header")
        
        # Should have leading comment but no docstring
        leading_comment = enc.get("leading_comment_block")
        self.assertIsNotNone(leading_comment)
        self.assertIn("Header comment", leading_comment)
        
        docstring = enc.get("docstring_text")
        self.assertIsNone(docstring, "Should not have docstring")

    def test_function_with_header_block_and_docstring(self):
        """Test function with triple-quote header block and separate docstring."""
        fixture_path = self._fixture_path("docstring_cases.py")
        if not os.path.exists(fixture_path):
            self.skipTest("Fixture file not found")
        
        # Find the match line in function_with_header_block
        with open(fixture_path, "rb") as f:
            lines = f.readlines()
        
        match_line_no = None
        for i, line in enumerate(lines, 1):
            if b"Another error" in line:
                match_line_no = i
                break
        
        self.assertIsNotNone(match_line_no)
        
        enc = extract_enclosure.extract_enclosure(fixture_path, match_line_no)
        
        self.assertEqual(enc.get("enclosure_type"), "def")
        self.assertEqual(enc.get("name"), "function_with_header_block")
        
        # Should have both header block and docstring
        leading_comment = enc.get("leading_comment_block")
        self.assertIsNotNone(leading_comment)
        self.assertIn("triple-quote header block", leading_comment)
        
        docstring = enc.get("docstring_text")
        self.assertIsNotNone(docstring)
        self.assertIn("actual docstring inside", docstring)
        # Docstring should be different from header block
        self.assertNotEqual(leading_comment, docstring)

    def test_containment_flag(self):
        """Test that enclosure_contains_match is set correctly."""
        import tempfile
        test_content = """def test_function():
    logger.error("test message")
    return True
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            temp_path = f.name

        try:
            # Match is on line 2 (inside function)
            match_line_no = 2
            enc = extract_enclosure.extract_enclosure(temp_path, match_line_no)
            
            # Should have containment flag set to True
            self.assertTrue(enc.get("enclosure_contains_match"), 
                          "enclosure_contains_match should be True for valid containment")
            
            # Verify containment
            self.assertLessEqual(enc.get("start_line"), match_line_no)
            self.assertGreaterEqual(enc.get("end_line"), match_line_no)
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass

    def test_decorator_separation(self):
        """Test that decorators are separated from def line."""
        import tempfile
        test_content = """@app.on_event("startup")
@another_decorator
async def startup_event():
    logger.error("test")
    return True
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            temp_path = f.name

        try:
            match_line_no = 4
            enc = extract_enclosure.extract_enclosure(temp_path, match_line_no)
            
            # Check decorators are separate
            decorator_lines = enc.get("decorator_lines", [])
            self.assertEqual(len(decorator_lines), 2)
            self.assertIn("@app.on_event", decorator_lines[0])
            self.assertIn("@another_decorator", decorator_lines[1])
            
            # Check def line is separate
            def_line = enc.get("def_line_text")
            self.assertEqual(def_line, "async def startup_event():")
            self.assertNotIn("@", def_line)
            
            # Check line numbers
            self.assertEqual(enc.get("decorator_start_line"), 1)
            self.assertEqual(enc.get("def_line_no"), 3)
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()


