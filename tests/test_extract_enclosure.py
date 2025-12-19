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

        match_line_no = top.get("line_no")
        enc = extract_enclosure.extract_enclosure(top.get("path"), match_line_no)
        self.assertEqual(enc.get("enclosure_type"), "def")
        self.assertIn("def do_periodic_idle", enc.get("block", ""))
        self.assertIn("PeriodicIdle: waitComplete for localhost:9210:Dyn-ultron:VALVE", enc.get("block", ""))
        # Validate containment
        self.assertLessEqual(enc.get("start_line"), match_line_no)
        self.assertGreaterEqual(enc.get("end_line"), match_line_no)

    def test_fallback_module(self):
        path = os.path.join(self._fixture_root(), "top_level_only.py")
        # logger.error is on line 4 in this fixture (after future import + comment).
        match_line_no = 4
        enc = extract_enclosure.extract_enclosure(path, match_line_no, context_fallback=2)
        self.assertEqual(enc.get("enclosure_type"), "module")
        self.assertIsNone(enc.get("start_line"), "Module-level should have start_line=None")
        self.assertIsNone(enc.get("end_line"), "Module-level should have end_line=None")
        self.assertIn("very_unique_marker_123456", enc.get("block", ""))
        # Block should still contain the match line (context window)
        block_lines = enc.get("block", "").split("\n")
        self.assertTrue(len(block_lines) > 0, "Block should have content")

    def test_wrong_previous_function_regression(self):
        """Test that match inside second function returns second function, not first."""
        # Create a temporary test file with two functions
        import tempfile
        test_content = """def first_function():
    x = 1
    return x

def second_function():
    logger.error("match string here")
    y = 2
    return y
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            temp_path = f.name

        try:
            # Match is on line 6 (inside second_function)
            match_line_no = 6
            enc = extract_enclosure.extract_enclosure(temp_path, match_line_no)
            # Should return second_function, not first_function
            self.assertEqual(enc.get("enclosure_type"), "def")
            self.assertEqual(enc.get("name"), "second_function")
            self.assertIn("second_function", enc.get("block", ""))
            self.assertNotIn("first_function", enc.get("block", ""))
            # Validate containment
            self.assertLessEqual(enc.get("start_line"), match_line_no)
            self.assertGreaterEqual(enc.get("end_line"), match_line_no)
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass

    def test_decorator_async_def(self):
        """Test that decorator + async def is handled correctly."""
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

    def test_module_level_log(self):
        """Test that module-level match returns module type."""
        import tempfile
        test_content = """# Module level
logger.error("module level error")
x = 1
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            temp_path = f.name

        try:
            # Match is on line 2 (module level, no def/class)
            match_line_no = 2
            enc = extract_enclosure.extract_enclosure(temp_path, match_line_no, context_fallback=5)
            # Should return module type
            self.assertEqual(enc.get("enclosure_type"), "module")
            self.assertIsNone(enc.get("name"))
            self.assertIsNone(enc.get("start_line"), "Module-level should have start_line=None")
            self.assertIsNone(enc.get("end_line"), "Module-level should have end_line=None")
            self.assertIn("module level error", enc.get("block", ""))
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass

    def test_nested_def(self):
        """Test that match inside inner def returns inner def, not outer."""
        import tempfile
        test_content = """def outer_function():
    def inner_function():
        logger.error("match inside inner")
        return True
    return inner_function()
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            temp_path = f.name

        try:
            # Match is on line 3 (inside inner_function)
            match_line_no = 3
            enc = extract_enclosure.extract_enclosure(temp_path, match_line_no)
            # Should return inner_function, not outer_function
            self.assertEqual(enc.get("enclosure_type"), "def")
            self.assertEqual(enc.get("name"), "inner_function")
            self.assertIn("inner_function", enc.get("block", ""))
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


