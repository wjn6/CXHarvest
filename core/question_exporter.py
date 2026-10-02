#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
题目导出模块 - 支持多种格式导出
整合多个优秀脚本的导出逻辑，提供最强大的导出功能

支持格式：
- HTML：精美网页格式，支持打印
- JSON：结构化数据，便于二次处理
- Word (DOCX)：正式文档格式
- Excel (XLSX)：表格格式，便于筛选统计
- PDF：通用便携格式
- Markdown：纯文本标记格式

"""

import os
import json
import base64
import re
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path

from core.enterprise_logger import app_logger
from core.version import __version__, APP_NAME
from core.common import get_question_field

def _escape_xml(text: str) -> str:
    """转义 XML/HTML 特殊字符（供 reportlab Paragraph 使用）"""
    if not text:
        return ""
    return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#39;'))


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
        self.include_separator = False       # 题目间添加分割线
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
    
    def __init__(self, questions: List[Dict], homework_title: str = "作业题目", session=None):
        """
        初始化导出器
        
        Args:
            questions: 题目列表
            homework_title: 作业标题
            session: 可选的 requests.Session，用于下载需要认证的图片
        """
        self.questions = questions
        self.homework_title = homework_title
        self.options = ExportOptions()
        self._statistics = None
        self._session = session
    
    def set_options(self, options: ExportOptions):
        """设置导出选项"""
        self.options = options
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        if self._statistics is None:
            self._statistics = self._calculate_statistics()
        return self._statistics

    @staticmethod
    def _to_text(value, default: str = "") -> str:
        """将平台返回的标量字段稳定地转换为文本。"""
        if value is None:
            return default
        if isinstance(value, str):
            return value
        return str(value)
    
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
            is_correct = get_question_field(q, 'is_correct', None)
            if is_correct is True:
                stats['correct_count'] += 1
            elif is_correct is False:
                stats['wrong_count'] += 1
            else:
                stats['unanswered_count'] += 1
            
            # 统计分数
            score = self._parse_score(get_question_field(q, 'score', None))
            if score is not None:
                stats['total_score'] += score

            max_score = self._parse_score(get_question_field(q, 'total_score', None))
            if max_score is not None:
                stats['max_score'] += max_score
            
            # 统计题型
            q_type = self._to_text(
                get_question_field(q, 'question_type', '未知'), '未知'
            ) or '未知'
            stats['question_types'][q_type] = stats['question_types'].get(q_type, 0) + 1
            
            # 统计图片
            content_images = get_question_field(q, 'content_images', [])
            if not isinstance(content_images, (list, tuple)):
                content_images = []
            stats['total_images'] += len(content_images)
            options = q.get('options', [])
            if not isinstance(options, (list, tuple)):
                options = []
            for opt in options:
                if isinstance(opt, dict):
                    images = opt.get('images', [])
                    if isinstance(images, (list, tuple)):
                        stats['total_images'] += len(images)
        
        # 计算正确率
        if stats['total_questions'] > 0:
            stats['accuracy'] = f"{(stats['correct_count'] / stats['total_questions'] * 100):.1f}%"
        else:
            stats['accuracy'] = "0%"
        
        return stats

    @staticmethod
    def _parse_score(value) -> Optional[float]:
        """从 ``2.5分``、``2/5`` 等显示文本中读取第一个数值。"""
        if value is None or isinstance(value, bool):
            return None
        match = re.search(r'-?\d+(?:\.\d+)?', str(value))
        if not match:
            return None
        try:
            return float(match.group(0))
        except ValueError:
            return None
    
    def _get_question_content(self, q: Dict) -> str:
        """获取题目内容，清理图片占位符"""
        content = self._to_text(get_question_field(q, 'content', ''))
        # 清理图片占位符文本，如 [图片:333.jpg] 或 [图片:图片]
        content = re.sub(r'\[图片[：:][^\]]*\]', '', content).strip()
        return content
    
    def _get_question_type(self, q: Dict) -> str:
        """获取题目类型"""
        return self._to_text(get_question_field(q, 'question_type', '未知'), '未知') or '未知'
    
    def _get_question_answer(self, q: Dict) -> str:
        """获取正确答案"""
        return self._to_text(get_question_field(q, 'correct_answer', ''))
    
    def _get_my_answer(self, q: Dict) -> str:
        """获取我的答案"""
        return self._to_text(get_question_field(q, 'my_answer', ''))
    
    def _get_analysis(self, q: Dict) -> str:
        """获取解析"""
        return self._to_text(get_question_field(q, 'explanation', ''))
    
    def _get_options(self, q: Dict) -> List:
        """获取选项列表"""
        options = q.get('options', [])
        if not isinstance(options, (list, tuple)):
            return []
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
        return get_question_field(q, 'is_correct', None)
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名中的非法字符"""
        from core.common import sanitize_filename
        return sanitize_filename(filename)
    
    # ==================== HTML 导出 ====================
    
    def export_html(self, output_path: str, template_id: str = 'default') -> bool:
        """
        导出为HTML格式
        
        Args:
            output_path: 输出文件路径
            template_id: HTML 模板 ID
            
        Returns:
            是否成功
        """
        try:
            from core.html_templates import get_template_registry
            template = get_template_registry().get(template_id)
            html_content = self._generate_html(template)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            app_logger.info(f"HTML导出成功: {output_path} (模板: {template.name})")
            return True
        except Exception as e:
            app_logger.error(f"HTML导出失败: {e}")
            return False
    
    def _generate_html(self, template=None) -> str:
        """生成HTML内容——委托给模板的 render_html"""
        if template is None:
            from core.html_templates import get_template_registry
            template = get_template_registry().get('default')
        return template.render_html(self)
    
    def _get_image_bytes(self, img_data: dict) -> Optional[bytes]:
        """从图片数据获取字节流"""
        max_bytes = 20 * 1024 * 1024
        try:
            # 优先使用data字段（base64编码）
            data = img_data.get('data', '')
            if data and data.startswith('data:image'):
                if ',' in data:
                    base64_str = data.split(',', 1)[1]
                    if len(base64_str) > (max_bytes * 4 // 3 + 8):
                        return None
                    decoded = base64.b64decode(base64_str, validate=True)
                    return decoded if len(decoded) <= max_bytes else None
            
            # 尝试src字段
            src = img_data.get('src', '')
            if src and src.startswith('data:image'):
                if ',' in src:
                    base64_str = src.split(',', 1)[1]
                    if len(base64_str) > (max_bytes * 4 // 3 + 8):
                        return None
                    decoded = base64.b64decode(base64_str, validate=True)
                    return decoded if len(decoded) <= max_bytes else None
            
            # URL图片 - 尝试下载
            # 优先使用认证 session（超星图片需要 cookie）；
            # 若无 session 则 fallback 到无认证请求（公开图片仍可下载，需认证的会返回 403）
            if src and src.startswith('http'):
                try:
                    if self._session:
                        response = self._session.get(src, timeout=(5, 10), stream=True)
                    else:
                        import requests
                        response = requests.get(src, timeout=(5, 10), stream=True)
                    try:
                        if response.status_code != 200:
                            return None
                        content_length = int(response.headers.get('content-length') or 0)
                        if content_length > max_bytes:
                            app_logger.warning(f"图片过大，已跳过: {src}")
                            return None
                        chunks = []
                        total = 0
                        for chunk in response.iter_content(64 * 1024):
                            if not chunk:
                                continue
                            total += len(chunk)
                            if total > max_bytes:
                                app_logger.warning(f"图片下载超过大小限制，已跳过: {src}")
                                return None
                            chunks.append(chunk)
                        return b''.join(chunks)
                    finally:
                        response.close()
                except Exception as e:
                    app_logger.warning(f"下载图片失败: {src}, {e}")
                    return None
            
            return None
        except Exception as e:
            app_logger.warning(f"获取图片字节流失败: {e}")
            return None
    
    def _to_png_bytes(self, img_bytes: bytes) -> Optional[bytes]:
        """把任意格式的图片字节统一转成 PNG（Word / Excel 共用）

        抓取到的图片可能是 JPEG / WebP / RGBA / 调色板等任意格式，
        而 python-docx 与 xlsxwriter 对格式支持有限，统一转 PNG 更稳。
        透明通道会合成到白底，避免转 RGB 后背景发黑。
        """
        import io
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(img_bytes))
            if img.mode in ('RGBA', 'LA', 'P'):
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            return buf.getvalue()
        except Exception as e:
            app_logger.warning(f"图片转PNG失败: {type(e).__name__}: {e}")
            return None

    def _collect_question_images(self, q: Dict) -> List[dict]:
        """收集一道题关联的全部图片（题干/选项/我的答案/正确答案/解析）"""
        images: List[dict] = []
        for field in ('content_images', 'option_images', 'my_answer_images',
                      'correct_answer_images', 'explanation_images'):
            images.extend(get_question_field(q, field, []) or [])
        for opt in (q.get('options') or []):
            if isinstance(opt, dict):
                images.extend(opt.get('images') or [])
        return [img for img in images if isinstance(img, dict)]

    def _insert_images_to_excel(self, worksheet, row: int, col: int, images: List,
                                max_width_px: int = 200, padding: int = 4) -> int:
        """把图片纵向堆叠插入 Excel 单元格，返回该行所需高度（像素）

        多张图片共用一个单元格时必须手动累加 y_offset，
        否则后插入的会盖住先插入的。

        单位说明：xlsxwriter 的 set_row 行高单位是磅（1px ≈ 0.75 磅 @96DPI），
        Excel 行高上限 409.5 磅（≈546px）。若图片堆叠总高超过上限，
        等比缩小整组图片，避免溢出覆盖下一题所在的行。
        """
        import io
        if not images or not self.options.include_images:
            return 0

        # 第一遍：解码并按最大宽度缩放，得到各图显示尺寸
        sized = []
        for img in images:
            raw = self._get_image_bytes(img)
            if not raw:
                continue
            png = self._to_png_bytes(raw)
            if not png:
                continue
            try:
                from PIL import Image as PILImage
                width, height = PILImage.open(io.BytesIO(png)).size
                scale = min(1.0, max_width_px / float(width)) if width else 1.0
                sized.append([png, scale, int(width * scale), int(height * scale)])
            except Exception as e:
                app_logger.warning(f"Excel图片解码失败: {type(e).__name__}: {e}")

        if not sized:
            return 0

        # 第二遍：堆叠总高超过行高上限时，等比压缩整组图片
        MAX_ROW_PX = 540  # 409.5 磅 ≈ 546px，留余量
        gaps = padding * (len(sized) - 1)
        total_h = sum(item[3] for item in sized) + gaps
        if total_h > MAX_ROW_PX:
            avail = float(MAX_ROW_PX - gaps)
            img_h = float(sum(item[3] for item in sized))
            if img_h > 0 and avail > 0:
                shrink = avail / img_h
                for item in sized:
                    item[1] *= shrink
                    item[2] = max(1, int(item[2] * shrink))
                    item[3] = max(1, int(item[3] * shrink))
                total_h = sum(item[3] for item in sized) + gaps

        # 第三遍：插入并累计 y_offset
        y_offset = 0
        for i, (png, scale, _w, h) in enumerate(sized):
            try:
                worksheet.insert_image(row, col, f'image_{row}_{col}_{i}.png', {
                    'image_data': io.BytesIO(png),
                    'x_scale': scale,
                    'y_scale': scale,
                    'y_offset': y_offset,
                })
                y_offset += h + padding
            except Exception as e:
                app_logger.warning(f"Excel插入图片失败: {type(e).__name__}: {e}")

        # 行高：像素转磅（×0.75），并夹在上限内
        worksheet.set_row(row, min(409.0, total_h * 0.75))
        return total_h

    def _add_images_to_word(self, doc, images: List, max_width_inches: float = 6.0):
        """向Word文档添加图片，保持原始比例"""
        from docx.shared import Inches, Pt
        import io
        
        if not images or not self.options.include_images:
            return
        
        for img in images:
            if not isinstance(img, dict):
                continue
            
            img_bytes = self._get_image_bytes(img)
            if not img_bytes:
                continue
            
            try:
                # 统一转 PNG，确保 python-docx 能识别
                from PIL import Image
                png_bytes = self._to_png_bytes(img_bytes)
                if not png_bytes:
                    continue

                png_buffer = io.BytesIO(png_bytes)
                orig_width, _ = Image.open(png_buffer).size
                png_buffer.seek(0)

                # 计算尺寸：像素转英寸（96 DPI），但限制最大宽度
                width_inches = orig_width / 96.0
                if width_inches > max_width_inches:
                    width_inches = max_width_inches

                doc.add_picture(png_buffer, width=Inches(width_inches))
            except Exception as e:
                app_logger.warning(f"Word添加图片失败: {type(e).__name__}: {e}")
    
    def _add_images_to_pdf(self, story: List, images: List, max_width: float = 400, max_height: float = 500):
        """向PDF文档添加图片
        
        Args:
            story: PDF story列表
            images: 图片数据列表
            max_width: 最大宽度（点）
            max_height: 最大高度（点），防止图片超出页面
        """
        import io
        try:
            from reportlab.platypus import Image as RLImage
            from reportlab.lib.units import inch
        except ImportError:
            return
        
        if not images or not self.options.include_images:
            return
        
        for img in images:
            img_bytes = self._get_image_bytes(img) if isinstance(img, dict) else None
            if img_bytes:
                try:
                    img_stream = io.BytesIO(img_bytes)
                    rl_img = RLImage(img_stream)
                    
                    # 按比例缩放 - 同时限制宽度和高度
                    width_ratio = max_width / rl_img.drawWidth if rl_img.drawWidth > max_width else 1
                    height_ratio = max_height / rl_img.drawHeight if rl_img.drawHeight > max_height else 1
                    ratio = min(width_ratio, height_ratio)
                    
                    if ratio < 1:
                        rl_img.drawWidth *= ratio
                        rl_img.drawHeight *= ratio
                    
                    story.append(rl_img)
                except Exception as e:
                    app_logger.warning(f"PDF添加图片失败: {e}")
    
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
                'content': self._get_question_content(q),
                'options': self._get_options(q),
            }

            if self.options.include_question_number:
                filtered['question_number'] = q.get('question_number', '')

            if self.options.include_question_type:
                filtered['question_type'] = self._get_question_type(q)

            if self.options.include_homework_title:
                filtered['homework_title'] = q.get('homework_title', '')

            section = q.get('section', None)
            if section:
                filtered['section'] = section
            
            if self.options.include_my_answer:
                filtered['my_answer'] = self._get_my_answer(q)
            
            if self.options.include_correct_answer:
                filtered['correct_answer'] = self._get_question_answer(q)
            
            if self.options.include_score:
                filtered['score'] = get_question_field(q, 'score', '')
                filtered['total_score'] = get_question_field(q, 'total_score', '')
                filtered['is_correct'] = self._is_correct(q)
            
            if self.options.include_analysis:
                filtered['explanation'] = self._get_analysis(q)
            
            if self.options.include_images:
                filtered['content_images'] = get_question_field(q, 'content_images', [])
                filtered['option_images'] = get_question_field(q, 'option_images', [])
                filtered['my_answer_images'] = get_question_field(q, 'my_answer_images', [])
                filtered['correct_answer_images'] = get_question_field(q, 'correct_answer_images', [])
                filtered['explanation_images'] = get_question_field(q, 'explanation_images', [])
            
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
            
            # 题目图片
            content_images = get_question_field(q, 'content_images', [])
            if content_images and self.options.include_images:
                for img in content_images:
                    md += self._render_image_markdown(img)
            
            # 正确/错误状态
            if self.options.show_correct_status and is_correct is not None:
                status = "✅ 正确" if is_correct else "❌ 错误"
                md += f"**状态**: {status}\n\n"
            
            # 选项
            raw_options = q.get('options', [])
            if raw_options:
                for opt in raw_options:
                    if isinstance(opt, dict):
                        label = opt.get('label', '')
                        opt_content = opt.get('content', '')
                        opt_images = opt.get('images', [])
                        if opt_images:
                            opt_content = re.sub(r'\[图片选项[：:]\s*\d+张\]', '', opt_content).strip()
                        md += f"- {label}. {opt_content}\n"
                        if opt_images and self.options.include_images:
                            for img in opt_images:
                                md += f"  {self._render_image_markdown(img)}"
                    else:
                        md += f"- {opt}\n"
                md += "\n"
            
            # 我的答案
            if self.options.include_my_answer:
                my_answer = self._get_my_answer(q)
                if my_answer and '[图片' not in my_answer:
                    md += f"**我的答案**: {my_answer}\n\n"
                my_answer_images = get_question_field(q, 'my_answer_images', [])
                if my_answer_images and self.options.include_images:
                    for img in my_answer_images:
                        md += self._render_image_markdown(img)
            
            # 正确答案
            if self.options.include_correct_answer:
                correct_answer = self._get_question_answer(q)
                if correct_answer and '[图片' not in correct_answer:
                    md += f"**正确答案**: {correct_answer}\n\n"
                correct_answer_images = get_question_field(q, 'correct_answer_images', [])
                if correct_answer_images and self.options.include_images:
                    for img in correct_answer_images:
                        md += self._render_image_markdown(img)
            
            # 解析
            if self.options.include_analysis:
                analysis = self._get_analysis(q)
                if analysis:
                    md += f"> **解析**: {analysis}\n\n"
            
            # 得分
            if self.options.include_score:
                score = get_question_field(q, 'score', '')
                if score:
                    md += f"*得分: {score}*\n\n"
            
            if self.options.include_separator and i < len(self.questions):
                md += "---\n\n"
        
        return md

    def _render_image_markdown(self, img) -> str:
        """将图片渲染为 Markdown 格式"""
        if isinstance(img, dict):
            src = img.get('data') or img.get('src', '')
            alt = img.get('alt', '图片')
        else:
            src = str(img)
            alt = '图片'
        if src:
            from core.html_templates import HtmlTemplate
            safe_src = HtmlTemplate._safe_src(src)
            if not safe_src:
                app_logger.warning(f"Markdown 已丢弃不安全的图片地址: {str(src)[:60]}")
                return ""
            safe_alt = str(alt).replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]')
            safe_src = (safe_src.replace(' ', '%20')
                        .replace('(', '%28').replace(')', '%29')
                        .replace('<', '%3C').replace('>', '%3E'))
            return f"![{safe_alt}]({safe_src})\n\n"
        return ""

    def export_excel(self, output_path: str) -> bool:
        try:
            import xlsxwriter
        except ImportError:
            app_logger.error("Excel导出需要安装xlsxwriter库: pip install xlsxwriter")
            return False

        workbook = None
        try:
            # 题目来自远端页面，禁止把以 =/+/-/@ 开头的文本解释成公式或 URL。
            # 这样即使导出内容恶意，也只会作为普通单元格文本打开。
            workbook = xlsxwriter.Workbook(output_path, {
                'strings_to_formulas': False,
                'strings_to_urls': False,
            })
            worksheet = workbook.add_worksheet('题目列表')

            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#0891B2',
                'font_color': 'white',
                'border': 1,
                'align': 'center',
                'valign': 'vcenter'
            })
            cell_format = workbook.add_format({
                'border': 1,
                'text_wrap': True,
                'valign': 'top'
            })

            headers = []
            if self.options.include_question_number:
                headers.append('序号')
            if self.options.include_homework_title:
                headers.append('作业')
            headers.append('题目')
            if self.options.include_question_type:
                headers.append('类型')
            headers.append('选项')
            if self.options.include_my_answer:
                headers.append('我的答案')
            if self.options.include_correct_answer:
                headers.append('正确答案')
            if self.options.include_score:
                headers.append('得分')
            if self.options.show_correct_status:
                headers.append('是否正确')
            if self.options.include_analysis:
                headers.append('解析')
            if self.options.include_images:
                headers.append('图片')

            for col, header in enumerate(headers):
                worksheet.write(0, col, header, header_format)

            worksheet.freeze_panes(1, 0)

            for row, q in enumerate(self.questions, 1):
                col = 0

                if self.options.include_question_number:
                    worksheet.write(row, col, row, cell_format)
                    col += 1

                if self.options.include_homework_title:
                    worksheet.write(row, col, q.get('homework_title', ''), cell_format)
                    col += 1

                worksheet.write(row, col, self._get_question_content(q), cell_format)
                col += 1

                if self.options.include_question_type:
                    worksheet.write(row, col, self._get_question_type(q), cell_format)
                    col += 1

                options_text = ""
                raw_options = q.get('options', [])
                if raw_options:
                    opt_lines = []
                    for opt in raw_options:
                        if isinstance(opt, dict):
                            label = opt.get('label', '')
                            content = opt.get('content', '')
                            opt_images = opt.get('images', [])
                            if opt_images:
                                content = re.sub(r'\[图片选项[：:]\s*\d+张\]', '', content).strip()
                            if label:
                                opt_lines.append(f"{label}. {content}")
                            else:
                                opt_lines.append(str(content))
                        else:
                            opt_lines.append(str(opt))
                    options_text = "\n".join(opt_lines)
                worksheet.write(row, col, options_text, cell_format)
                col += 1

                if self.options.include_my_answer:
                    # 图片已在独立列展示，文本里只需去掉占位符，不再整段清空
                    my_answer = re.sub(r'\[图片[：:][^\]]*\]', '', self._get_my_answer(q) or '').strip()
                    worksheet.write(row, col, my_answer, cell_format)
                    col += 1

                if self.options.include_correct_answer:
                    correct_answer = re.sub(r'\[图片[：:][^\]]*\]', '', self._get_question_answer(q) or '').strip()
                    worksheet.write(row, col, correct_answer, cell_format)
                    col += 1

                if self.options.include_score:
                    worksheet.write(row, col, get_question_field(q, 'score', ''), cell_format)
                    col += 1

                if self.options.show_correct_status:
                    is_correct = self._is_correct(q)
                    status = '正确' if is_correct is True else ('错误' if is_correct is False else '')
                    worksheet.write(row, col, status, cell_format)
                    col += 1

                if self.options.include_analysis:
                    worksheet.write(row, col, self._get_analysis(q), cell_format)
                    col += 1

                if self.options.include_images:
                    self._insert_images_to_excel(
                        worksheet, row, col, self._collect_question_images(q))
                    col += 1

            col_widths = {
                '序号': 8,
                '作业': 20,
                '题目': 40,
                '类型': 12,
                '选项': 30,
                '我的答案': 15,
                '正确答案': 15,
                '得分': 10,
                '是否正确': 10,
                '解析': 30,
                '图片': 30
            }
            for col, header in enumerate(headers):
                worksheet.set_column(col, col, col_widths.get(header, 15))

            workbook.close()
            workbook = None
            app_logger.info(f"Excel导出成功: {output_path}")
            return True

        except Exception as e:
            app_logger.error(f"Excel导出失败: {e}")
            return False
        finally:
            if workbook is not None:
                try:
                    workbook.close()
                except Exception:
                    pass
    
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
        except ImportError:
            app_logger.error("Word导出需要安装python-docx库: pip install python-docx")
            return False
        
        try:
            doc = Document()
            stats = self.get_statistics()
            
            # 标题
            title = doc.add_heading(self.homework_title, 0)
            title.alignment = WD_ALIGN_PARAGRAPH.CENTER
            
            # 副标题信息（统计 + 时间）
            if self.options.include_statistics or self.options.include_export_time:
                info_para = doc.add_paragraph()
                info_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                
                info_parts = []
                if self.options.include_statistics:
                    info_parts.append(f"共 {stats['total_questions']} 题")
                    info_parts.append(f"正确 {stats['correct_count']}")
                    info_parts.append(f"错误 {stats['wrong_count']}")
                    info_parts.append(f"正确率 {stats['accuracy']}")
                if self.options.include_export_time:
                    info_parts.append(datetime.now().strftime('%Y-%m-%d %H:%M'))
                
                info_run = info_para.add_run("  |  ".join(info_parts))
                info_run.font.size = Pt(10)
                info_run.font.color.rgb = RGBColor(128, 128, 128)
            
            doc.add_paragraph()
            
            # 题目列表
            for i, q in enumerate(self.questions, 1):
                q_type = self._get_question_type(q)
                content = self._get_question_content(q)
                options = self._get_options(q)
                is_correct = self._is_correct(q)
                
                # 题目标题（题号 + 类型 + 状态 在同一行）
                q_para = doc.add_paragraph()
                
                # 题号
                num_run = q_para.add_run(f"{i}. ")
                num_run.bold = True
                num_run.font.size = Pt(11)
                
                # 题型
                if self.options.include_question_type:
                    type_run = q_para.add_run(f"[{q_type}] ")
                    type_run.font.size = Pt(10)
                    type_run.font.color.rgb = RGBColor(100, 100, 100)
                
                # 状态标记
                if self.options.show_correct_status and is_correct is not None:
                    if is_correct:
                        status_run = q_para.add_run(" ✓")
                        status_run.font.color.rgb = RGBColor(34, 139, 34)
                    else:
                        status_run = q_para.add_run(" ✗")
                        status_run.font.color.rgb = RGBColor(220, 20, 60)
                
                # 题目内容
                content_para = doc.add_paragraph()
                content_run = content_para.add_run(content)
                content_run.font.size = Pt(11)
                
                # 题目图片
                content_images = get_question_field(q, 'content_images', [])
                if content_images:
                    self._add_images_to_word(doc, content_images, 4.0)
                
                # 选项（包含图片）
                raw_options = q.get('options', [])
                for opt in raw_options:
                    opt_para = doc.add_paragraph()
                    opt_para.paragraph_format.left_indent = Inches(0.3)
                    
                    if isinstance(opt, dict):
                        label = opt.get('label', '')
                        content = opt.get('content', '')
                        opt_images = opt.get('images', [])
                        
                        # 如果有图片，清理占位符文本
                        if opt_images:
                            content = re.sub(r'\[图片选项[：:]\s*\d+张\]', '', content).strip()
                        
                        opt_run = opt_para.add_run(f"{label}. {content}")
                        opt_run.font.size = Pt(10)
                        
                        # 添加选项图片
                        if opt_images:
                            self._add_images_to_word(doc, opt_images, 3.0)
                    else:
                        opt_run = opt_para.add_run(str(opt))
                        opt_run.font.size = Pt(10)
                
                # 答案区域
                ans_para = doc.add_paragraph()
                ans_para.paragraph_format.space_before = Pt(6)
                
                if self.options.include_my_answer:
                    my_answer = self._get_my_answer(q)
                    my_answer_images = get_question_field(q, 'my_answer_images', [])
                    # 过滤掉图片占位符文本
                    if my_answer and '[图片' in my_answer:
                        my_answer = ''
                    if my_answer:
                        my_run = ans_para.add_run(f"我的答案: {my_answer}    ")
                        my_run.font.size = Pt(10)
                        my_run.font.color.rgb = RGBColor(0, 100, 180)
                    # 嵌入我的答案图片
                    if my_answer_images:
                        label_para = doc.add_paragraph()
                        label_run = label_para.add_run("我的答案图片:")
                        label_run.font.size = Pt(9)
                        label_run.font.color.rgb = RGBColor(0, 100, 180)
                        self._add_images_to_word(doc, my_answer_images, 3.5)
                
                if self.options.include_correct_answer:
                    correct_answer = self._get_question_answer(q)
                    correct_answer_images = get_question_field(q, 'correct_answer_images', [])
                    if correct_answer and '[图片' in correct_answer:
                        correct_answer = ''
                    if correct_answer:
                        correct_run = ans_para.add_run(f"正确答案: {correct_answer}")
                        correct_run.font.size = Pt(10)
                        correct_run.font.color.rgb = RGBColor(0, 128, 0)
                    # 嵌入正确答案图片
                    if correct_answer_images:
                        label_para = doc.add_paragraph()
                        label_run = label_para.add_run("正确答案图片:")
                        label_run.font.size = Pt(9)
                        label_run.font.color.rgb = RGBColor(0, 128, 0)
                        self._add_images_to_word(doc, correct_answer_images, 3.5)
                
                # 得分
                if self.options.include_score:
                    score = get_question_field(q, 'score', '')
                    if score:
                        score_run = ans_para.add_run(f"    得分: {score}")
                        score_run.font.size = Pt(10)
                        score_run.font.color.rgb = RGBColor(128, 128, 128)
                
                # 解析（单独一行）
                if self.options.include_analysis:
                    analysis = self._get_analysis(q)
                    if analysis:
                        analysis_para = doc.add_paragraph()
                        analysis_run = analysis_para.add_run(f"解析: {analysis}")
                        analysis_run.font.size = Pt(9)
                        analysis_run.font.color.rgb = RGBColor(150, 100, 50)
                        analysis_run.italic = True
                
                # 分割线
                if self.options.include_separator and i < len(self.questions):
                    separator_para = doc.add_paragraph()
                    separator_para.paragraph_format.space_before = Pt(10)
                    separator_para.paragraph_format.space_after = Pt(10)
                    separator_run = separator_para.add_run("─" * 60)
                    separator_run.font.size = Pt(8)
                    separator_run.font.color.rgb = RGBColor(200, 200, 200)
                else:
                    # 题目间距
                    doc.add_paragraph()
            
            doc.save(output_path)
            app_logger.info(f"Word导出成功: {output_path}")
            return True
            
        except Exception as e:
            app_logger.error(f"Word导出失败: {e}")
            return False
    
    # ==================== PDF 导出 ====================
    
    @staticmethod
    def _find_chinese_font() -> Optional[str]:
        """按平台查找可用的中文字体文件，找不到返回 None

        原实现硬编码 C:/Windows/Fonts/，在非 Windows 平台必然找不到字体，
        导致导出的 PDF 中文全是乱码（且只有一条 warning，用户不易察觉）。
        """
        import platform
        import glob

        system = platform.system()
        candidates: List[str] = []

        if system == 'Windows':
            windir = (os.environ.get('WINDIR')
                      or os.environ.get('SystemRoot')
                      or r'C:\Windows')
            candidates = [
                os.path.join(windir, 'Fonts', 'msyh.ttc'),     # 微软雅黑
                os.path.join(windir, 'Fonts', 'msyhbd.ttc'),
                os.path.join(windir, 'Fonts', 'simhei.ttf'),   # 黑体
                os.path.join(windir, 'Fonts', 'simsun.ttc'),   # 宋体
            ]
        elif system == 'Darwin':
            candidates = [
                '/System/Library/Fonts/PingFang.ttc',
                '/System/Library/Fonts/STHeiti Medium.ttc',
                '/System/Library/Fonts/STHeiti Light.ttc',
                '/Library/Fonts/Arial Unicode.ttf',
            ]
        else:  # Linux 及其他类 Unix
            candidates = (
                glob.glob('/usr/share/fonts/**/NotoSansCJK*.tt[cf]', recursive=True) +
                glob.glob('/usr/share/fonts/**/NotoSerifCJK*.tt[cf]', recursive=True) +
                glob.glob('/usr/share/fonts/**/wqy-*.tt[cf]', recursive=True) +
                glob.glob(os.path.expanduser('~/.fonts/**/*.tt[cf]'), recursive=True) +
                ['/usr/share/fonts/truetype/arphic/uming.ttc']
            )

        for path in candidates:
            if path and os.path.exists(path):
                return path
        return None

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
            # 注册中文字体：系统字体 → reportlab 内置 CID 字体 → 明确告警
            chinese_font_registered = False
            font_name = 'Helvetica'

            font_path = self._find_chinese_font()
            if font_path:
                try:
                    pdfmetrics.registerFont(TTFont('ChineseFont', font_path))
                    chinese_font_registered = True
                    font_name = 'ChineseFont'
                    app_logger.info(f"PDF 中文字体: {font_path}")
                except Exception as e:
                    app_logger.warning(f"注册中文字体失败 {font_path}: {e}")

            if not chinese_font_registered:
                # reportlab 自带 STSong-Light CID 字体，不依赖任何系统字体文件
                try:
                    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
                    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
                    chinese_font_registered = True
                    font_name = 'STSong-Light'
                    app_logger.info("PDF 中文字体回退: reportlab 内置 STSong-Light")
                except Exception as e:
                    app_logger.warning(f"内置 CID 字体不可用: {e}")

            if not chinese_font_registered:
                app_logger.error("未找到任何可用的中文字体，PDF 中的中文将显示为乱码")
            
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
                    fontName=font_name,
                    fontSize=18,
                    alignment=1
                )
                normal_style = ParagraphStyle(
                    'ChineseNormal',
                    parent=styles['Normal'],
                    fontName=font_name,
                    fontSize=11,
                    leading=16
                )
                heading_style = ParagraphStyle(
                    'ChineseHeading',
                    parent=styles['Heading2'],
                    fontName=font_name,
                    fontSize=14
                )
            else:
                title_style = styles['Title']
                normal_style = styles['Normal']
                heading_style = styles['Heading2']
            
            stats = self.get_statistics()
            
            # 标题
            story.append(Paragraph(_escape_xml(self.homework_title), title_style))
            story.append(Spacer(1, 12))
            
            # 副标题信息（统计 + 时间）
            info_parts = []
            if self.options.include_statistics:
                info_parts.append(f"共 {stats['total_questions']} 题")
                info_parts.append(f"正确 {stats['correct_count']}")
                info_parts.append(f"错误 {stats['wrong_count']}")
                info_parts.append(f"正确率 {stats['accuracy']}")
            if self.options.include_export_time:
                info_parts.append(datetime.now().strftime('%Y-%m-%d %H:%M'))
            
            if info_parts:
                info_style = ParagraphStyle(
                    'InfoStyle',
                    parent=normal_style,
                    fontSize=10,
                    textColor=colors.grey,
                    alignment=1
                )
                story.append(Paragraph("  |  ".join(info_parts), info_style))
                story.append(Spacer(1, 25))
            
            # 题目列表
            for i, q in enumerate(self.questions, 1):
                q_type = self._get_question_type(q)
                content = self._get_question_content(q)
                options = self._get_options(q)
                is_correct = self._is_correct(q)
                
                # 题目标题（题号 + 类型 + 状态）
                status_mark = ""
                if self.options.show_correct_status and is_correct is not None:
                    status_mark = " <font color='green'>[正确]</font>" if is_correct else " <font color='red'>[错误]</font>"
                
                q_header = f"<b>{i}.</b> "
                if self.options.include_question_type:
                    q_header += f"<font color='grey'>[{q_type}]</font> "
                q_header += status_mark
                
                story.append(Paragraph(q_header, normal_style))
                
                # 题目内容
                story.append(Paragraph(_escape_xml(content), normal_style))
                
                # 题目图片
                content_images = get_question_field(q, 'content_images', [])
                if content_images:
                    self._add_images_to_pdf(story, content_images)
                
                story.append(Spacer(1, 4))
                
                # 选项（包含图片）
                raw_options = q.get('options', [])
                if raw_options:
                    for opt in raw_options:
                        if isinstance(opt, dict):
                            label = opt.get('label', '')
                            content = opt.get('content', '')
                            opt_images = opt.get('images', [])
                            
                            # 如果有图片，清理占位符文本
                            if opt_images:
                                content = re.sub(r'\[图片选项[：:]\s*\d+张\]', '', content).strip()
                            
                            story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;{_escape_xml(label)}. {_escape_xml(content)}", normal_style))
                            
                            # 添加选项图片
                            if opt_images:
                                self._add_images_to_pdf(story, opt_images, max_width=350)
                        else:
                            story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;{_escape_xml(str(opt))}", normal_style))
                    story.append(Spacer(1, 4))
                
                # 答案（合并到一行）
                ans_parts = []
                if self.options.include_my_answer:
                    my_answer = self._get_my_answer(q)
                    my_answer_images = get_question_field(q, 'my_answer_images', [])
                    if my_answer and '[图片' in my_answer:
                        my_answer = ''
                    if my_answer:
                        ans_parts.append(f"<font color='#0066CC'>我的答案: {_escape_xml(my_answer)}</font>")
                
                if self.options.include_correct_answer:
                    correct_answer = self._get_question_answer(q)
                    correct_answer_images = get_question_field(q, 'correct_answer_images', [])
                    if correct_answer and '[图片' in correct_answer:
                        correct_answer = ''
                    if correct_answer:
                        ans_parts.append(f"<font color='#008800'>正确答案: {_escape_xml(correct_answer)}</font>")
                
                if self.options.include_score:
                    score_val = get_question_field(q, 'score', '')
                    if score_val:
                        ans_parts.append(f"<font color='grey'>得分: {_escape_xml(str(score_val))}</font>")
                
                if ans_parts:
                    story.append(Paragraph("&nbsp;&nbsp;".join(ans_parts), normal_style))
                
                # 嵌入答案图片到PDF
                if self.options.include_my_answer:
                    my_answer_images = get_question_field(q, 'my_answer_images', [])
                    if my_answer_images:
                        story.append(Paragraph("<font color='#0066CC'>我的答案图片:</font>", normal_style))
                        self._add_images_to_pdf(story, my_answer_images)
                
                if self.options.include_correct_answer:
                    correct_answer_images = get_question_field(q, 'correct_answer_images', [])
                    if correct_answer_images:
                        story.append(Paragraph("<font color='#008800'>正确答案图片:</font>", normal_style))
                        self._add_images_to_pdf(story, correct_answer_images)
                
                # 解析
                if self.options.include_analysis:
                    analysis = self._get_analysis(q)
                    if analysis:
                        story.append(Paragraph(f"<i><font color='#996633'>解析: {_escape_xml(analysis)}</font></i>", normal_style))
                
                # 分割线或间距
                if self.options.include_separator and i < len(self.questions):
                    from reportlab.platypus import HRFlowable
                    story.append(Spacer(1, 10))
                    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
                    story.append(Spacer(1, 10))
                else:
                    story.append(Spacer(1, 18))
            
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
        
        # Excel
        xlsx_path = os.path.join(output_dir, f"{base_name}.xlsx")
        results['excel'] = self.export_excel(xlsx_path)

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
        format: 格式 ('html', 'json', 'md', 'markdown', 'word', 'docx', 'excel', 'xlsx', 'pdf')
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
    elif format in ('excel', 'xlsx'):
        return exporter.export_excel(output_path)
    elif format == 'pdf':
        return exporter.export_pdf(output_path)
    else:
        app_logger.error(f"不支持的格式: {format}")
        return False
