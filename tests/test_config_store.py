from __future__ import absolute_import

import os
import shutil
import sys
import unittest


# Ensure src/ is importable when running tests directly.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
SRC_DIR = os.path.join(REPO_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


from arrow_log_helper import config_store  # noqa: E402


class ConfigStoreTest(unittest.TestCase):
    def test_save_and_load_selected_roots(self):
        tmp_root = os.path.join(REPO_ROOT, "tests", "tmp_config_store")
        # Clean slate
        if os.path.isdir(tmp_root):
            shutil.rmtree(tmp_root)
        os.makedirs(os.path.join(tmp_root, "config"))

        roots = ["A", "B"]
        config_store.save_selected_roots(tmp_root, roots)
        loaded = config_store.load_selected_roots(tmp_root)
        self.assertEqual(loaded, roots)

        shutil.rmtree(tmp_root)


if __name__ == "__main__":
    unittest.main()


