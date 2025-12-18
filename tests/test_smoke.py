from __future__ import absolute_import

import os
import subprocess
import sys
import unittest


class SmokeTest(unittest.TestCase):
    def test_module_help_runs(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        src_dir = os.path.join(repo_root, "src")

        env = dict(os.environ)
        env["PYTHONPATH"] = src_dir + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

        # `--help` should exit 0 via argparse without running any tool logic.
        p = subprocess.Popen(
            [sys.executable, "-m", "log_explainer", "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        out, err = p.communicate()
        self.assertEqual(p.returncode, 0, msg="stdout=%r stderr=%r" % (out, err))


if __name__ == "__main__":
    unittest.main()


