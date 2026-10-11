import os
import shutil
import subprocess
import tempfile
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SH = shutil.which("sh")


@unittest.skipUnless(SH, "needs a POSIX sh")
class InstallScriptTest(unittest.TestCase):
    def test_refuses_to_install_over_its_own_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(os.path.join(PROJECT_ROOT, "install.sh"), tmp)
            os.mkdir(os.path.join(tmp, "wwol"))
            marker = os.path.join(tmp, "wwol", "server.py")
            open(marker, "w").close()

            result = subprocess.run(
                [SH, "install.sh"], cwd=tmp,
                env=dict(os.environ, WWOL_APP_DIR=tmp),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True)

            self.assertEqual(result.returncode, 1)
            self.assertIn("not into", result.stderr)
            self.assertTrue(os.path.exists(marker), "source files were deleted")


if __name__ == "__main__":
    unittest.main()
