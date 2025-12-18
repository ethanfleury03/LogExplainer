from __future__ import absolute_import

import os
import sys
import unittest


# Ensure src/ is importable when running tests directly.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
SRC_DIR = os.path.join(REPO_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


from arrow_log_helper import repo_discover  # noqa: E402


class RepoDiscoverTest(unittest.TestCase):
    def test_discover_candidates_on_fixture(self):
        fixture_root = os.path.join(REPO_ROOT, "tests", "fixtures", "sample_repo")
        res = repo_discover.discover_candidates([fixture_root], max_depth=4, follow_symlinks=False)
        self.assertTrue(res, msg="Expected some candidates")
        # Should include the fixture root itself or a subdir.
        paths = [c.get("path") for c in res]
        self.assertTrue(
            any(p and os.path.abspath(p).startswith(os.path.abspath(fixture_root)) for p in paths),
            msg="Expected fixture root (or subdir) in candidates",
        )
        self.assertTrue(any(int(c.get("score", 0)) > 0 for c in res), msg="Expected score > 0 for some candidate")


if __name__ == "__main__":
    unittest.main()


