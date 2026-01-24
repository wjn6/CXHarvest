#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
题目导出模块 - 支持多种格式导出
整合多个优秀脚本的导出逻辑，提供最强大的导出功能

支持格式：
- HTML：精美网页格式，支持打印
- JSON：结构化数据，便于二次处理
- Word (DOCX)：正式文档格式
- PDF：通用便携格式
- Markdown：纯文本标记格式

Author: 综合优化版
"""

import os
import json
import base64
import re
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path

from core.enterprise_logger import app_logger


class ExportOptions:
    """导出选项配置类"""
    
    def __init__(self):
        # 内容选项
        self.include_my_answer = True       # 包含我的答案
        self.include_correct_answer = True   # 包含正确答案
        self.include_score = True            # 包含得分信息
        self.include_analysis = True         # 包含答案解析
        self.include_statistics = True       # 包含统计信息
        self.include_images = True           # 包含图片
        self.embed_images = False            # Word/PDF中嵌入图片（而非链接）
        
        # 格式选项
        self.include_separator = True        # 题目间添加分割线
        self.include_question_number = True  # 包含题目编号
        self.include_question_type = True    # 包含题目类型
        self.show_correct_status = True      # 显示答题正确/错误状态
        
        # 元信息
        self.include_export_time = True      # 包含导出时间
        self.include_homework_title = True   # 包含作业标题
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'include_my_answer': self.include_my_answer,
            'include_correct_answer': self.include_correct_answer,
            'include_score': self.include_score,
            'include_analysis': self.include_analysis,
            'include_statistics': self.include_statistics,
            'include_images': self.include_images,
            'embed_images': self.embed_images,
            'include_separator': self.include_separator,
            'include_question_number': self.include_question_number,
            'include_question_type': self.include_question_type,
            'show_correct_status': self.show_correct_status,
            'include_export_time': self.include_export_time,
            'include_homework_title': self.include_homework_title
        }


class QuestionExporter:
    """题目导出器 - 支持多种格式"""
    
    def __init__(self, questions: List[Dict], homework_title: str = "作业题目"):
        """
        初始化导出器
        
        Args:
            questions: 题目列表
            homework_title: 作业标题
        """
        self.questions = questions
        self.homework_title = homework_title
        self.options = ExportOptions()
        self._statistics = None
    
    def set_options(self, options: ExportOptions):
        """设置导出选项"""
        self.options = options
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        if self._statistics is None:
            self._statistics = self._calculate_statistics()
        return self._statistics
    
    def _calculate_statistics(self) -> Dict:
        """计算统计信息"""
        stats = {
            'total_questions': len(self.questions),
            'correct_count': 0,
            'wrong_count': 0,
            'unanswered_count': 0,
            'total_score': 0,
            'max_score': 0,
            'total_images': 0,
            'question_types': {}
        }
        
        for q in self.questions:
            # 统计正确/错误
            is_correct = q.get('isCorrect') or q.get('is_correct')
            if is_correct is True:
                stats['correct_count'] += 1
            elif is_correct is False:
                stats['wrong_count'] += 1
            else:
                stats['unanswered_count'] += 1
            
            # 统计分数
            score_str = q.get('score', '')
            if score_str:
                try:
                    score = float(re.sub(r'[^\d.]', '', str(score_str)))
                    stats['total_score'] += score
                except:
                    pass
            
            # 统计题型
            q_type = q.get('type') or q.get('question_type', '未知')
            stats['question_types'][q_type] = stats['question_types'].get(q_type, 0) + 1
            
            # 统计图片
            stats['total_images'] += len(q.get('title_images', []))
            stats['total_images'] += len(q.get('contentImages', []))
            for opt in q.get('options', []):
                if isinstance(opt, dict):
                    stats['total_images'] += len(opt.get('images', []))
        
        # 计算正确率
        if stats['total_questions'] > 0:
            stats['accuracy'] = f"{(stats['correct_count'] / stats['total_questions'] * 100):.1f}%"
        else:
            stats['accuracy'] = "0%"
        
        return stats
    
    def _get_question_content(self, q: Dict) -> str:
        """获取题目内容"""
        return q.get('content') or q.get('title', '')
    
    def _get_question_type(self, q: Dict) -> str:
        """获取题目类型"""
        return q.get('type') or q.get('question_type', '未知')
    
    def _get_question_answer(self, q: Dict) -> str:
        """获取正确答案"""
        return q.get('answer') or q.get('correct_answer', '')
    
    def _get_my_answer(self, q: Dict) -> str:
        """获取我的答案"""
        return q.get('myAnswer') or q.get('my_answer', '')
    
    def _get_analysis(self, q: Dict) -> str:
        """获取解析"""
        return q.get('analysis') or q.get('explanation', '')
    
    def _get_options(self, q: Dict) -> List:
        """获取选项列表"""
        options = q.get('options', [])
        result = []
        for opt in options:
            if isinstance(opt, dict):
                label = opt.get('label', '')
                content = opt.get('content', '')
                result.append(f"{label}. {content}")
            else:
                result.append(str(opt))
        return result
    
    def _is_correct(self, q: Dict) -> Optional[bool]:
        """判断是否正确"""
        return q.get('isCorrect') or q.get('is_correct')
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名中的非法字符"""
        illegal_chars = r'[\\/:*?"<>|]'
        return re.sub(illegal_chars, '_', filename)
    
    # ==================== HTML 导出 ====================
    
    def export_html(self, output_path: str) -> bool:
        """
        导出为HTML格式
        
        Args:
            output_path: 输出文件路径
            
        Returns:
            是否成功
        """
        try:
            html_content = self._generate_html()
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            app_logger.info(f"HTML导出成功: {output_path}")
            return True
        except Exception as e:
            app_logger.error(f"HTML导出失败: {e}")
            return False
    
    def _generate_html(self) -> str:
        """生成HTML内容"""
        stats = self.get_statistics()
        
        # HTML头部
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.homework_title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Microsoft YaHei", sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: #fff;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.15);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 28px;
            margin-bottom: 10px;
        }}
        .header .meta {{
            opacity: 0.9;
            font-size: 14px;
        }}
        .stats-bar {{
            display: flex;
            justify-content: space-around;
            padding: 20px;
            background: #f8fafc;
            border-bottom: 1px solid #e2e8f0;
        }}
        .stat-item {{
            text-align: center;
        }}
        .stat-value {{
            font-size: 24px;
            font-weight: bold;
            color: #667eea;
        }}
        .stat-label {{
            font-size: 12px;
            color: #64748b;
            margin-top: 4px;
        }}
        .stat-item.correct .stat-value {{ color: #22c55e; }}
        .stat-item.wrong .stat-value {{ color: #ef4444; }}
        .content {{
            padding: 30px;
        }}
        .question-card {{
            background: #fff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            transition: box-shadow 0.2s;
        }}
        .question-card:hover {{
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        }}
        .question-header {{
            display: flex;
            align-items: center;
            margin-bottom: 12px;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .question-number {{
            background: #667eea;
            color: white;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 500;
        }}
        .question-type {{
            background: #f1f5f9;
            color: #64748b;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
        }}
        .question-status {{
            margin-left: auto;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 500;
        }}
        .question-status.correct {{
            background: #dcfce7;
            color: #16a34a;
        }}
        .question-status.wrong {{
            background: #fee2e2;
            color: #dc2626;
        }}
        .question-content {{
            font-size: 15px;
            line-height: 1.7;
            color: #1e293b;
            margin-bottom: 16px;
        }}
        .options-list {{
            list-style: none;
            margin-bottom: 16px;
        }}
        .options-list li {{
            padding: 10px 14px;
            margin-bottom: 8px;
            background: #f8fafc;
            border-radius: 8px;
            font-size: 14px;
            color: #475569;
            border: 1px solid transparent;
        }}
        .options-list li.selected {{
            background: #eff6ff;
            border-color: #3b82f6;
        }}
        .options-list li.correct-option {{
            background: #f0fdf4;
            border-color: #22c55e;
        }}
        .answer-section {{
            padding: 12px 16px;
            border-radius: 8px;
            margin-top: 12px;
            font-size: 14px;
        }}
        .answer-section.my-answer {{
            background: #eff6ff;
            border-left: 4px solid #3b82f6;
        }}
        .answer-section.correct-answer {{
            background: #f0fdf4;
            border-left: 4px solid #22c55e;
        }}
        .answer-section.analysis {{
            background: #fef3c7;
            border-left: 4px solid #f59e0b;
        }}
        .answer-label {{
            font-weight: 600;
            margin-right: 8px;
        }}
        .score-info {{
            margin-top: 12px;
            font-size: 13px;
            color: #64748b;
        }}
        .separator {{
            border: none;
            height: 1px;
            background: linear-gradient(to right, transparent, #e2e8f0, transparent);
            margin: 20px 0;
        }}
        .footer {{
            text-align: center;
            padding: 20px;
            background: #f8fafc;
            color: #94a3b8;
            font-size: 12px;
        }}
        .question-image {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            margin: 10px 0;
        }}
        @media print {{
            body {{ background: white; padding: 0; }}
            .container {{ box-shadow: none; }}
            .question-card {{ break-inside: avoid; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{self.homework_title}</h1>
"""
        
        if self.options.include_export_time:
            html += f'            <div class="meta">导出时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>\n'
        
        html += """        </div>
"""
        
        # 统计信息
        if self.options.include_statistics:
            html += f"""        <div class="stats-bar">
            <div class="stat-item">
                <div class="stat-value">{stats['total_questions']}</div>
                <div class="stat-label">总题数</div>
            </div>
            <div class="stat-item correct">
                <div class="stat-value">{stats['correct_count']}</div>
                <div class="stat-label">正确</div>
            </div>
            <div class="stat-item wrong">
                <div class="stat-value">{stats['wrong_count']}</div>
                <div class="stat-label">错误</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{stats['accuracy']}</div>
                <div class="stat-label">正确率</div>
            </div>
        </div>
"""
        
        html += '        <div class="content">\n'
        
        # 题目列表
        for i, q in enumerate(self.questions, 1):
            q_type = self._get_question_type(q)
            content = self._get_question_content(q)
            options = self._get_options(q)
            is_correct = self._is_correct(q)
            
            html += '            <div class="question-card">\n'
            html += '                <div class="question-header">\n'
            
            if self.options.include_question_number:
                html += f'                    <span class="question-number">第 {i} 题</span>\n'
            
            if self.options.include_question_type:
                html += f'                    <span class="question-type">{q_type}</span>\n'
            
            if self.options.show_correct_status and is_correct is not None:
                status_class = "correct" if is_correct else "wrong"
                status_text = "✓ 正确" if is_correct else "✗ 错误"
                html += f'                    <span class="question-status {status_class}">{status_text}</span>\n'
            
            html += '                </div>\n'
            html += f'                <div class="question-content">{self._escape_html(content)}</div>\n'
            
            # 选项
            if options:
                html += '                <ul class="options-list">\n'
                for opt in options:
                    html += f'                    <li>{self._escape_html(opt)}</li>\n'
                html += '                </ul>\n'
            
            # 我的答案
            if self.options.include_my_answer:
                my_answer = self._get_my_answer(q)
                if my_answer:
                    html += f'                <div class="answer-section my-answer"><span class="answer-label">我的答案:</span>{self._escape_html(my_answer)}</div>\n'
            
            # 正确答案
            if self.options.include_correct_answer:
                correct_answer = self._get_question_answer(q)
                if correct_answer:
                    html += f'                <div class="answer-section correct-answer"><span class="answer-label">正确答案:</span>{self._escape_html(correct_answer)}</div>\n'
            
            # 解析
            if self.options.include_analysis:
                analysis = self._get_analysis(q)
                if analysis:
                    html += f'                <div class="answer-section analysis"><span class="answer-label">解析:</span>{self._escape_html(analysis)}</div>\n'
            
            # 得分
            if self.options.include_score:
                score = q.get('score', '')
                if score:
                    html += f'                <div class="score-info">得分: {score}</div>\n'
            
            html += '            </div>\n'
            
            if self.options.include_separator and i < len(self.questions):
                html += '            <hr class="separator">\n'
        
        html += """        </div>
        <div class="footer">
            Generated by 学习通题目导出工具
        </div>
    </div>
</body>
</html>
"""
        return html
    
    def _escape_html(self, text: str) -> str:
        """转义HTML特殊字符"""
        if not text:
            return ""
        return (str(text)
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#39;'))
    
    # ==================== JSON 导出 ====================
    
    def export_json(self, output_path: str, pretty: bool = True) -> bool:
        """
        导出为JSON格式
        
        Args:
            output_path: 输出文件路径
            pretty: 是否格式化输出
            
        Returns:
            是否成功
        """
        try:
            data = self._generate_json_data()
            
            with open(output_path, 'w', encoding='utf-8') as f:
                if pretty:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                else:
                    json.dump(data, f, ensure_ascii=False)
            
            app_logger.info(f"JSON导出成功: {output_path}")
            return True
        except Exception as e:
            app_logger.error(f"JSON导出失败: {e}")
            return False
    
    def _generate_json_data(self) -> Dict:
        """生成JSON数据"""
        stats = self.get_statistics() if self.options.include_statistics else None
        
        # 根据选项过滤题目数据
        filtered_questions = []
        for q in self.questions:
            filtered = {
                'question_number': q.get('question_number', ''),
                'type': self._get_question_type(q),
                'content': self._get_question_content(q),
                'options': self._get_options(q),
            }
            
            if self.options.include_my_answer:
                filtered['my_answer'] = self._get_my_answer(q)
            
            if self.options.include_correct_answer:
                filtered['correct_answer'] = self._get_question_answer(q)
            
            if self.options.include_score:
                filtered['score'] = q.get('score', '')
                filtered['is_correct'] = self._is_correct(q)
            
            if self.options.include_analysis:
                filtered['analysis'] = self._get_analysis(q)
            
            if self.options.include_images:
                filtered['title_images'] = q.get('title_images', [])
                filtered['option_images'] = q.get('optionImages', [])
            
            filtered_questions.append(filtered)
        
        return {
            'title': self.homework_title,
            'export_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'export_options': self.options.to_dict(),
            'statistics': stats,
            'questions': filtered_questions
        }
    
    # ==================== Markdown 导出 ====================
    
    def export_markdown(self, output_path: str) -> bool:
        """
        导出为Markdown格式
        
        Args:
            output_path: 输出文件路径
            
        Returns:
            是否成功
        """
        try:
            md_content = self._generate_markdown()
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(md_content)
            
            app_logger.info(f"Markdown导出成功: {output_path}")
            return True
        except Exception as e:
            app_logger.error(f"Markdown导出失败: {e}")
            return False
    
    def _generate_markdown(self) -> str:
        """生成Markdown内容"""
        stats = self.get_statistics()
        
        md = f"# {self.homework_title}\n\n"
        
        if self.options.include_export_time:
            md += f"> 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        # 统计信息
        if self.options.include_statistics:
            md += "## 📊 统计信息\n\n"
            md += f"| 项目 | 数值 |\n"
            md += f"|------|------|\n"
            md += f"| 总题数 | {stats['total_questions']} |\n"
            md += f"| 正确 | {stats['correct_count']} |\n"
            md += f"| 错误 | {stats['wrong_count']} |\n"
            md += f"| 正确率 | {stats['accuracy']} |\n"
            
            if stats['question_types']:
                md += "\n### 题型分布\n\n"
                for q_type, count in stats['question_types'].items():
                    md += f"- {q_type}: {count} 题\n"
            
            md += "\n"
        
        md += "## 📝 题目列表\n\n"
        
        # 题目
        for i, q in enumerate(self.questions, 1):
            q_type = self._get_question_type(q)
            content = self._get_question_content(q)
            options = self._get_options(q)
            is_correct = self._is_correct(q)
            
            # 题目标题
            if self.options.include_question_number:
                md += f"### {i}. "
            else:
                md += "### "
            
            if self.options.include_question_type:
                md += f"[{q_type}] "
            
            md += f"{content}\n\n"
            
            # 正确/错误状态
            if self.options.show_correct_status and is_correct is not None:
                status = "✅ 正确" if is_correct else "❌ 错误"
                md += f"**状态**: {status}\n\n"
            
            # 选项
            if options:
                for opt in options:
                    md += f"- {opt}\n"
                md += "\n"
            
            # 我的答案
            if self.options.include_my_answer:
                my_answer = self._get_my_answer(q)
                if my_answer:
                    md += f"**我的答案**: {my_answer}\n\n"
            
            # 正确答案
            if self.options.include_correct_answer:
                correct_answer = self._get_question_answer(q)
                if correct_answer:
                    md += f"**正确答案**: {correct_answer}\n\n"
            
            # 解析
            if self.options.include_analysis:
                analysis = self._get_analysis(q)
                if analysis:
                    md += f"> **解析**: {analysis}\n\n"
            
            # 得分
            if self.options.include_score:
                score = q.get('score', '')
                if score:
                    md += f"*得分: {score}*\n\n"
            
            if self.options.include_separator and i < len(self.questions):
                md += "---\n\n"
        
        return md
    
    # ==================== Word (DOCX) 导出 ====================
    
    def export_word(self, output_path: str) -> bool:
        """
        导出为Word格式 (DOCX)
        
        Args:
            output_path: 输出文件路径
            
        Returns:
            是否成功
        """
        try:
            # 尝试导入python-docx
            from docx import Document
            from docx.shared import Inches, Pt, RGBColor
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.enum.style import WD_STYLE_TYPE
        except ImportError:
            app_logger.error("Word导出需要安装python-docx库: pip install python-docx")
            return False
        
        try:
            doc = Document()
            stats = self.get_statistics()
            
            # 标题
            title = doc.add_heading(self.homework_title, 0)
            title.alignment = WD_ALIGN_PARAGRAPH.CENTER
            
            # 导出时间
            if self.options.include_export_time:
                time_para = doc.add_paragraph()
                time_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                time_run = time_para.add_run(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                time_run.font.size = Pt(10)
                time_run.font.color.rgb = RGBColor(128, 128, 128)
            
            doc.add_paragraph()
            
            # 统计信息
            if self.options.include_statistics:
                doc.add_heading('答题统计', level=1)
                
                table = doc.add_table(rows=5, cols=2)
                table.style = 'Table Grid'
                
                cells = [
                    ('总题数', str(stats['total_questions'])),
                    ('正确', str(stats['correct_count'])),
                    ('错误', str(stats['wrong_count'])),
                    ('正确率', stats['accuracy']),
                    ('图片数', str(stats['total_images']))
                ]
                
                for i, (label, value) in enumerate(cells):
                    table.rows[i].cells[0].text = label
                    table.rows[i].cells[1].text = value
                
                doc.add_paragraph()
            
            # 题目列表
            doc.add_heading('题目列表', level=1)
            
            for i, q in enumerate(self.questions, 1):
                q_type = self._get_question_type(q)
                content = self._get_question_content(q)
                options = self._get_options(q)
                is_correct = self._is_correct(q)
                
                # 题目标题段落
                q_para = doc.add_paragraph()
                
                if self.options.include_question_number:
                    num_run = q_para.add_run(f"{i}. ")
                    num_run.bold = True
                
                if self.options.include_question_type:
                    type_run = q_para.add_run(f"[{q_type}] ")
                    type_run.font.color.rgb = RGBColor(52, 152, 219)
                
                content_run = q_para.add_run(content)
                content_run.bold = True
                
                # 正确/错误状态
                if self.options.show_correct_status and is_correct is not None:
                    status_para = doc.add_paragraph()
                    if is_correct:
                        status_run = status_para.add_run("✓ 正确")
                        status_run.font.color.rgb = RGBColor(39, 174, 96)
                    else:
                        status_run = status_para.add_run("✗ 错误")
                        status_run.font.color.rgb = RGBColor(231, 76, 60)
                    status_run.bold = True
                
                # 选项
                if options:
                    for opt in options:
                        opt_para = doc.add_paragraph(opt, style='List Bullet')
                
                # 我的答案
                if self.options.include_my_answer:
                    my_answer = self._get_my_answer(q)
                    if my_answer:
                        ans_para = doc.add_paragraph()
                        label_run = ans_para.add_run("我的答案: ")
                        label_run.bold = True
                        label_run.font.color.rgb = RGBColor(0, 102, 204)
                        ans_para.add_run(my_answer).font.color.rgb = RGBColor(0, 102, 204)
                
                # 正确答案
                if self.options.include_correct_answer:
                    correct_answer = self._get_question_answer(q)
                    if correct_answer:
                        ans_para = doc.add_paragraph()
                        label_run = ans_para.add_run("正确答案: ")
                        label_run.bold = True
                        label_run.font.color.rgb = RGBColor(0, 153, 0)
                        ans_para.add_run(correct_answer).font.color.rgb = RGBColor(0, 153, 0)
                
                # 解析
                if self.options.include_analysis:
                    analysis = self._get_analysis(q)
                    if analysis:
                        ans_para = doc.add_paragraph()
                        label_run = ans_para.add_run("解析: ")
                        label_run.bold = True
                        label_run.font.color.rgb = RGBColor(255, 102, 0)
                        ans_para.add_run(analysis).font.color.rgb = RGBColor(255, 102, 0)
                
                # 得分
                if self.options.include_score:
                    score = q.get('score', '')
                    if score:
                        score_para = doc.add_paragraph()
                        score_run = score_para.add_run(f"得分: {score}")
                        score_run.font.size = Pt(9)
                        score_run.font.color.rgb = RGBColor(128, 128, 128)
                
                # 分隔线
                if self.options.include_separator and i < len(self.questions):
                    sep_para = doc.add_paragraph()
                    sep_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    sep_run = sep_para.add_run("─" * 50)
                    sep_run.font.color.rgb = RGBColor(204, 204, 204)
            
            doc.save(output_path)
            app_logger.info(f"Word导出成功: {output_path}")
            return True
            
        except Exception as e:
            app_logger.error(f"Word导出失败: {e}")
            return False
    
    # ==================== PDF 导出 ====================
    
    def export_pdf(self, output_path: str) -> bool:
        """
        导出为PDF格式
        
        Args:
            output_path: 输出文件路径
            
        Returns:
            是否成功
        """
        try:
            # 尝试导入reportlab
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch, cm
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
        except ImportError:
            app_logger.error("PDF导出需要安装reportlab库: pip install reportlab")
            return False
        
        try:
            # 注册中文字体 (尝试多种字体)
            chinese_font_registered = False
            font_paths = [
                "C:/Windows/Fonts/simhei.ttf",  # 黑体
                "C:/Windows/Fonts/simsun.ttc",  # 宋体
                "C:/Windows/Fonts/msyh.ttc",    # 微软雅黑
            ]
            
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(TTFont('ChineseFont', font_path))
                        chinese_font_registered = True
                        break
                    except:
                        continue
            
            if not chinese_font_registered:
                app_logger.warning("未找到中文字体，PDF可能显示乱码")
            
            doc = SimpleDocTemplate(output_path, pagesize=A4,
                                   rightMargin=2*cm, leftMargin=2*cm,
                                   topMargin=2*cm, bottomMargin=2*cm)
            
            story = []
            styles = getSampleStyleSheet()
            
            # 创建中文样式
            if chinese_font_registered:
                title_style = ParagraphStyle(
                    'ChineseTitle',
                    parent=styles['Title'],
                    fontName='ChineseFont',
                    fontSize=18,
                    alignment=1
                )
                normal_style = ParagraphStyle(
                    'ChineseNormal',
                    parent=styles['Normal'],
                    fontName='ChineseFont',
                    fontSize=11,
                    leading=16
                )
                heading_style = ParagraphStyle(
                    'ChineseHeading',
                    parent=styles['Heading2'],
                    fontName='ChineseFont',
                    fontSize=14
                )
            else:
                title_style = styles['Title']
                normal_style = styles['Normal']
                heading_style = styles['Heading2']
            
            stats = self.get_statistics()
            
            # 标题
            story.append(Paragraph(self.homework_title, title_style))
            story.append(Spacer(1, 12))
            
            # 导出时间
            if self.options.include_export_time:
                time_text = f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                story.append(Paragraph(time_text, normal_style))
                story.append(Spacer(1, 20))
            
            # 统计信息
            if self.options.include_statistics:
                story.append(Paragraph("答题统计", heading_style))
                story.append(Spacer(1, 10))
                
                table_data = [
                    ['总题数', str(stats['total_questions'])],
                    ['正确', str(stats['correct_count'])],
                    ['错误', str(stats['wrong_count'])],
                    ['正确率', stats['accuracy']]
                ]
                
                table = Table(table_data, colWidths=[3*cm, 3*cm])
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), colors.whitesmoke),
                    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                    ('FONTNAME', (0, 0), (-1, -1), 'ChineseFont' if chinese_font_registered else 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                story.append(table)
                story.append(Spacer(1, 20))
            
            # 题目列表
            story.append(Paragraph("题目列表", heading_style))
            story.append(Spacer(1, 10))
            
            for i, q in enumerate(self.questions, 1):
                q_type = self._get_question_type(q)
                content = self._get_question_content(q)
                options = self._get_options(q)
                is_correct = self._is_correct(q)
                
                # 题目
                q_text = ""
                if self.options.include_question_number:
                    q_text += f"{i}. "
                if self.options.include_question_type:
                    q_text += f"[{q_type}] "
                q_text += content
                
                story.append(Paragraph(f"<b>{q_text}</b>", normal_style))
                story.append(Spacer(1, 6))
                
                # 选项
                if options:
                    for opt in options:
                        story.append(Paragraph(f"    {opt}", normal_style))
                    story.append(Spacer(1, 6))
                
                # 我的答案
                if self.options.include_my_answer:
                    my_answer = self._get_my_answer(q)
                    if my_answer:
                        story.append(Paragraph(f"<font color='blue'><b>我的答案:</b> {my_answer}</font>", normal_style))
                
                # 正确答案
                if self.options.include_correct_answer:
                    correct_answer = self._get_question_answer(q)
                    if correct_answer:
                        story.append(Paragraph(f"<font color='green'><b>正确答案:</b> {correct_answer}</font>", normal_style))
                
                # 解析
                if self.options.include_analysis:
                    analysis = self._get_analysis(q)
                    if analysis:
                        story.append(Paragraph(f"<font color='orange'><b>解析:</b> {analysis}</font>", normal_style))
                
                story.append(Spacer(1, 15))
                
                if self.options.include_separator and i < len(self.questions):
                    story.append(Paragraph("─" * 60, normal_style))
                    story.append(Spacer(1, 10))
            
            doc.build(story)
            app_logger.info(f"PDF导出成功: {output_path}")
            return True
            
        except Exception as e:
            app_logger.error(f"PDF导出失败: {e}")
            return False
    
    # ==================== 批量导出 ====================
    
    def export_all(self, output_dir: str, base_name: str = None) -> Dict[str, bool]:
        """
        导出所有格式
        
        Args:
            output_dir: 输出目录
            base_name: 基础文件名（不含扩展名）
            
        Returns:
            各格式导出结果
        """
        if base_name is None:
            base_name = self._sanitize_filename(self.homework_title)
        
        os.makedirs(output_dir, exist_ok=True)
        
        results = {}
        
        # HTML
        html_path = os.path.join(output_dir, f"{base_name}.html")
        results['html'] = self.export_html(html_path)
        
        # JSON
        json_path = os.path.join(output_dir, f"{base_name}.json")
        results['json'] = self.export_json(json_path)
        
        # Markdown
        md_path = os.path.join(output_dir, f"{base_name}.md")
        results['markdown'] = self.export_markdown(md_path)
        
        # Word
        docx_path = os.path.join(output_dir, f"{base_name}.docx")
        results['word'] = self.export_word(docx_path)
        
        # PDF
        pdf_path = os.path.join(output_dir, f"{base_name}.pdf")
        results['pdf'] = self.export_pdf(pdf_path)
        
        return results


# 便捷导出函数
def quick_export(questions: List[Dict], 
                 homework_title: str,
                 output_path: str,
                 format: str = 'html',
                 include_my_answer: bool = True,
                 include_correct_answer: bool = True) -> bool:
    """
    快速导出题目
    
    Args:
        questions: 题目列表
        homework_title: 作业标题
        output_path: 输出路径
        format: 格式 ('html', 'json', 'md', 'word', 'pdf')
        include_my_answer: 包含我的答案
        include_correct_answer: 包含正确答案
        
    Returns:
        是否成功
    """
    exporter = QuestionExporter(questions, homework_title)
    exporter.options.include_my_answer = include_my_answer
    exporter.options.include_correct_answer = include_correct_answer
    
    format = format.lower()
    
    if format == 'html':
        return exporter.export_html(output_path)
    elif format == 'json':
        return exporter.export_json(output_path)
    elif format in ('md', 'markdown'):
        return exporter.export_markdown(output_path)
    elif format in ('word', 'docx'):
        return exporter.export_word(output_path)
    elif format == 'pdf':
        return exporter.export_pdf(output_path)
    else:
        app_logger.error(f"不支持的格式: {format}")
        return False
