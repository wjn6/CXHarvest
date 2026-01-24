#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
作业列表页面 - Fluent Design 重构版
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QHeaderView,
    QAbstractItemView, QTableWidgetItem, QFrame
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont, QColor

from qfluentwidgets import (
    CardWidget, SimpleCardWidget,
    BodyLabel, SubtitleLabel, TitleLabel, CaptionLabel, StrongBodyLabel,
    PrimaryPushButton, PushButton, TransparentPushButton, ToolButton,
    SearchLineEdit, ComboBox, CheckBox, ProgressRing, IndeterminateProgressBar,
    InfoBar, InfoBarPosition, TableWidget,
    BreadcrumbBar
)
from qfluentwidgets import FluentIcon as FIF

from core.enterprise_logger import app_logger
from core.homework_manager import HomeworkManager


class HomeworkLoadWorker(QThread):
    """作业加载线程"""
    homework_loaded = Signal(list)
    progress_update = Signal(str)
    error_occurred = Signal(str)
    
    def __init__(self, course_info: dict, login_manager):
        super().__init__()
        self.course_info = course_info
        self.login_manager = login_manager
    
    def run(self):
        try:
            manager = HomeworkManager(self.login_manager)
            homework_list = manager.get_homework_list(self.course_info)
            self.homework_loaded.emit(homework_list)
        except Exception as e:
            self.error_occurred.emit(str(e))


class HomeworkListFluent(QWidget):
    """作业列表页面"""
    homework_selected = Signal(dict)
    back_requested = Signal()
    login_required = Signal()  # 新增: 需要登录信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HomeworkListInterface")
        
        self.homework_list = []
        self.filtered_list = []
        self.current_course = None
        self.login_manager = None
        self.load_worker = None
        
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
        
        # 作业表格
        self._create_table(layout)
        
        # 底部操作栏
        self._create_footer(layout)
        
        # 初始显示空状态（未登录提示）
        self.table.hide()
        self.empty_container.show()
    
    def _create_breadcrumb(self, parent_layout):
        """创建面包屑导航"""
        nav_layout = QHBoxLayout()
        
        # 返回按钮
        self.back_btn = TransparentPushButton("返回课程列表", self, FIF.LEFT_ARROW)
        self.back_btn.clicked.connect(lambda: self.back_requested.emit())
        nav_layout.addWidget(self.back_btn)
        
        nav_layout.addStretch()
        
        parent_layout.addLayout(nav_layout)
    
    def _create_header(self, parent_layout):
        """创建标题区域"""
        header_layout = QHBoxLayout()
        
        # 标题
        title_layout = QVBoxLayout()
        self.title_label = TitleLabel("作业列表", self)
        self.course_label = CaptionLabel("", self)
        self.course_label.setStyleSheet("color: #888888;")
        title_layout.addWidget(self.title_label)
        title_layout.addWidget(self.course_label)
        header_layout.addLayout(title_layout)
        
        header_layout.addStretch()
        
        # 统计卡片
        self._create_stats_cards(header_layout)
        
        parent_layout.addLayout(header_layout)
    
    def _create_stats_cards(self, parent_layout):
        """创建统计卡片"""
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)
        
        # 待完成
        self.pending_card = self._create_stat_card("待完成", "0", "#e74c3c")
        stats_layout.addWidget(self.pending_card)
        
        # 已完成
        self.completed_card = self._create_stat_card("已完成", "0", "#27ae60")
        stats_layout.addWidget(self.completed_card)
        
        # 总计
        self.total_card = self._create_stat_card("总计", "0", "#3498db")
        stats_layout.addWidget(self.total_card)
        
        parent_layout.addLayout(stats_layout)
    
    def _create_stat_card(self, label: str, value: str, color: str) -> SimpleCardWidget:
        """创建单个统计卡片"""
        card = SimpleCardWidget(self)
        card.setFixedSize(100, 70)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)
        
        value_label = SubtitleLabel(value, card)
        value_label.setStyleSheet(f"color: {color};")
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setObjectName(f"stat_value_{label}")
        
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
        self.search_edit.setPlaceholderText("搜索作业标题...")
        self.search_edit.setFixedWidth(250)
        self.search_edit.textChanged.connect(self._filter_homework)
        toolbar_layout.addWidget(self.search_edit)
        
        # 状态筛选
        self.status_combo = ComboBox(self)
        self.status_combo.addItems(["全部状态", "待完成", "已完成", "已过期"])
        self.status_combo.setFixedWidth(120)
        self.status_combo.currentIndexChanged.connect(self._filter_homework)
        toolbar_layout.addWidget(self.status_combo)
        
        toolbar_layout.addStretch()
        
        # 刷新按钮
        self.refresh_btn = ToolButton(FIF.SYNC, self)
        self.refresh_btn.clicked.connect(self._on_refresh)
        toolbar_layout.addWidget(self.refresh_btn)
        
        parent_layout.addLayout(toolbar_layout)
    
    def _create_table(self, parent_layout):
        """创建作业表格"""
        self.table = TableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["选择", "作业标题", "状态", "截止时间", "操作"])
        
        # 设置列宽
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(2, 80)
        self.table.setColumnWidth(3, 150)
        self.table.setColumnWidth(4, 100)
        
        # 设置选择模式
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        # 启用排序
        self.table.setSortingEnabled(True)
        header.setSortIndicatorShown(True)
        
        # 双击进入详情
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)
        
        parent_layout.addWidget(self.table, 1)
        
        # 加载状态容器（居中显示）
        self.loading_container = QFrame(self)
        self.loading_container.setStyleSheet("background: transparent;")
        loading_layout = QVBoxLayout(self.loading_container)
        loading_layout.setContentsMargins(0, 80, 0, 0)
        loading_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        
        # 使用进度条替代加载圈
        self.loading_bar = IndeterminateProgressBar(self.loading_container)
        self.loading_bar.setFixedWidth(200)
        
        self.loading_label = CaptionLabel("正在加载作业列表...", self.loading_container)
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
        
        self.empty_label = BodyLabel("暂无作业数据，请先登录", self.empty_container)
        self.empty_label.setStyleSheet("color: #888888; font-size: 14px;")
        
        self.login_hint_btn = PrimaryPushButton("点击登录", self.empty_container)
        self.login_hint_btn.setFixedWidth(120)
        self.login_hint_btn.clicked.connect(lambda: self.login_required.emit())
        
        empty_layout.addWidget(self.empty_label, alignment=Qt.AlignCenter)
        empty_layout.addSpacing(16)
        empty_layout.addWidget(self.login_hint_btn, alignment=Qt.AlignCenter)
        empty_layout.addStretch()
        
        parent_layout.addWidget(self.empty_container, 1)
        self.empty_container.hide()
    
    def _create_footer(self, parent_layout):
        """创建底部操作栏"""
        footer_layout = QHBoxLayout()
        
        # 全选
        self.select_all_cb = CheckBox("全选", self)
        self.select_all_cb.stateChanged.connect(self._on_select_all_changed)
        footer_layout.addWidget(self.select_all_cb)
        
        # 已选数量
        self.selected_label = CaptionLabel("已选择 0 项", self)
        self.selected_label.setStyleSheet("color: #888888;")
        footer_layout.addWidget(self.selected_label)
        
        footer_layout.addStretch()
        
        # 批量解析
        self.batch_parse_btn = PrimaryPushButton("解析选中作业", self)
        self.batch_parse_btn.clicked.connect(self._on_batch_parse)
        self.batch_parse_btn.setEnabled(False)
        footer_layout.addWidget(self.batch_parse_btn)
        
        parent_layout.addLayout(footer_layout)
    
    # ==================== 数据操作 ====================
    
    def load_homework(self, course_info: dict, login_manager):
        """加载作业列表"""
        self.current_course = course_info
        self.login_manager = login_manager
        
        # 更新标题
        course_name = course_info.get('name', '未知课程')
        self.course_label.setText(f"课程: {course_name}")
        
        # 显示加载状态
        self._set_loading(True)
        
        # 启动加载线程
        self.load_worker = HomeworkLoadWorker(course_info, login_manager)
        self.load_worker.homework_loaded.connect(self._on_homework_loaded)
        self.load_worker.error_occurred.connect(self._on_load_error)
        self.load_worker.finished.connect(lambda: self._set_loading(False))
        self.load_worker.start()
    
    def _on_homework_loaded(self, homework_list: list):
        """作业加载完成"""
        self.homework_list = homework_list
        self.filtered_list = homework_list.copy()
        self._display_homework()
        self._update_stats()
        
        app_logger.info(f"加载了 {len(homework_list)} 个作业")
    
    def _on_load_error(self, error_msg: str):
        """加载错误"""
        InfoBar.error(
            title="加载失败",
            content=error_msg,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self.window()
        )
        app_logger.error(f"作业加载失败: {error_msg}")
    
    def _display_homework(self):
        """显示作业列表"""
        self.table.setRowCount(0)
        
        if not self.filtered_list:
            self.table.hide()
            # 根据登录状态显示不同提示
            if self.login_manager:
                self.empty_label.setText("暂无作业数据")
                self.login_hint_btn.hide()
            else:
                self.empty_label.setText("暂无作业数据，请先登录")
                self.login_hint_btn.show()
            self.empty_container.show()
            return
        
        self.empty_container.hide()
        self.table.show()
        self.table.setRowCount(len(self.filtered_list))
        
        for row, homework in enumerate(self.filtered_list):
            # 选择框
            cb = CheckBox(self)
            cb.stateChanged.connect(self._update_selection_count)
            self.table.setCellWidget(row, 0, cb)
            
            # 标题
            title = homework.get('title', '未知作业')
            title_item = QTableWidgetItem(title)
            title_item.setData(Qt.UserRole, homework)
            self.table.setItem(row, 1, title_item)
            
            # 状态处理
            raw_status = str(homework.get('status', '待完成'))
            display_status = "待完成"
            status_color = "#e74c3c"  # 默认红色
            
            if "完成" in raw_status or "提交" in raw_status or "1" == raw_status:
                display_status = "已完成"
                status_color = "#27ae60"  # 绿色
            elif "过期" in raw_status or "截止" in raw_status or "2" == raw_status:
                display_status = "已过期"
                status_color = "#95a5a6"  # 灰色
            elif "批阅" in raw_status:
                 display_status = "待批阅"
                 status_color = "#f39c12"  # 橙色
            
            status_item = QTableWidgetItem(display_status)
            status_item.setForeground(QColor(status_color))
            self.table.setItem(row, 2, status_item)
            
            # 截止时间
            deadline = homework.get('deadline', '')  # 注意：manager返回的是deadline不是endTime
            deadline_item = QTableWidgetItem(deadline)
            self.table.setItem(row, 3, deadline_item)
            
            # 操作按钮
            view_btn = PushButton("查看", self)
            view_btn.setFixedWidth(80)
            view_btn.clicked.connect(lambda checked, h=homework: self._on_view_clicked(h))
            self.table.setCellWidget(row, 4, view_btn)
    
    def _filter_homework(self):
        """筛选作业"""
        keyword = self.search_edit.text().strip().lower()
        status_filter = self.status_combo.currentIndex()  # 0=全部, 1=待完成, 2=已完成, 3=已过期
        
        self.filtered_list = []
        for hw in self.homework_list:
            # 关键词匹配
            title = hw.get('title', '').lower()
            if keyword and keyword not in title:
                continue
            
            # 状态匹配
            status = str(hw.get('status', ''))
            is_completed = "完成" in status or "提交" in status or status == '1'
            is_expired = "过期" in status or "截止" in status or status == '2'
            
            if status_filter == 1 and (is_completed or is_expired): # 筛选待完成
                continue
            if status_filter == 2 and not is_completed: # 筛选已完成
                continue
            if status_filter == 3 and not is_expired: # 筛选已过期
                continue
            
            self.filtered_list.append(hw)
        
        self._display_homework()
    
    def _update_stats(self):
        """更新统计信息"""
        total = len(self.homework_list)
        
        pending = 0
        completed = 0
        
        for hw in self.homework_list:
            status = str(hw.get('status', ''))
            if "完成" in status or "提交" in status or status == '1':
                completed += 1
            elif not ("过期" in status or "截止" in status or status == '2'):
                pending += 1
        
        # 更新统计卡片
        self.pending_card.findChild(SubtitleLabel, "stat_value_待完成").setText(str(pending))
        self.completed_card.findChild(SubtitleLabel, "stat_value_已完成").setText(str(completed))
        self.total_card.findChild(SubtitleLabel, "stat_value_总计").setText(str(total))
    
    def _update_selection_count(self):
        """更新选中数量"""
        count = 0
        for row in range(self.table.rowCount()):
            cb = self.table.cellWidget(row, 0)
            if cb and cb.isChecked():
                count += 1
        
        self.selected_label.setText(f"已选择 {count} 项")
        self.batch_parse_btn.setEnabled(count > 0)
    
    def _on_select_all_changed(self, state):
        """全选状态改变"""
        checked = state == Qt.Checked
        for row in range(self.table.rowCount()):
            cb = self.table.cellWidget(row, 0)
            if cb:
                cb.setChecked(checked)
    
    def _on_row_double_clicked(self, row, col):
        """行双击处理"""
        item = self.table.item(row, 1)
        if item:
            homework = item.data(Qt.UserRole)
            if homework:
                self.homework_selected.emit(homework)
    
    def _on_view_clicked(self, homework: dict):
        """查看按钮点击"""
        self.homework_selected.emit(homework)
    
    def _on_batch_parse(self):
        """批量解析"""
        selected = []
        for row in range(self.table.rowCount()):
            cb = self.table.cellWidget(row, 0)
            if cb and cb.isChecked():
                item = self.table.item(row, 1)
                if item:
                    homework = item.data(Qt.UserRole)
                    if homework:
                        selected.append(homework)
        
        if selected:
            # TODO: 实现批量解析逻辑
            InfoBar.info(
                title="批量解析",
                content=f"已选择 {len(selected)} 个作业进行解析",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000,
                parent=self.window()
            )
    
    def _on_refresh(self):
        """刷新"""
        if self.current_course and self.login_manager:
            self.load_homework(self.current_course, self.login_manager)
    
    def _set_loading(self, loading: bool):
        """设置加载状态"""
        self.search_edit.setEnabled(not loading)
        self.status_combo.setEnabled(not loading)
        self.refresh_btn.setEnabled(not loading)
        
        if loading:
            self.table.hide()
            self.empty_container.hide()
            self.loading_container.show()
        else:
            self.loading_container.hide()
            self.table.show()
    
    def clear_data(self):
        """清空数据"""
        self.homework_list = []
        self.filtered_list = []
        self.current_course = None
        self.table.setRowCount(0)
        self.course_label.setText("")
        
        # 显示登录提示
        self.empty_label.setText("暂无作业数据，请先登录")
        self.login_hint_btn.show()
        self.table.hide()
        self.empty_container.show()
        
        # 重置统计
        self.pending_card.findChild(SubtitleLabel, "stat_value_待完成").setText("0")
        self.completed_card.findChild(SubtitleLabel, "stat_value_已完成").setText("0")
        self.total_card.findChild(SubtitleLabel, "stat_value_总计").setText("0")
