import unittest
import tempfile
import zipfile
from pathlib import Path

from core.html_templates import TemplateRegistry
from core.question_exporter import QuestionExporter


class QuestionExporterTests(unittest.TestCase):
    def test_statistics_support_aliases_and_human_readable_scores(self):
        questions = [
            {
                "type": "单选题",
                "isCorrect": True,
                "score": "2.5分",
                "totalScore": "5分",
                "contentImages": ["one.png"],
                "options": [{"images": ["two.png"]}],
            },
            {
                "question_type": "判断题",
                "is_correct": False,
                "score": "1/2",
                "total_score": 2,
            },
            {"question_type": "填空题"},
        ]

        stats = QuestionExporter(questions).get_statistics()

        self.assertEqual(stats["total_questions"], 3)
        self.assertEqual(stats["correct_count"], 1)
        self.assertEqual(stats["wrong_count"], 1)
        self.assertEqual(stats["unanswered_count"], 1)
        self.assertEqual(stats["total_score"], 3.5)
        self.assertEqual(stats["max_score"], 7.0)
        self.assertEqual(stats["total_images"], 2)
        self.assertEqual(stats["accuracy"], "33.3%")

    def test_parse_score_uses_first_number_without_concatenating(self):
        self.assertEqual(QuestionExporter._parse_score("1/2分"), 1.0)
        self.assertEqual(QuestionExporter._parse_score("得 3.25 分"), 3.25)
        self.assertIsNone(QuestionExporter._parse_score("未评分"))
        self.assertIsNone(QuestionExporter._parse_score(True))

    def test_malformed_remote_field_types_do_not_break_export_helpers(self):
        exporter = QuestionExporter([{
            "content": ["unexpected"],
            "question_type": ["单选题"],
            "content_images": {"src": "bad-shape"},
            "options": {"A": "not-a-list"},
        }])

        stats = exporter.get_statistics()
        self.assertEqual(stats["question_types"], {"['单选题']": 1})
        self.assertEqual(stats["total_images"], 0)
        self.assertEqual(exporter._get_question_content(exporter.questions[0]), "['unexpected']")
        self.assertEqual(exporter._get_options(exporter.questions[0]), [])

    def test_all_html_templates_escape_type_score_and_filter_values(self):
        question = {
            "content": "<script>alert('content')</script>",
            "question_type": "x');alert('type');//<b>",
            "score": "<img src=x onerror=alert('score')>",
            "options": [],
        }
        exporter = QuestionExporter([question], "<标题>")
        registry = TemplateRegistry()

        for template_info in registry.list_all():
            html = registry.get(template_info["id"]).render_html(exporter)
            self.assertNotIn("<script>alert('content')</script>", html)
            self.assertNotIn("<img src=x onerror=alert('score')>", html)
            self.assertNotIn("filterByType('x');alert", html)
            self.assertIn("&lt;", html)

    def test_excel_export_keeps_remote_text_out_of_formula_cells(self):
        exporter = QuestionExporter([{
            "content": "=HYPERLINK(\"https://example.invalid\",\"click\")",
            "question_type": "单选题",
            "options": [],
        }])
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "safe.xlsx"
            self.assertTrue(exporter.export_excel(str(output)))
            with zipfile.ZipFile(output) as archive:
                worksheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
                self.assertNotIn("<f>", worksheet)

    def test_markdown_drops_unsafe_image_protocol(self):
        exporter = QuestionExporter([])
        rendered = exporter._render_image_markdown({
            "src": "javascript:alert(1)",
            "alt": "] malicious",
        })
        self.assertEqual(rendered, "")


if __name__ == "__main__":
    unittest.main()
