from __future__ import absolute_import

import os
import shutil
import sys
import tempfile
import unittest


# Ensure src/ is importable when running tests directly.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
SRC_DIR = os.path.join(REPO_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


from arrow_log_helper import write_firewall  # noqa: E402


class WriteFirewallTest(unittest.TestCase):
    def test_blocks_writes_outside_allowed_root(self):
        allowed = os.path.join(REPO_ROOT, "tests", "tmp_allowed")
        other = tempfile.mkdtemp(prefix="alh_other_")
        try:
            if os.path.isdir(allowed):
                shutil.rmtree(allowed)
            os.makedirs(allowed)

            # Create a file outside allowed root BEFORE installing firewall.
            outside_path = os.path.join(other, "outside.txt")
            f = open(outside_path, "wb")
            try:
                f.write(b"outside\n")
            finally:
                f.close()

            # Install firewall and verify allowed root is writable.
            write_firewall.assert_writable_dir(allowed)
            write_firewall.install_write_firewall(allowed)

            # Writing inside allowed root works.
            inside_path = os.path.join(allowed, "inside.txt")
            f2 = open(inside_path, "wb")
            try:
                f2.write(b"inside\n")
            finally:
                f2.close()
            os.remove(inside_path)

            # Writing outside allowed root is blocked.
            blocked = False
            try:
                open(os.path.join(other, "nope.txt"), "wb")
            except IOError:
                blocked = True
            self.assertTrue(blocked)

            # os.remove outside allowed root is blocked.
            blocked = False
            try:
                os.remove(outside_path)
            except IOError:
                blocked = True
            self.assertTrue(blocked)

            # shutil.move to outside allowed root is blocked.
            src_path = os.path.join(allowed, "move_me.txt")
            f3 = open(src_path, "wb")
            try:
                f3.write(b"move\n")
            finally:
                f3.close()

            blocked = False
            try:
                shutil.move(src_path, os.path.join(other, "moved.txt"))
            except IOError:
                blocked = True
            self.assertTrue(blocked)
        finally:
            try:
                write_firewall.uninstall_write_firewall()
            except Exception:
                pass
            try:
                shutil.rmtree(other)
            except Exception:
                pass
            try:
                shutil.rmtree(allowed)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()


