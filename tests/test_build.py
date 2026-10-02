import os
import tempfile
import unittest
from pathlib import Path

import build


class BuildScriptTests(unittest.TestCase):
    def test_parse_version_tuple(self):
        self.assertEqual(build.parse_version_tuple("3.1.4"), (3, 1, 4, 0))
        self.assertEqual(build.parse_version_tuple("3.beta.4.5.6"), (3, 0, 4, 5))
        self.assertEqual(build.parse_version_tuple("-1.2"), (0, 2, 0, 0))

    def test_build_args_share_local_and_ci_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            (root / "main.py").write_text("", encoding="utf-8")
            (root / "README.md").write_text("", encoding="utf-8")
            (root / "assets").mkdir()
            (root / "assets" / "icon.ico").write_bytes(b"icon")

            args = build.build_pyinstaller_args(root, clean=True, console=False)

            self.assertIn("--clean", args)
            self.assertIn("--noconsole", args)
            self.assertIn("--onedir", args)
            self.assertIn("--collect-all=qfluentwidgets", args)
            self.assertIn(f"--add-data={root / 'README.md'}{os.pathsep}.", args)
            self.assertTrue(any(arg.startswith("--version-file=") for arg in args))
            self.assertTrue((root / "build" / "version_info.autogen.txt").exists())

            fast_args = build.build_pyinstaller_args(root, clean=False, console=True)
            self.assertNotIn("--clean", fast_args)
            self.assertIn("--console", fast_args)

    def test_validate_project_reports_missing_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(FileNotFoundError):
                build.validate_project(Path(temp_dir))


if __name__ == "__main__":
    unittest.main()
