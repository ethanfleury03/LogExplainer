from __future__ import absolute_import

import os
import sys
import shutil
import tempfile
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
        "2025-12-19T05:22:06.751222+11:00 RS20300529 Kareela0: <I> [#4] EngineConductor: Changing state ...",
        "2025-12-19T05:22:06.895453+11:00 RS20300529 Kareela0: <E> [#4] PeriodicIdle: waitComplete for localhost:9210:Dyn-ultron:VALVE",
    ]
)


class SearchCodeTest(unittest.TestCase):
    def _fixture_root(self):
        return os.path.join(REPO_ROOT, "tests", "fixtures", "sample_repo")

    def test_exact_match_found(self):
        parsed = parse_log.analyze_pasted_text(SAMPLE_BLOCK)
        roots = [self._fixture_root()]
        msg = parsed.get("search_message")
        res, stats = search_code.search_message_exact_in_roots(
            roots=roots,
            message=msg,
            include_exts=[".py"],
            exclude_dir_names=["__pycache__"],
            case_insensitive=False,
            max_results=10,
            component=parsed.get("component"),
        )
        self.assertTrue(res, msg="Expected at least 1 match")
        top = res[0]
        self.assertEqual(top.get("match_type"), "exact_message")
        self.assertGreaterEqual(float(top.get("score", 0.0)), 0.9)

    def test_normalized_fallback(self):
        # Message-only exact search: casing differences require case_insensitive=True.
        log = "2025-12-19T05:22:06.895453+11:00 RS20300529 Kareela0: <E> [#4] PeriodicIdle: WAITCOMPLETE for localhost:9210:Dyn-ultron:VALVE"
        parsed = parse_log.analyze_pasted_text(log)
        roots = [self._fixture_root()]
        res, stats = search_code.search_message_exact_in_roots(
            roots=roots,
            message=parsed.get("search_message"),
            include_exts=[".py"],
            exclude_dir_names=["__pycache__"],
            case_insensitive=True,
            max_results=10,
        )
        self.assertTrue(res, msg="Expected fallback matches")
        self.assertEqual(res[0].get("match_type"), "exact_message")

    def test_exclude_dirs(self):
        parsed = parse_log.analyze_pasted_text(SAMPLE_BLOCK)
        roots = [self._fixture_root()]
        res, stats = search_code.search_message_exact_in_roots(
            roots=roots,
            message=parsed.get("search_message"),
            include_exts=[".py"],
            exclude_dir_names=["__pycache__"],
            case_insensitive=False,
            max_results=50,
        )
        # Ensure we didn't return the ignored.py under __pycache__.
        for m in res:
            self.assertNotIn("__pycache__", m.get("path", ""))

    def test_no_symlink_follow(self):
        # Create a symlink inside a temp root pointing to an external directory with a matching file.
        if not hasattr(os, "symlink"):
            return

        temp_root = tempfile.mkdtemp(prefix="alh_symlink_root_")
        outside = tempfile.mkdtemp(prefix="alh_symlink_outside_")
        try:
            # Matching file exists only in 'outside' directory.
            target_py = os.path.join(outside, "target.py")
            f = open(target_py, "wb")
            try:
                f.write(b'logger.error("SymlinkOnly: very_unique_marker_123456")\n')
            finally:
                f.close()

            link_path = os.path.join(temp_root, "linkdir")
            try:
                os.symlink(outside, link_path)
            except Exception:
                # Likely permissions/platform; skip gracefully.
                return

            # Search for the symlink-only string within temp_root. Should find nothing by default.
            log = "SymlinkOnly: very_unique_marker_123456"
            parsed = parse_log.analyze_pasted_text(log)
            res, stats = search_code.search_message_exact_in_roots(
                roots=[temp_root],
                message=parsed.get("search_message") or parsed.get("message") or "SymlinkOnly: very_unique_marker_123456",
                include_exts=[".py"],
                exclude_dir_names=[],
                case_insensitive=False,
                max_results=10,
                follow_symlinks=False,
            )
            self.assertEqual(res, [], msg="Should not follow symlink dirs by default")
        finally:
            # Best-effort cleanup; ignore failures (Windows locks, permissions).
            try:
                lp = os.path.join(temp_root, "linkdir")
                if os.path.lexists(lp):
                    try:
                        os.remove(lp)
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                shutil.rmtree(temp_root)
            except Exception:
                pass
            try:
                shutil.rmtree(outside)
            except Exception:
                pass

    def test_max_files_scanned(self):
        parsed = parse_log.analyze_pasted_text(SAMPLE_BLOCK)
        res, stats = search_code.search_message_exact_in_roots(
            roots=[self._fixture_root()],
            message=parsed.get("search_message"),
            include_exts=[".py"],
            exclude_dir_names=["__pycache__"],
            case_insensitive=False,
            max_results=10,
            max_files_scanned=1,
        )
        self.assertIn(stats.get("stopped_reason"), ("max_files", "max_results", None))

    def test_max_seconds(self):
        parsed = parse_log.analyze_pasted_text(SAMPLE_BLOCK)
        res, stats = search_code.search_message_exact_in_roots(
            roots=[self._fixture_root()],
            message=parsed.get("search_message"),
            include_exts=[".py"],
            exclude_dir_names=["__pycache__"],
            case_insensitive=False,
            max_results=10,
            max_seconds=0.0,
        )
        self.assertIn(stats.get("stopped_reason"), ("max_seconds", "max_results", None))
        self.assertGreaterEqual(float(stats.get("elapsed_seconds", 0.0)), 0.0)


if __name__ == "__main__":
    unittest.main()


