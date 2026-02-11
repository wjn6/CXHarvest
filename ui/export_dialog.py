#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导出对话框 - Fluent Design 风格
提供多格式导出选项和自定义配置界面
"""

import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QFrame,
    QFileDialog, QGridLayout
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor

from qfluentwidgets import (
    CardWidget, BodyLabel, TitleLabel, CaptionLabel, StrongBodyLabel,
    PrimaryPushButton, PushButton, TransparentPushButton, TransparentToolButton,
    CheckBox, ProgressRing, InfoBar, InfoBarPosition, 
    SmoothScrollArea, LineEdit, isDarkTheme
)
from qfluentwidgets import FluentIcon as FIF

from core.enterprise_logger import app_logger
from core.question_exporter import QuestionExporter, ExportOptions
from core.export_history import get_export_history_manager


class ExportWorker(QThread):
    """导出工作线程"""
    progress = Signal(str, int)  # 消息, 百分比
    finished = Signal(dict)       # 结果
    error = Signal(str)           # 错误消息
    
    def __init__(self, exporter: QuestionExporter, output_dir: str, 
                 formats: List[str], base_name: str):
        super().__init__()
        self.exporter = exporter
        self.output_dir = output_dir
        self.formats = formats
        self.base_name = base_name
    
    def run(self):
        try:
            results = {}
            total = len(self.formats)
            
            for i, fmt in enumerate(self.formats):
                self.progress.emit(f"正在导出 {fmt.upper()}...", int((i / total) * 100))
                
                if fmt == 'html':
                    path = os.path.join(self.output_dir, f"{self.base_name}.html")
                    results['html'] = self.exporter.export_html(path)
                elif fmt == 'json':
                    path = os.path.join(self.output_dir, f"{self.base_name}.json")
                    results['json'] = self.exporter.export_json(path)
                elif fmt == 'markdown':
                    path = os.path.join(self.output_dir, f"{self.base_name}.md")
                    results['markdown'] = self.exporter.export_markdown(path)
                elif fmt == 'word':
                    path = os.path.join(self.output_dir, f"{self.base_name}.docx")
                    results['word'] = self.exporter.export_word(path)
                elif fmt == 'pdf':
                    path = os.path.join(self.output_dir, f"{self.base_name}.pdf")
                    results['pdf'] = self.exporter.export_pdf(path)
                elif fmt == 'excel':
                    path = os.path.join(self.output_dir, f"{self.base_name}.xlsx")
                    results['excel'] = self.exporter.export_excel(path)
            
            self.progress.emit("导出完成", 100)
            self.finished.emit(results)
            
        except Exception as e:
            self.error.emit(str(e))


class ExportDialog(QDialog):
    """导出对话框 - Fluent Design 风格"""
    
    def __init__(self, questions: List[Dict], homework_title: str = "作业题目", 
                 course_name: str = "", parent=None):
        super().__init__(parent)
        self.questions = questions
        self.homework_title = homework_title
        self.course_name = course_name
        self.export_worker = None
        self._exported_files = []  # 保存导出的文件路径
        
        self.setWindowTitle("导出题目")
        self.setMinimumSize(700, 680)
        self.setModal(True)
        
        # 设置无边框窗口
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        
        # 用于窗口拖动
        self._drag_pos = None
        
        # 应用 Fluent Design 样式
        self._apply_fluent_style()
        
        self._init_ui()
        self._load_default_path()
    
    def _apply_fluent_style(self):
        """应用 Fluent Design 样式 - 跟随系统主题"""
        if isDarkTheme():
            self.setStyleSheet("""
                QDialog { background-color: #2d2d2d; color: #ffffff; }
                CardWidget { background-color: #2d2d2d; border: none; border-bottom: 1px solid #404040; border-radius: 0px; }
                SmoothScrollArea { background-color: #2d2d2d; border: none; }
                SmoothScrollArea > QWidget > QWidget { background-color: #2d2d2d; }
                QScrollBar:vertical { background-color: #2d2d2d; }
                QLabel { color: #ffffff; }
            """)
        else:
            self.setStyleSheet("""
                QDialog { background-color: #ffffff; color: #000000; }
                CardWidget { background-color: #ffffff; border: none; border-bottom: 1px solid #e8e8e8; border-radius: 0px; }
                SmoothScrollArea { background-color: #ffffff; border: none; }
                SmoothScrollArea > QWidget > QWidget { background-color: #ffffff; }
                QScrollBar:vertical { background-color: #ffffff; }
                QLabel { color: #000000; }
            """)
    
    def _create_title_bar(self, parent_layout):
        """创建自定义标题栏"""
        title_bar = QFrame(self)
        title_bar.setFixedHeight(48)
        title_bar.setObjectName("titleBar")
        
        # 标题栏样式
        if isDarkTheme():
            title_bar.setStyleSheet("""
                #titleBar {
                    background-color: #1f1f1f;
                    border-bottom: 1px solid #333333;
                }
            """)
        else:
            title_bar.setStyleSheet("""
                #titleBar {
                    background-color: #f3f3f3;
                    border-bottom: 1px solid #e0e0e0;
                }
            """)
        
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(16, 0, 8, 0)
        title_layout.setSpacing(12)
        
        # 图标和标题
        title_label = StrongBodyLabel("📤 导出题目", title_bar)
        title_layout.addWidget(title_label)
        
        title_layout.addStretch()
        
        # 题目数量统计
        stats_label = CaptionLabel(f"共 {len(self.questions)} 道题目", title_bar)
        title_layout.addWidget(stats_label)
        
        # 关闭按钮
        close_btn = TransparentToolButton(FIF.CLOSE, title_bar)
        close_btn.setFixedSize(32, 32)
        close_btn_font = close_btn.font()
        if close_btn_font.pointSize() <= 0:
            base_point_size = self.font().pointSize()
            close_btn_font.setPointSize(base_point_size if base_point_size > 0 else 9)
            close_btn.setFont(close_btn_font)
        close_btn.clicked.connect(self.reject)
        title_layout.addWidget(close_btn)
        
        parent_layout.addWidget(title_bar)
    
    def mousePressEvent(self, event):
        """鼠标按下事件 - 用于拖动窗口"""
        if event.button() == Qt.LeftButton and event.position().y() < 48:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """鼠标移动事件 - 用于拖动窗口"""
        if self._drag_pos is not None and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """鼠标释放事件"""
        self._drag_pos = None
        super().mouseReleaseEvent(event)
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 自定义标题栏
        self._create_title_bar(layout)
        
        # 主内容区域（带边距）
        content_widget = QWidget(self)
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(24, 16, 24, 24)
        content_layout.setSpacing(16)
        
        # 滚动区域
        scroll = SmoothScrollArea(self)
        scroll.setWidgetResizable(True)
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 12, 0)
        scroll_layout.setSpacing(0)  # 无间距，卡片紧密排列
        
        # 导出格式选择卡片
        self._create_format_card(scroll_layout)
        
        # 内容选项卡片
        self._create_content_options_card(scroll_layout)
        
        # 格式选项卡片
        self._create_format_options_card(scroll_layout)
        
        # 输出路径卡片
        self._create_output_card(scroll_layout)
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        content_layout.addWidget(scroll, 1)
        
        # 进度条
        self.progress_container = QFrame(self)
        progress_layout = QHBoxLayout(self.progress_container)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        
        self.progress_ring = ProgressRing(self.progress_container)
        self.progress_ring.setFixedSize(24, 24)
        progress_layout.addWidget(self.progress_ring)
        
        self.progress_label = CaptionLabel("准备导出...", self.progress_container)
        progress_layout.addWidget(self.progress_label)
        progress_layout.addStretch()
        
        self.progress_container.hide()
        content_layout.addWidget(self.progress_container)
        
        # 底部按钮
        button_layout = QHBoxLayout()
        
        self.cancel_btn = PushButton("取消", self)
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        button_layout.addStretch()
        
        self.export_btn = PrimaryPushButton("开始导出", self)
        self.export_btn.setMinimumWidth(120)
        self.export_btn.clicked.connect(self._start_export)
        button_layout.addWidget(self.export_btn)
        
        content_layout.addLayout(button_layout)
        layout.addWidget(content_widget)
    
    def _create_format_card(self, parent_layout):
        """创建格式选择卡片"""
        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)
        
        # 标题
        title = StrongBodyLabel("选择导出格式", card)
        card_layout.addWidget(title)
        
        # 格式复选框
        formats_layout = QHBoxLayout()
        formats_layout.setSpacing(20)
        
        self.format_checks = {}
        
        formats = [
            ('html', 'HTML', '精美网页格式，支持打印'),
            ('pdf', 'PDF', '通用便携格式'),
            ('word', 'Word', '正式文档格式 (.docx)'),
            ('excel', 'Excel', '表格格式 (.xlsx)'),
            ('json', 'JSON', '结构化数据，便于处理'),
            ('markdown', 'Markdown', '纯文本标记格式'),
        ]
        
        for fmt_id, fmt_name, fmt_desc in formats:
            fmt_widget = QWidget(card)
            fmt_layout = QVBoxLayout(fmt_widget)
            fmt_layout.setContentsMargins(0, 0, 0, 0)
            fmt_layout.setSpacing(2)
            
            check = CheckBox(fmt_name, fmt_widget)
            check.setChecked(fmt_id in ['html', 'pdf', 'word'])  # 默认选中HTML、PDF、Word
            self.format_checks[fmt_id] = check
            fmt_layout.addWidget(check)
            
            hint = CaptionLabel(fmt_desc, fmt_widget)
            fmt_layout.addWidget(hint)
            
            formats_layout.addWidget(fmt_widget)
        
        formats_layout.addStretch()
        card_layout.addLayout(formats_layout)
        
        # 全选/取消全选
        select_layout = QHBoxLayout()
        select_all_btn = TransparentPushButton("全选", card)
        select_all_btn.clicked.connect(lambda: self._set_all_formats(True))
        select_layout.addWidget(select_all_btn)
        
        deselect_all_btn = TransparentPushButton("取消全选", card)
        deselect_all_btn.clicked.connect(lambda: self._set_all_formats(False))
        select_layout.addWidget(deselect_all_btn)
        
        select_layout.addStretch()
        card_layout.addLayout(select_layout)
        
        parent_layout.addWidget(card)
    
    def _create_content_options_card(self, parent_layout):
        """创建内容选项卡片"""
        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)
        
        # 标题
        title = StrongBodyLabel("内容选项", card)
        card_layout.addWidget(title)
        
        # 使用网格布局，3列2行
        grid = QGridLayout()
        grid.setSpacing(16)
        
        self.check_my_answer = CheckBox("包含我的答案", card)
        self.check_my_answer.setChecked(True)
        grid.addWidget(self.check_my_answer, 0, 0)
        
        self.check_analysis = CheckBox("包含答案解析", card)
        self.check_analysis.setChecked(True)
        grid.addWidget(self.check_analysis, 0, 1)
        
        self.check_correct_answer = CheckBox("包含正确答案", card)
        self.check_correct_answer.setChecked(True)
        grid.addWidget(self.check_correct_answer, 1, 0)
        
        self.check_statistics = CheckBox("包含统计信息", card)
        self.check_statistics.setChecked(True)
        grid.addWidget(self.check_statistics, 1, 1)
        
        self.check_score = CheckBox("包含得分信息", card)
        self.check_score.setChecked(True)
        grid.addWidget(self.check_score, 2, 0)
        
        self.check_images = CheckBox("包含图片", card)
        self.check_images.setChecked(True)
        grid.addWidget(self.check_images, 2, 1)
        
        card_layout.addLayout(grid)
        parent_layout.addWidget(card)
    
    def _create_format_options_card(self, parent_layout):
        """创建格式选项卡片"""
        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)
        
        # 标题
        title = StrongBodyLabel("格式选项", card)
        card_layout.addWidget(title)
        
        # 使用网格布局，2行2列
        grid = QGridLayout()
        grid.setSpacing(16)
        
        self.check_separator = CheckBox("题目间添加分割线", card)
        self.check_separator.setChecked(False)
        grid.addWidget(self.check_separator, 0, 0)
        
        self.check_question_number = CheckBox("显示题目编号", card)
        self.check_question_number.setChecked(True)
        grid.addWidget(self.check_question_number, 0, 1)
        
        self.check_question_type = CheckBox("显示题目类型", card)
        self.check_question_type.setChecked(True)
        grid.addWidget(self.check_question_type, 1, 0)
        
        self.check_correct_status = CheckBox("显示正确/错误状态", card)
        self.check_correct_status.setChecked(True)
        grid.addWidget(self.check_correct_status, 1, 1)
        
        card_layout.addLayout(grid)
        parent_layout.addWidget(card)
    
    def _create_output_card(self, parent_layout):
        """创建输出路径卡片"""
        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)
        
        # 标题
        title = StrongBodyLabel("输出设置", card)
        card_layout.addWidget(title)
        
        # 文件名
        name_layout = QHBoxLayout()
        name_label = BodyLabel("文件名:", card)
        name_layout.addWidget(name_label)
        
        self.filename_edit = LineEdit(card)
        self.filename_edit.setText(self._sanitize_filename(self.homework_title))
        self.filename_edit.setPlaceholderText("输入文件名")
        name_layout.addWidget(self.filename_edit, 1)
        
        card_layout.addLayout(name_layout)
        
        # 输出目录
        path_layout = QHBoxLayout()
        path_label = BodyLabel("保存到:", card)
        path_layout.addWidget(path_label)
        
        self.path_edit = LineEdit(card)
        self.path_edit.setPlaceholderText("选择保存目录")
        self.path_edit.setReadOnly(True)
        path_layout.addWidget(self.path_edit, 1)
        
        browse_btn = PushButton("浏览", card)
        browse_btn.clicked.connect(self._browse_output_dir)
        path_layout.addWidget(browse_btn)
        
        card_layout.addLayout(path_layout)
        
        parent_layout.addWidget(card)
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名"""
        import re
        illegal_chars = r'[\\/:*?"<>|]'
        return re.sub(illegal_chars, '_', filename)
    
    def _set_all_formats(self, checked: bool):
        """全选/取消全选格式"""
        for check in self.format_checks.values():
            check.setChecked(checked)
    
    def _load_default_path(self):
        """加载默认路径"""
        default_dir = os.path.join(os.path.expanduser("~"), "Desktop", "题目导出")
        self.path_edit.setText(default_dir)
    
    def _browse_output_dir(self):
        """浏览输出目录"""
        current_path = self.path_edit.text() or os.path.expanduser("~")
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择保存目录", current_path
        )
        if dir_path:
            self.path_edit.setText(dir_path)
    
    def _get_selected_formats(self) -> List[str]:
        """获取选中的格式"""
        return [fmt for fmt, check in self.format_checks.items() if check.isChecked()]
    
    def _build_export_options(self) -> ExportOptions:
        """构建导出选项"""
        options = ExportOptions()
        
        # 内容选项
        options.include_my_answer = self.check_my_answer.isChecked()
        options.include_correct_answer = self.check_correct_answer.isChecked()
        options.include_score = self.check_score.isChecked()
        options.include_analysis = self.check_analysis.isChecked()
        options.include_statistics = self.check_statistics.isChecked()
        options.include_images = self.check_images.isChecked()
        
        # 格式选项
        options.include_separator = self.check_separator.isChecked()
        options.include_question_number = self.check_question_number.isChecked()
        options.include_question_type = self.check_question_type.isChecked()
        options.show_correct_status = self.check_correct_status.isChecked()
        
        return options
    
    def _start_export(self):
        """开始导出"""
        # 验证
        formats = self._get_selected_formats()
        if not formats:
            InfoBar.warning(
                title="请选择格式",
                content="请至少选择一种导出格式",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            return
        
        output_dir = self.path_edit.text()
        if not output_dir:
            InfoBar.warning(
                title="请选择目录",
                content="请选择保存目录",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            return
        
        base_name = self.filename_edit.text().strip()
        if not base_name:
            base_name = self._sanitize_filename(self.homework_title)
        
        # 创建目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 构建导出器
        exporter = QuestionExporter(self.questions, self.homework_title)
        exporter.set_options(self._build_export_options())
        
        # 禁用界面
        self.export_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.progress_container.show()
        
        # 启动工作线程
        self.export_worker = ExportWorker(exporter, output_dir, formats, base_name)
        self.export_worker.progress.connect(self._on_progress)
        self.export_worker.finished.connect(self._on_export_finished)
        self.export_worker.error.connect(self._on_export_error)
        self.export_worker.start()
    
    def _on_progress(self, message: str, percentage: int):
        """进度更新"""
        self.progress_label.setText(message)
    
    def _on_export_finished(self, results: dict):
        """导出完成"""
        self.progress_container.hide()
        self.export_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        
        # 统计结果
        success_count = sum(1 for v in results.values() if v)
        total_count = len(results)
        
        if success_count > 0:
            # 保存导出历史记录
            self._save_export_history(results)
        
        if success_count == total_count:
            InfoBar.success(
                title="导出成功",
                content=f"已成功导出 {success_count} 个文件到 {self.path_edit.text()}",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self
            )
            
            # 打开输出目录
            output_dir = self.path_edit.text()
            if os.path.exists(output_dir):
                os.startfile(output_dir)
            
            self.accept()
        else:
            failed = [fmt for fmt, success in results.items() if not success]
            InfoBar.warning(
                title="部分导出失败",
                content=f"成功: {success_count}/{total_count}，失败: {', '.join(failed)}",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self
            )
    
    def _on_export_error(self, error_msg: str):
        """导出错误"""
        self.progress_container.hide()
        self.export_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        
        InfoBar.error(
            title="导出失败",
            content=error_msg,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self
        )
    
    def _save_export_history(self, results: dict):
        """保存导出历史记录"""
        try:
            output_dir = self.path_edit.text()
            base_name = self.filename_edit.text().strip() or self._sanitize_filename(self.homework_title)
            
            # 获取成功导出的格式
            success_formats = [fmt for fmt, success in results.items() if success]
            
            for fmt in success_formats:
                # 构建文件路径
                ext_map = {'html': '.html', 'json': '.json', 'markdown': '.md', 'word': '.docx', 'pdf': '.pdf', 'excel': '.xlsx'}
                ext = ext_map.get(fmt, f'.{fmt}')
                file_path = os.path.join(output_dir, f"{base_name}{ext}")
                
                # 获取文件大小
                file_size = 0
                if os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                
                # 保存记录
                history_manager = get_export_history_manager()
                history_manager.add_record(
                    course_name=self.course_name or "未知课程",
                    homework_titles=[self.homework_title],
                    question_count=len(self.questions),
                    export_format=fmt.upper(),
                    file_path=file_path,
                    file_size=file_size
                )
        except Exception as e:
            app_logger.warning(f"保存导出历史失败: {e}")


def show_export_dialog(questions: List[Dict], homework_title: str = "作业题目", 
                       course_name: str = "", parent=None) -> bool:
    """
    显示导出对话框
    
    Args:
        questions: 题目列表
        homework_title: 作业标题
        course_name: 课程名称
        parent: 父窗口
        
    Returns:
        是否完成导出
    """
    dialog = ExportDialog(questions, homework_title, course_name, parent)
    return dialog.exec() == QDialog.Accepted


# 兼容性别名
ExportDialogFluent = ExportDialog

