import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.common import (
    PathManager,
    get_question_field,
    safe_json_load,
    safe_json_save,
    sanitize_filename,
)


class PathManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.project_root = (Path(self.temp_dir.name) / "project").resolve()
        self.original_root = PathManager._app_root
        PathManager._app_root = self.project_root
        self.addCleanup(setattr, PathManager, "_app_root", self.original_root)
        self.frozen_patch = mock.patch.object(sys, "frozen", False, create=True)
        self.frozen_patch.start()
        self.addCleanup(self.frozen_patch.stop)

    def test_get_file_path_accepts_a_nested_path_inside_directory(self):
        result = PathManager.get_file_path("nested/value.json", "cache")
        self.assertEqual(result, self.project_root / "data" / "cache" / "nested" / "value.json")

    def test_get_file_path_rejects_sibling_prefix_bypass(self):
        with self.assertRaises(ValueError):
            PathManager.get_file_path("../data-backup/value.json", "data")

    def test_get_file_path_rejects_absolute_path(self):
        outside = Path(self.temp_dir.name) / "outside.json"
        with self.assertRaises(ValueError):
            PathManager.get_file_path(str(outside), "data")

    def test_get_file_path_rejects_unknown_subdirectory(self):
        with self.assertRaises(ValueError):
            PathManager.get_file_path("value.json", "typo")


class CommonUtilityTests(unittest.TestCase):
    def test_sanitize_filename_removes_paths_and_reserved_names(self):
        self.assertEqual(sanitize_filename(" ../课程:一? "), ".._课程_一_")
        self.assertEqual(sanitize_filename("CON"), "_CON")
        self.assertEqual(sanitize_filename("..."), "untitled")
        self.assertEqual(sanitize_filename(""), "untitled")

    def test_sanitize_filename_honours_length_limit(self):
        self.assertEqual(sanitize_filename("abcdef", max_length=4), "abcd")
        with self.assertRaises(ValueError):
            sanitize_filename("name", max_length=0)

    def test_safe_json_save_is_atomic_and_creates_parent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "nested" / "state.json"
            payload = {"课程": [1, 2, 3]}
            self.assertTrue(safe_json_save(payload, target))
            self.assertEqual(safe_json_load(target), payload)
            self.assertEqual(list(target.parent.glob("*.tmp")), [])
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), payload)

    def test_get_question_field_uses_non_empty_alias(self):
        question = {"correct_answer": "", "answer": "B", "isCorrect": False}
        self.assertEqual(get_question_field(question, "correct_answer"), "B")
        self.assertIs(get_question_field(question, "is_correct"), False)


if __name__ == "__main__":
    unittest.main()
