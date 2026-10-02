import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import requests

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QSignalSpy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from core.config_manager import ConfigManager
from core.common import LoginError
from core.course_manager import CourseManager
from core.export_history import ExportHistoryManager
from core.homework_count_manager import HomeworkCountManager
from core.homework_manager import HomeworkManager
from core.homework_question_parser import HomeworkQuestionParser
from ui.export_dialog import ExportWorker
from ui.course_list import CourseListFluent
from ui.homework_list import HomeworkListFluent, _parse_homework_status
from ui.main_window import DownloadWorker
from ui.question_list import QuestionListFluent


class HomeworkLogicTests(unittest.TestCase):
    def test_status_parser_checks_negative_words_before_substrings(self):
        self.assertEqual(_parse_homework_status("未完成")[0], "待完成")
        self.assertEqual(_parse_homework_status("待提交")[0], "待完成")
        self.assertEqual(_parse_homework_status("已提交")[0], "已完成")
        self.assertEqual(_parse_homework_status("已截止")[0], "已过期")
        self.assertEqual(_parse_homework_status("待批阅")[0], "待批阅")
        self.assertEqual(_parse_homework_status("已批阅")[0], "已完成")

    def test_pagination_url_preserves_required_parameters(self):
        manager = HomeworkManager.__new__(HomeworkManager)
        url = (
            "https://mooc1.chaoxing.com/mooc2/work/list?"
            "courseId=1&classId=2&cpi=3&ut=s&t=4&stuenc=5&enc=6"
        )
        page_url = manager.build_homework_url_with_page(url, 3)
        self.assertIn("courseId=1", page_url)
        self.assertIn("classId=2", page_url)
        self.assertIn("stuenc=5", page_url)
        self.assertIn("pageNum=3", page_url)
        self.assertIn("status=0", page_url)

    def test_question_parser_does_not_trust_fallback_user_name(self):
        class FakeManager:
            class Session:
                cookies = []

            session = Session()

            def get_user_info(self):
                return {"name": "学习通用户"}

        parser = HomeworkQuestionParser(FakeManager())
        self.assertFalse(parser.check_login())
        FakeManager.Session.cookies = [object()]
        self.assertTrue(parser.check_login())

    def test_corrupt_count_cache_entry_is_a_miss(self):
        manager = HomeworkCountManager.__new__(HomeworkCountManager)
        manager.load_count_cache = lambda: {"course": {"count": "bad", "ts": "bad"}}
        self.assertEqual(manager._read_cached_count("course"), (False, 0))


class PersistenceTests(unittest.TestCase):
    def test_config_ignores_invalid_nested_sections(self):
        manager = ConfigManager.__new__(ConfigManager)
        config = manager._dict_to_config({"network": None, "ui": "invalid"})
        self.assertEqual(config.network.timeout, 30)
        self.assertEqual(config.ui.theme, "light")

    def test_export_history_recovers_from_non_list_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_file = Path(temp_dir) / "history.json"
            history_file.write_text('{"unexpected": true}', encoding="utf-8")
            manager = ExportHistoryManager(str(history_file))
            self.assertEqual(manager.get_history(), [])
            manager.add_record("课程", ["作业"], 2, "JSON", str(history_file))
            self.assertEqual(manager.get_statistics()["total_exports"], 1)

    def test_course_cache_is_bound_to_current_account(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = CourseManager.__new__(CourseManager)
            manager.courses_file = Path(temp_dir) / "courses.json"
            account_a = requests.Session()
            account_a.cookies.set("_uid", "account-a")
            account_b = requests.Session()
            account_b.cookies.set("_uid", "account-b")
            key_a = manager._account_cache_key(account_a)
            key_b = manager._account_cache_key(account_b)
            self.assertTrue(manager.save_courses_to_cache([{"name": "A 的课程"}], key_a))
            self.assertEqual(manager.load_courses_from_cache(key_a), [{"name": "A 的课程"}])
            self.assertEqual(manager.load_courses_from_cache(key_b), [])

    def test_expired_login_does_not_fall_back_to_cached_courses(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = CourseManager.__new__(CourseManager)
            manager.courses_file = Path(temp_dir) / "courses.json"
            manager.headers = {}
            manager.courses = []
            session = requests.Session()
            session.cookies.set("_uid", "account-a")
            key = manager._account_cache_key(session)
            self.assertTrue(manager.save_courses_to_cache([{"name": "cached"}], key))
            session.post = lambda *args, **kwargs: SimpleNamespace(
                status_code=200, text="<title>用户登录</title>"
            )
            manager.get_session = lambda: session
            manager.invalidate_session = lambda: None

            with self.assertRaises(LoginError):
                manager.get_course_list(use_cache=False)


class WorkerContractTests(unittest.TestCase):
    def test_export_worker_does_not_shadow_qthread_finished_signal(self):
        class DummyExporter:
            pass

        worker = ExportWorker(DummyExporter(), ".", [], "name")
        self.assertTrue(hasattr(worker, "export_finished"))
        self.assertIn("finished()", str(worker.finished))
        self.assertIn("export_finished", str(worker.export_finished))

    def test_download_without_checksum_emits_full_failure_contract(self):
        worker = DownloadWorker("https://example.invalid/file", "unused", sha256_url=None)
        spy = QSignalSpy(worker.download_finished)
        worker.run()
        self.assertEqual(spy.count(), 1)
        self.assertEqual(len(spy.at(0)), 4)
        self.assertFalse(spy.at(0)[0])


class QuestionPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_selection_survives_search_filter_rebuild(self):
        page = QuestionListFluent()
        questions = [
            {"content": "第一题 alpha", "question_type": "单选题"},
            {"content": "第二题 beta", "question_type": "判断题"},
        ]
        page._on_questions_loaded(questions)
        page.question_cards[0].set_selected(True)

        page.search_edit.setText("beta")
        page._filter_timer.stop()
        page._filter_questions()
        self.assertEqual(len(page.question_cards), 1)
        self.assertEqual(len(page._selected_question_ids), 1)

        page.search_edit.clear()
        page._filter_timer.stop()
        page._filter_questions()
        first_card = next(c for c in page.question_cards if c.question_data is questions[0])
        self.assertTrue(first_card.is_selected)
        self.assertEqual(page.selected_label.text(), "已选择 1 题")

        page.deleteLater()
        self.app.processEvents()

    def test_parse_failure_clears_old_export_selection(self):
        page = QuestionListFluent()
        page._on_questions_loaded([{"content": "old", "question_type": "单选题"}])
        page.question_cards[0].set_selected(True)
        self.assertTrue(page.export_selected_btn.isEnabled())

        with patch("ui.question_list.InfoBar.error"):
            page._on_parse_error("网络异常")

        self.assertEqual(page.questions, [])
        self.assertEqual(page._selected_question_ids, set())
        self.assertFalse(page.export_selected_btn.isEnabled())
        self.assertFalse(page.select_all_cb.isChecked())
        page.deleteLater()
        self.app.processEvents()

    def test_single_question_toggle_updates_select_all(self):
        page = QuestionListFluent()
        page._on_questions_loaded([{"content": "one"}, {"content": "two"}])
        page.select_all_cb.setChecked(True)
        self.assertTrue(page.select_all_cb.isChecked())
        page.question_cards[0].set_selected(False)
        self.assertFalse(page.select_all_cb.isChecked())
        page.deleteLater()
        self.app.processEvents()

    def test_clear_during_loading_removes_overlay_and_disables_old_export(self):
        page = QuestionListFluent()
        page._on_questions_loaded([{"content": "old"}])
        page.question_cards[0].set_selected(True)
        page._set_loading(True)
        self.assertFalse(page.export_selected_btn.isEnabled())
        page.clear_data()
        self.assertTrue(page.loading_container.isHidden())
        self.assertFalse(page.export_selected_btn.isEnabled())
        self.assertEqual(page.questions, [])
        page.deleteLater()
        self.app.processEvents()


class HomeworkPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_sort_keeps_status_with_its_homework(self):
        page = HomeworkListFluent()
        page._on_homework_loaded([
            {"title": "B 作业", "status": "未完成", "url": "b"},
            {"title": "A 作业", "status": "已完成", "url": "a"},
        ])
        page.table.sortItems(1, Qt.AscendingOrder)
        self.assertEqual(page.table.item(0, 1).text(), "A 作业")
        self.assertEqual(page.table.item(0, 2).text(), "已完成")
        self.assertEqual(page.table.item(1, 1).text(), "B 作业")
        self.assertEqual(page.table.item(1, 2).text(), "待完成")
        page.deleteLater()
        self.app.processEvents()

    def test_load_failure_clears_old_selection_and_counts(self):
        page = HomeworkListFluent()
        page._on_homework_loaded([{"title": "old", "status": "已完成", "url": "old"}])
        page.table.cellWidget(0, 0).setChecked(True)
        self.assertTrue(page.batch_export_btn.isEnabled())
        self.assertTrue(page.select_all_cb.isChecked())

        with patch("ui.homework_list.InfoBar.error"):
            page._on_load_error("网络异常")

        self.assertEqual(page.homework_list, [])
        self.assertEqual(page._selected_ids, set())
        self.assertFalse(page.batch_export_btn.isEnabled())
        self.assertFalse(page.select_all_cb.isChecked())
        self.assertEqual(page.table.rowCount(), 0)
        page.deleteLater()
        self.app.processEvents()

    def test_clear_during_loading_removes_overlay(self):
        page = HomeworkListFluent()
        page._set_loading(True)
        page.clear_data()
        self.assertTrue(page.loading_container.isHidden())
        self.assertTrue(page.refresh_btn.isEnabled())
        page.deleteLater()
        self.app.processEvents()


class CoursePageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_clear_during_loading_removes_overlay(self):
        page = CourseListFluent()
        page._set_loading(True)
        page.clear_data()
        self.assertTrue(page.loading_container.isHidden())
        self.assertTrue(page.refresh_btn.isEnabled())
        page.deleteLater()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
