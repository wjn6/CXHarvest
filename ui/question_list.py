#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
题目列表页面 - Fluent Design 重构版
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QFrame, QSizePolicy, QSpacerItem, QLabel
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont, QPixmap, QCursor

from qfluentwidgets import (
    CardWidget, SimpleCardWidget,
    BodyLabel, SubtitleLabel, TitleLabel, CaptionLabel, StrongBodyLabel,
    PrimaryPushButton, PushButton, TransparentPushButton, ToolButton,
    SearchLineEdit, ComboBox, CheckBox, IndeterminateProgressBar,
    InfoBar, InfoBarPosition, SmoothScrollArea
)
from qfluentwidgets import FluentIcon as FIF

from core.enterprise_logger import app_logger
from core.homework_question_parser import HomeworkQuestionParser
from ui.export_dialog import show_export_dialog
from ui.image_preview import ImagePreviewDialog, ClickableImageLabel


class QuestionParseWorker(QThread):
    """题目解析线程"""
    questions_loaded = Signal(list)
    progress_update = Signal(str, int)
    error_occurred = Signal(str)
    
    def __init__(self, homework_info: dict, login_manager):
        super().__init__()
        self.homework_info = homework_info
        self.login_manager = login_manager
    
    def run(self):
        try:
            parser = HomeworkQuestionParser(self.login_manager)
            # 从 homework_info 中提取 url 和 title
            homework_url = self.homework_info.get('url', '')
            homework_title = self.homework_info.get('title', '未知作业')
            questions = parser.parse_homework_questions(homework_url, homework_title)
            self.questions_loaded.emit(questions)
        except Exception as e:
            self.error_occurred.emit(str(e))


class QuestionCard(CardWidget):
    """题目卡片组件"""
    selection_changed = Signal(bool)
    
    def __init__(self, question_data: dict, index: int, parent=None):
        super().__init__(parent)
        self.question_data = question_data
        self.index = index
        self.is_selected = False
        
        self._init_ui()
    
    def _init_ui(self):
        self.setMinimumWidth(600)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        
        # 顶部：序号 + 类型 + 得分 + 选择框
        top_layout = QHBoxLayout()
        
        # 序号和类型组合
        q_type = self.question_data.get('type', '未知')
        self.index_label = CaptionLabel(f"第 {self.index + 1} 题 · {q_type}", self)
        self.index_label.setStyleSheet("color: #666666;")
        top_layout.addWidget(self.index_label)
        
        # 得分显示
        score = self.question_data.get('score', '') or self.question_data.get('得分', '')
        total_score = self.question_data.get('totalScore', '') or self.question_data.get('满分', '')
        if score or total_score:
            score_text = f"{score}" if score else ""
            if total_score:
                score_text = f"{score}/{total_score}分" if score else f"满分{total_score}分"
            elif score:
                score_text = f"{score}分"
            if score_text:
                score_label = CaptionLabel(score_text, self)
                score_label.setStyleSheet("color: #e67e22; font-weight: 500;")
                top_layout.addWidget(score_label)
        
        # 正确/错误标记 - 仅对客观题显示
        is_correct = self.question_data.get('isCorrect', None)
        # 客观题类型
        objective_types = ['单选题', '多选题', '判断题', '选择题']
        is_objective = any(ot in q_type for ot in objective_types)
        
        if is_objective and is_correct is True:
            status_label = CaptionLabel("✓ 正确", self)
            status_label.setStyleSheet("color: #27ae60; font-weight: 500;")
            top_layout.addWidget(status_label)
        elif is_objective and is_correct is False:
            status_label = CaptionLabel("✗ 错误", self)
            status_label.setStyleSheet("color: #e74c3c; font-weight: 500;")
            top_layout.addWidget(status_label)
        
        top_layout.addStretch()
        
        # 选择框
        self.checkbox = CheckBox(self)
        self.checkbox.stateChanged.connect(self._on_checkbox_changed)
        top_layout.addWidget(self.checkbox)
        
        layout.addLayout(top_layout)
        
        # 题目内容（保留换行）
        content = self.question_data.get('content', '')
        self.content_label = BodyLabel(self)
        self.content_label.setWordWrap(True)
        self.content_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # 将换行符转换为HTML换行以正确显示
        if '\n' in content:
            html_content = content.replace('\n', '<br>')
            self.content_label.setText(html_content)
        else:
            self.content_label.setText(content)
        layout.addWidget(self.content_label)
        
        # 题目中的图片
        title_images = self.question_data.get('title_images', []) or self.question_data.get('contentImages', [])
        if title_images:
            images_layout = QHBoxLayout()
            images_layout.setSpacing(8)
            for img_info in title_images[:5]:  # 最多显示5张
                img_widget = self._create_image_widget(img_info)
                if img_widget:
                    images_layout.addWidget(img_widget)
            images_layout.addStretch()
            layout.addLayout(images_layout)
        
        # 选项（如果有）- 主观题不显示选项
        options = self.question_data.get('options', [])
        # 主观题类型列表（不显示选项）
        subjective_types = ['简答题', '填空题', '论述题', '问答题', '解答题', '计算题', '分析题', '综合题']
        is_subjective = any(st in q_type for st in subjective_types)
        
        if options and not is_subjective:
            options_layout = QVBoxLayout()
            options_layout.setSpacing(4)
            for opt in options:
                # 兼容处理：如果是字典则提取内容，如果是字符串直接使用
                if isinstance(opt, dict):
                    text = f"{opt.get('label', '')}. {opt.get('content', '')}"
                    opt_images = opt.get('images', [])
                else:
                    text = str(opt)
                    opt_images = []
                
                opt_label = BodyLabel(text, self)
                opt_label.setWordWrap(True)
                opt_label.setStyleSheet("color: #555555; padding-left: 16px;")
                options_layout.addWidget(opt_label)
                
                # 选项中的图片
                if opt_images:
                    opt_img_layout = QHBoxLayout()
                    opt_img_layout.setContentsMargins(16, 0, 0, 0)
                    for img_info in opt_images[:3]:  # 每个选项最多3张图
                        img_widget = self._create_image_widget(img_info, max_size=100)
                        if img_widget:
                            opt_img_layout.addWidget(img_widget)
                    opt_img_layout.addStretch()
                    options_layout.addLayout(opt_img_layout)
            layout.addLayout(options_layout)
        
        # 我的答案
        my_answer = self.question_data.get('myAnswer', '') or self.question_data.get('my_answer', '')
        my_answer_images = self.question_data.get('myAnswerImages', []) or self.question_data.get('my_answer_images', [])
        
        # 清理答案文本中的图片占位符
        clean_my_answer = my_answer
        if clean_my_answer:
            import re
            clean_my_answer = re.sub(r'\[图片[^\]]*\]\s*', '', clean_my_answer).strip()
        
        my_answer_container = QVBoxLayout()
        my_answer_header = QHBoxLayout()
        my_answer_title = CaptionLabel("我的答案:", self)
        my_answer_title.setStyleSheet("color: #2980b9;")
        my_answer_header.addWidget(my_answer_title)
        
        # 有文本答案时显示文本，否则根据是否有图片决定显示内容
        if clean_my_answer:
            display_answer = clean_my_answer[:200] + '...' if len(clean_my_answer) > 200 else clean_my_answer
            my_answer_text = BodyLabel(display_answer, self)
            my_answer_text.setWordWrap(True)
            my_answer_text.setStyleSheet("color: #333;")
            my_answer_header.addWidget(my_answer_text, 1)
        elif my_answer_images:
            # 只有图片，不显示文本
            my_answer_header.addStretch(1)
        else:
            my_answer_text = BodyLabel("(未作答)", self)
            my_answer_text.setStyleSheet("color: #aaa;")
            my_answer_header.addWidget(my_answer_text, 1)
        
        my_answer_container.addLayout(my_answer_header)
        
        # 我的答案中的图片
        if my_answer_images:
            my_ans_img_layout = QHBoxLayout()
            my_ans_img_layout.setContentsMargins(80, 4, 0, 0)
            for img_info in my_answer_images[:5]:
                img_widget = self._create_image_widget(img_info, max_size=200)
                if img_widget:
                    my_ans_img_layout.addWidget(img_widget)
            my_ans_img_layout.addStretch()
            my_answer_container.addLayout(my_ans_img_layout)
        
        layout.addLayout(my_answer_container)
        
        # 正确答案
        answer = self.question_data.get('answer', '') or self.question_data.get('correct_answer', '')
        answer_images = self.question_data.get('answerImages', []) or self.question_data.get('correct_answer_images', [])
        
        answer_container = QVBoxLayout()
        answer_header = QHBoxLayout()
        answer_title = CaptionLabel("正确答案:", self)
        answer_title.setStyleSheet("color: #27ae60;")
        answer_header.addWidget(answer_title)
        
        if answer:
            display_correct = answer[:200] + '...' if len(answer) > 200 else answer
            answer_text = BodyLabel(display_correct, self)
            answer_text.setStyleSheet("color: #333;")
        else:
            answer_text = BodyLabel("(未设置)", self)
            answer_text.setStyleSheet("color: #aaa;")
        answer_text.setWordWrap(True)
        answer_header.addWidget(answer_text, 1)
        answer_container.addLayout(answer_header)
        
        # 正确答案中的图片
        if answer_images:
            ans_img_layout = QHBoxLayout()
            ans_img_layout.setContentsMargins(80, 4, 0, 0)
            for img_info in answer_images[:5]:
                img_widget = self._create_image_widget(img_info, max_size=200)
                if img_widget:
                    ans_img_layout.addWidget(img_widget)
            ans_img_layout.addStretch()
            answer_container.addLayout(ans_img_layout)
        
        layout.addLayout(answer_container)
        
        # 解析（如果有）
        analysis = self.question_data.get('analysis', '') or self.question_data.get('explanation', '')
        if analysis:
            analysis_layout = QVBoxLayout()
            analysis_title = CaptionLabel("解析:", self)
            analysis_title.setStyleSheet("color: #888888;")
            display_analysis = analysis[:300] + '...' if len(analysis) > 300 else analysis
            analysis_text = CaptionLabel(display_analysis, self)
            analysis_text.setWordWrap(True)
            analysis_text.setStyleSheet("color: #888888;")
            analysis_layout.addWidget(analysis_title)
            analysis_layout.addWidget(analysis_text)
            layout.addLayout(analysis_layout)
    
    def _on_checkbox_changed(self, state):
        """选择框状态改变"""
        self.is_selected = (state == Qt.Checked)
        self.selection_changed.emit(self.is_selected)
    
    def _create_image_widget(self, img_info, max_size=150):
        """创建可点击放大的图片控件"""
        try:
            import base64
            
            if not img_info:
                return None
            
            # 获取图片数据
            data = img_info.get('data', '') if isinstance(img_info, dict) else str(img_info)
            
            if not data:
                # 如果没有base64数据，尝试使用原始URL
                src = img_info.get('src', '') if isinstance(img_info, dict) else ''
                if src:
                    # 创建一个占位符显示URL
                    placeholder = CaptionLabel("[图片]", self)
                    placeholder.setStyleSheet("color: #3498db; text-decoration: underline;")
                    placeholder.setToolTip(src)
                    return placeholder
                return None
            
            # 解析Base64数据
            if data.startswith('data:image'):
                # 格式: data:image/png;base64,xxxxx
                try:
                    header, encoded = data.split(',', 1)
                    image_data = base64.b64decode(encoded)
                except Exception:
                    return None
            else:
                return None
            
            # 创建原始QPixmap（用于放大查看）
            original_pixmap = QPixmap()
            if not original_pixmap.loadFromData(image_data):
                return None
            
            # 缩放图片用于缩略图显示
            thumbnail_pixmap = original_pixmap
            if original_pixmap.width() > max_size or original_pixmap.height() > max_size:
                thumbnail_pixmap = original_pixmap.scaled(max_size, max_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            # 创建可点击的图片标签
            img_label = ClickableImageLabel(self)
            img_label.setPixmap(thumbnail_pixmap)
            img_label.setStyleSheet("border: 1px solid #ddd; border-radius: 4px; padding: 2px;")
            img_label.setToolTip("点击查看大图")
            
            # 点击放大
            img_label.clicked.connect(lambda: self._show_image_preview(original_pixmap))
            
            return img_label
            
        except Exception as e:
            # 图片加载失败，返回占位符
            placeholder = CaptionLabel("[图片加载失败]", self)
            placeholder.setStyleSheet("color: #e74c3c;")
            return placeholder
    
    def _show_image_preview(self, pixmap: QPixmap):
        """显示图片预览对话框"""
        dialog = ImagePreviewDialog(pixmap, self.window())
        dialog.exec()
    
    def set_selected(self, selected: bool):
        """设置选中状态"""
        self.checkbox.setChecked(selected)


class QuestionListFluent(QWidget):
    """题目列表页面"""
    back_requested = Signal()
    export_requested = Signal(list)
    login_required = Signal()  # 新增: 需要登录信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("QuestionListInterface")
        
        self.questions = []
        self.filtered_questions = []
        self.question_cards = []
        self.current_homework = None
        self.login_manager = None
        self.parse_worker = None
        
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 20, 36, 20)
        layout.setSpacing(16)
        
        # 面包屑导航
        self._create_breadcrumb(layout)
        
        # 标题和统计
        self._create_header(layout)
        
        # 工具栏
        self._create_toolbar(layout)
        
        # 题目列表
        self._create_content_area(layout)
        
        # 底部操作栏
        self._create_footer(layout)
        
        # 初始显示空状态（未登录提示）
        self.scroll_area.hide()
        self.empty_container.show()
    
    def _create_breadcrumb(self, parent_layout):
        """创建面包屑导航"""
        nav_layout = QHBoxLayout()
        
        self.back_btn = TransparentPushButton("返回作业列表", self, FIF.LEFT_ARROW)
        self.back_btn.clicked.connect(lambda: self.back_requested.emit())
        nav_layout.addWidget(self.back_btn)
        
        nav_layout.addStretch()
        
        parent_layout.addLayout(nav_layout)
    
    def _create_header(self, parent_layout):
        """创建标题区域"""
        header_layout = QHBoxLayout()
        
        # 标题
        title_layout = QVBoxLayout()
        self.title_label = TitleLabel("题目列表", self)
        self.homework_label = CaptionLabel("", self)
        self.homework_label.setStyleSheet("color: #888888;")
        title_layout.addWidget(self.title_label)
        title_layout.addWidget(self.homework_label)
        header_layout.addLayout(title_layout)
        
        header_layout.addStretch()
        
        # 统计信息
        self._create_stats_panel(header_layout)
        
        parent_layout.addLayout(header_layout)
    
    def _create_stats_panel(self, parent_layout):
        """创建统计面板"""
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)
        
        # 题目总数
        self.total_label = self._create_stat_item("总题数", "0", "#3498db")
        stats_layout.addWidget(self.total_label)
        
        # 正确数
        self.correct_label = self._create_stat_item("正确", "0", "#27ae60")
        stats_layout.addWidget(self.correct_label)
        
        # 错误数
        self.wrong_label = self._create_stat_item("错误", "0", "#e74c3c")
        stats_layout.addWidget(self.wrong_label)
        
        parent_layout.addLayout(stats_layout)
    
    def _create_stat_item(self, label: str, value: str, color: str) -> SimpleCardWidget:
        """创建统计项"""
        card = SimpleCardWidget(self)
        card.setFixedSize(80, 60)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        
        value_label = SubtitleLabel(value, card)
        value_label.setStyleSheet(f"color: {color};")
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setObjectName(f"stat_{label}")
        
        name_label = CaptionLabel(label, card)
        name_label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(value_label)
        layout.addWidget(name_label)
        
        return card
    
    def _create_toolbar(self, parent_layout):
        """创建工具栏"""
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(12)
        
        # 搜索框
        self.search_edit = SearchLineEdit(self)
        self.search_edit.setPlaceholderText("搜索题目内容...")
        self.search_edit.setFixedWidth(250)
        self.search_edit.textChanged.connect(self._filter_questions)
        toolbar_layout.addWidget(self.search_edit)
        
        # 类型筛选
        self.type_combo = ComboBox(self)
        self.type_combo.addItem("全部类型")
        self.type_combo.setFixedWidth(120)
        self.type_combo.currentIndexChanged.connect(self._filter_questions)
        toolbar_layout.addWidget(self.type_combo)
        
        # 状态筛选
        self.status_combo = ComboBox(self)
        self.status_combo.addItems(["全部", "仅正确", "仅错误"])
        self.status_combo.setFixedWidth(100)
        self.status_combo.currentIndexChanged.connect(self._filter_questions)
        toolbar_layout.addWidget(self.status_combo)
        
        toolbar_layout.addStretch()
        
        parent_layout.addLayout(toolbar_layout)
    
    def _create_content_area(self, parent_layout):
        """创建内容区域"""
        # 滚动区域
        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")
        
        # 内容容器
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(12)
        
        
        self.scroll_area.setWidget(self.content_widget)
        parent_layout.addWidget(self.scroll_area, 1)
        
        # 加载状态容器（居中显示）
        self.loading_container = QFrame(self)
        self.loading_container.setStyleSheet("background: transparent;")
        loading_layout = QVBoxLayout(self.loading_container)
        loading_layout.setContentsMargins(0, 80, 0, 0)
        loading_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        
        # 使用进度条替代加载圈
        self.loading_bar = IndeterminateProgressBar(self.loading_container)
        self.loading_bar.setFixedWidth(200)
        
        self.loading_label = CaptionLabel("正在解析题目...", self.loading_container)
        self.loading_label.setStyleSheet("color: #888888;")
        
        loading_layout.addWidget(self.loading_bar, alignment=Qt.AlignCenter)
        loading_layout.addSpacing(12)
        loading_layout.addWidget(self.loading_label, alignment=Qt.AlignCenter)
        loading_layout.addStretch()
        
        parent_layout.addWidget(self.loading_container, 1)
        self.loading_container.hide()
        
        # 空状态容器（居中显示）
        self.empty_container = QFrame(self)
        self.empty_container.setStyleSheet("background: transparent;")
        empty_layout = QVBoxLayout(self.empty_container)
        empty_layout.setContentsMargins(0, 80, 0, 0)
        empty_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        
        self.empty_label = BodyLabel("请选择作业解析题目", self.empty_container)
        self.empty_label.setStyleSheet("color: #888888; font-size: 14px;")
        
        self.login_hint_btn = PrimaryPushButton("点击登录", self.empty_container)
        self.login_hint_btn.setFixedWidth(120)
        self.login_hint_btn.clicked.connect(lambda: self.login_required.emit())
        self.login_hint_btn.hide()  # 默认隐藏
        
        empty_layout.addWidget(self.empty_label, alignment=Qt.AlignCenter)
        empty_layout.addSpacing(16)
        empty_layout.addWidget(self.login_hint_btn, alignment=Qt.AlignCenter)
        empty_layout.addStretch()
        
        parent_layout.addWidget(self.empty_container, 1)
        self.empty_container.hide()
    
    def _create_footer(self, parent_layout):
        """创建底部操作栏"""
        footer_layout = QHBoxLayout()
        
        # 全选操作
        self.select_all_cb = CheckBox("全选", self)
        self.select_all_cb.stateChanged.connect(self._on_select_all)
        footer_layout.addWidget(self.select_all_cb)
        
        # 快速选择按钮
        self.select_correct_btn = TransparentPushButton("选择正确题", self)
        self.select_correct_btn.clicked.connect(self._select_correct)
        footer_layout.addWidget(self.select_correct_btn)
        
        self.select_wrong_btn = TransparentPushButton("选择错误题", self)
        self.select_wrong_btn.clicked.connect(self._select_wrong)
        footer_layout.addWidget(self.select_wrong_btn)
        
        # 已选数量
        self.selected_label = CaptionLabel("已选择 0 题", self)
        self.selected_label.setStyleSheet("color: #888888;")
        footer_layout.addWidget(self.selected_label)
        
        footer_layout.addStretch()
        
        # 导出按钮
        self.export_selected_btn = PushButton("导出选中", self)
        self.export_selected_btn.clicked.connect(self._on_export_selected)
        self.export_selected_btn.setEnabled(False)
        footer_layout.addWidget(self.export_selected_btn)
        
        self.export_all_btn = PrimaryPushButton("导出全部", self)
        self.export_all_btn.clicked.connect(self._on_export_all)
        footer_layout.addWidget(self.export_all_btn)
        
        parent_layout.addLayout(footer_layout)
    
    # ==================== 数据操作 ====================
    
    def load_questions(self, homework_info: dict, login_manager):
        """加载题目列表"""
        # 清理之前的线程
        self._cleanup_worker()
        
        self.current_homework = homework_info
        self.login_manager = login_manager
        
        # 更新标题
        homework_title = homework_info.get('title', '未知作业')
        self.homework_label.setText(f"作业: {homework_title}")
        
        # 显示加载状态
        self._set_loading(True)
        
        # 启动解析线程
        self.parse_worker = QuestionParseWorker(homework_info, login_manager)
        self.parse_worker.questions_loaded.connect(self._on_questions_loaded)
        self.parse_worker.progress_update.connect(self._on_progress_update)
        self.parse_worker.error_occurred.connect(self._on_parse_error)
        self.parse_worker.finished.connect(lambda: self._set_loading(False))
        self.parse_worker.finished.connect(self._cleanup_worker)
        self.parse_worker.start()
    
    def _cleanup_worker(self):
        """清理工作线程"""
        if self.parse_worker and self.parse_worker.isRunning():
            self.parse_worker.quit()
            self.parse_worker.wait(1000)
        self.parse_worker = None
    
    def _on_questions_loaded(self, questions: list):
        """题目加载完成"""
        self.questions = questions
        self.filtered_questions = questions.copy()
        
        # 更新类型筛选选项
        self._update_type_filter()
        
        # 显示题目
        self._display_questions()
        self._update_stats()
        
        app_logger.info(f"解析了 {len(questions)} 道题目")
    
    def _on_progress_update(self, message: str, percentage: int):
        """进度更新"""
        self.loading_label.setText(message)
    
    def _on_parse_error(self, error_msg: str):
        """解析错误"""
        InfoBar.error(
            title="解析失败",
            content=error_msg,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self.window()
        )
        app_logger.error(f"题目解析失败: {error_msg}")
    
    def _update_type_filter(self):
        """更新类型筛选选项"""
        # 收集所有题目类型
        types = set()
        for q in self.questions:
            q_type = q.get('type', '未知')
            types.add(q_type)
        
        # 更新下拉框
        self.type_combo.clear()
        self.type_combo.addItem("全部类型")
        for t in sorted(types):
            self.type_combo.addItem(t)
    
    def _display_questions(self):
        """显示题目列表"""
        # 清空现有卡片
        self._clear_content()
        self.question_cards = []
        
        if not self.filtered_questions:
            self.scroll_area.hide()
            # 根据登录状态显示不同提示
            if self.login_manager:
                self.empty_label.setText("暂无题目数据")
                self.login_hint_btn.hide()
            else:
                self.empty_label.setText("暂无题目数据，请先登录")
                self.login_hint_btn.show()
            self.empty_container.show()
            return
        
        self.empty_container.hide()
        self.scroll_area.show()
        
        # 按分组显示题目
        current_section = None
        for i, question in enumerate(self.filtered_questions):
            # 检查是否需要添加分组标题
            question_section = question.get('section', '')
            if question_section and question_section != current_section:
                current_section = question_section
                # 创建分组标题卡片
                section_card = self._create_section_header(current_section)
                self.content_layout.addWidget(section_card)
            
            card = QuestionCard(question, i, self.content_widget)
            card.selection_changed.connect(self._update_selection_count)
            self.question_cards.append(card)
            self.content_layout.addWidget(card)
        
        # 添加底部占位
        self.content_layout.addStretch()
    
    def _create_section_header(self, section_title: str):
        """创建分组标题卡片 - 简洁风格"""
        header = QFrame(self.content_widget)
        header.setStyleSheet("""
            QFrame {
                background: #16a085;
                border-radius: 6px;
                margin-top: 8px;
            }
        """)
        
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 8, 16, 8)
        
        # 分组标题
        title_label = SubtitleLabel(section_title, header)
        title_label.setStyleSheet("color: white; font-weight: 500;")
        layout.addWidget(title_label)
        
        layout.addStretch()
        
        return header
    
    def _clear_content(self):
        """清空内容区域"""
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def _filter_questions(self):
        """筛选题目"""
        keyword = self.search_edit.text().strip().lower()
        type_filter = self.type_combo.currentText()
        status_filter = self.status_combo.currentIndex()  # 0=全部, 1=正确, 2=错误
        
        self.filtered_questions = []
        for q in self.questions:
            # 关键词匹配
            content = q.get('content', '').lower()
            if keyword and keyword not in content:
                continue
            
            # 类型匹配
            q_type = q.get('type', '未知')
            if type_filter != "全部类型" and q_type != type_filter:
                continue
            
            # 状态匹配
            is_correct = q.get('isCorrect', None)
            if status_filter == 1 and is_correct is not True:
                continue
            if status_filter == 2 and is_correct is not False:
                continue
            
            self.filtered_questions.append(q)
        
        self._display_questions()
    
    def _update_stats(self):
        """更新统计信息"""
        total = len(self.questions)
        correct = sum(1 for q in self.questions if q.get('isCorrect') is True)
        wrong = sum(1 for q in self.questions if q.get('isCorrect') is False)
        
        self.total_label.findChild(SubtitleLabel, "stat_总题数").setText(str(total))
        self.correct_label.findChild(SubtitleLabel, "stat_正确").setText(str(correct))
        self.wrong_label.findChild(SubtitleLabel, "stat_错误").setText(str(wrong))
    
    def _update_selection_count(self):
        """更新选中数量"""
        count = sum(1 for card in self.question_cards if card.is_selected)
        self.selected_label.setText(f"已选择 {count} 题")
        self.export_selected_btn.setEnabled(count > 0)
    
    def _on_select_all(self, state):
        """全选"""
        checked = (state == Qt.Checked)
        for card in self.question_cards:
            card.set_selected(checked)
    
    def _select_correct(self):
        """选择正确题"""
        for card in self.question_cards:
            is_correct = card.question_data.get('isCorrect')
            card.set_selected(is_correct is True)
    
    def _select_wrong(self):
        """选择错误题"""
        for card in self.question_cards:
            is_correct = card.question_data.get('isCorrect')
            card.set_selected(is_correct is False)
    
    def _on_export_selected(self):
        """导出选中题目"""
        selected = [card.question_data for card in self.question_cards if card.is_selected]
        if selected:
            homework_title = self.current_homework.get('title', '作业题目') if self.current_homework else '作业题目'
            course_name = self.current_homework.get('course_name', '') if self.current_homework else ''
            show_export_dialog(selected, homework_title, course_name, self.window())
    
    def _on_export_all(self):
        """导出全部题目"""
        if self.questions:
            homework_title = self.current_homework.get('title', '作业题目') if self.current_homework else '作业题目'
            course_name = self.current_homework.get('course_name', '') if self.current_homework else ''
            show_export_dialog(self.questions, homework_title, course_name, self.window())
    
    def _set_loading(self, loading: bool):
        """设置加载状态"""
        self.search_edit.setEnabled(not loading)
        self.type_combo.setEnabled(not loading)
        self.status_combo.setEnabled(not loading)
        self.export_all_btn.setEnabled(not loading)
        
        if loading:
            self.scroll_area.hide()
            self.empty_container.hide()
            self.loading_container.show()
        else:
            self.loading_container.hide()
            self.scroll_area.show()
    
    def clear_data(self):
        """清空数据"""
        self.questions = []
        self.filtered_questions = []
        self.question_cards = []
        self.current_homework = None
        self._clear_content()
        self.homework_label.setText("")
        
        # 显示空状态提示
        self.empty_label.setText("请选择作业解析题目")
        self.login_hint_btn.hide()
        self.scroll_area.hide()
        self.empty_container.show()
        
        # 重置统计
        self.total_label.findChild(SubtitleLabel, "stat_总题数").setText("0")
        self.correct_label.findChild(SubtitleLabel, "stat_正确").setText("0")
        self.wrong_label.findChild(SubtitleLabel, "stat_错误").setText("0")
