#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导出历史页面 - Fluent Design
"""

import os
import subprocess
import platform
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QHeaderView
from PySide6.QtCore import Qt

from qfluentwidgets import (
    SubtitleLabel, TitleLabel, CaptionLabel,
    PushButton, TransparentToolButton,
    InfoBar, InfoBarPosition, MessageBox,
    CardWidget, SearchLineEdit, TableWidget
)
from qfluentwidgets import FluentIcon as FIF

from core.enterprise_logger import app_logger
from core.export_history import get_export_history_manager
from ui import palette
from ui.screen_metrics import apply_page_margins
from ui.state_views import EmptyStateView
from ui.table_utils import (KeyedItem, install_adaptive_width, polish_table,
                            relocate_row_widgets,
                            status_item as table_status_item)


class ExportHistoryFluent(QWidget):
    """导出历史页面"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.history_manager = get_export_history_manager()
        # 行内按钮容器按记录 id 复用；列宽自适应器在 _create_table 里装好
        self._row_actions = {}
        self._title_col_adapter = None
        self._init_ui()
        self._load_history()
    
    def resizeEvent(self, event):
        """窄屏收紧左右留白，把宽度让给内容"""
        super().resizeEvent(event)
        apply_page_margins(self, 24, 24)

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 24, 40, 24)
        layout.setSpacing(20)
        
        # 设置页面样式
        self.setStyleSheet("""
            QWidget {
                background-color: transparent;
            }
        """)
        
        # 标题区域
        self._create_header(layout)
        
        # 统计卡片
        self._create_stats(layout)
        
        # 工具栏
        self._create_toolbar(layout)
        
        # 历史列表
        self._create_table(layout)
    
    def _create_header(self, parent_layout):
        """创建标题区域"""
        header_layout = QHBoxLayout()
        header_layout.setSpacing(16)
        
        # 图标和标题
        title = TitleLabel("导出历史", self)
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # 刷新按钮
        refresh_btn = PushButton(FIF.SYNC, "刷新", self)
        refresh_btn.clicked.connect(self._load_history)
        header_layout.addWidget(refresh_btn)
        
        parent_layout.addLayout(header_layout)
    
    def _create_stats(self, parent_layout):
        """创建统计卡片"""
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(16)
        
        # 总导出次数
        self.total_card = self._create_stat_card("总导出", "0", "次")
        stats_layout.addWidget(self.total_card)
        
        # 总题目数
        self.questions_card = self._create_stat_card("总题目", "0", "题")
        stats_layout.addWidget(self.questions_card)
        
        # 课程数
        self.courses_card = self._create_stat_card("涉及课程", "0", "门")
        stats_layout.addWidget(self.courses_card)
        
        stats_layout.addStretch()
        
        parent_layout.addLayout(stats_layout)
    
    def _create_stat_card(self, title: str, value: str, unit: str) -> CardWidget:
        """创建统计卡片"""
        card = CardWidget(self)
        card.setFixedSize(140, 90)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        
        # 数值
        value_label = SubtitleLabel(value, card)
        value_label.setObjectName(f"stat_{title}")
        value_label.setAlignment(Qt.AlignCenter)
        card._value_label = value_label
        layout.addWidget(value_label)
        
        # 标题
        title_label = CaptionLabel(f"{title}", card)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        return card
    
    def _create_toolbar(self, parent_layout):
        """创建工具栏"""
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(12)
        
        # 搜索框
        self.search_edit = SearchLineEdit(self)
        self.search_edit.setPlaceholderText("搜索课程或作业...")
        self.search_edit.setFixedWidth(280)
        self.search_edit.textChanged.connect(self._filter_history)
        toolbar_layout.addWidget(self.search_edit)
        
        toolbar_layout.addStretch()
        
        # 清空历史按钮
        clear_btn = PushButton(FIF.DELETE, "清空历史", self)
        clear_btn.clicked.connect(self._clear_history)
        toolbar_layout.addWidget(clear_btn)
        
        parent_layout.addLayout(toolbar_layout)
    
    def _create_table(self, parent_layout):
        """创建历史列表表格"""
        self.table = TableWidget(self)

        # 启用边框并设置圆角
        self.table.setBorderVisible(True)
        self.table.setBorderRadius(8)

        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "时间", "课程", "作业", "题目数", "格式", "状态", "操作"
        ])

        # 列宽：短列定宽（ResizeToContents 会按最长文本撑到 280+，把操作列挤出视口），
        # 课程列可拖，作业列宽时拉伸、窄屏保最小宽并交给横向滚动
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Interactive)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        header.setMinimumSectionSize(56)
        self.table.setColumnWidth(0, 165)   # 时间
        self.table.setColumnWidth(1, 200)   # 课程
        self.table.setColumnWidth(3, 64)    # 题目数
        self.table.setColumnWidth(4, 92)    # 格式
        self.table.setColumnWidth(5, 64)    # 状态
        self.table.setColumnWidth(6, 84)    # 操作
        self._title_col_adapter = install_adaptive_width(self.table, 2, min_width=200)

        polish_table(self.table, row_height=48)

        # 排序：时间字典序即 chronologic，题目数/状态用显式排序键
        self.table.setSortingEnabled(True)
        header.setSortIndicatorShown(True)
        header.setSortIndicator(0, Qt.DescendingOrder)
        self.table.horizontalHeader().sortIndicatorChanged.connect(self._sync_row_widgets)

        parent_layout.addWidget(self.table, 1)
        
        # 空状态提示
        self.empty_container = EmptyStateView("暂无导出记录", hint="导出题目后会在这里留痕",
                                              icon=FIF.HISTORY, parent=self,
                                              top_spacing=24)
        self.empty_container.hide()
        parent_layout.addWidget(self.empty_container, 1)
    
    def _load_history(self):
        """加载历史记录"""
        history = self.history_manager.get_history()
        stats = self.history_manager.get_statistics()
        
        # 更新统计
        if hasattr(self.total_card, '_value_label'):
            self.total_card._value_label.setText(str(stats["total_exports"]))
        if hasattr(self.questions_card, '_value_label'):
            self.questions_card._value_label.setText(str(stats["total_questions"]))
        if hasattr(self.courses_card, '_value_label'):
            self.courses_card._value_label.setText(str(len(stats["courses"])))
        
        # 显示历史
        self._display_history(history)
    
    def _display_history(self, history: list):
        """显示历史记录"""
        self.table.setRowCount(0)

        if not history:
            self._release_action_widgets()
            self.table.hide()
            self.empty_container.show()
            return

        self.empty_container.hide()
        self.table.show()

        # 排序开启时逐行插入会反复触发整表重排，填充期间先关掉
        sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(history))

        for row, record in enumerate(history):
            # 时间（字典序即时间序）
            time_item = KeyedItem(record.get("timestamp", ""))
            time_item.setData(Qt.UserRole, record)  # 保存完整记录
            self.table.setItem(row, 0, time_item)

            course_item = KeyedItem(record.get("course_name", ""))
            self.table.setItem(row, 1, course_item)

            # 作业
            homework_titles = record.get("homework_titles", [])
            if len(homework_titles) > 2:
                homework_text = f"{homework_titles[0]} 等{len(homework_titles)}个"
            else:
                homework_text = ", ".join(homework_titles)
            homework_item = KeyedItem(
                homework_text, tooltip="\n".join(homework_titles) or homework_text)
            self.table.setItem(row, 2, homework_item)

            # 题目数：按数值排序，避免 "9" > "10"
            count = int(record.get("question_count", 0) or 0)
            question_item = KeyedItem(str(count), count)
            question_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, question_item)

            # 格式
            format_item = KeyedItem(record.get("export_format", ""))
            format_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 4, format_item)

            # 文件状态：圆点色块，存在=绿 / 已删除=灰
            file_exists = bool(record.get("file_exists", False))
            status_cell = table_status_item("存在" if file_exists else "已删除",
                                            0 if file_exists else 1,
                                            'success' if file_exists else 'neutral')
            self.table.setItem(row, 5, status_cell)

            # 操作按钮
            self.table.setCellWidget(row, 6, self._action_widget(record))

        self.table.setSortingEnabled(sorting)
        self._sync_row_widgets()

    def _make_tool_button(self, icon, tip: str) -> TransparentToolButton:
        btn = TransparentToolButton(icon, self.table)
        btn.setFixedSize(32, 32)
        btn.setToolTip(tip)
        palette.ensure_readable_font(btn, self)
        return btn

    def _action_widget(self, record: dict) -> QWidget:
        """行内操作按钮：按记录 id 复用，排序/筛选只搬不重建"""
        rid = record.get("id")
        widget = self._row_actions.get(rid)
        if widget is None:
            widget = QWidget()
            btn_layout = QHBoxLayout(widget)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            btn_layout.setSpacing(4)
            btn_layout.setAlignment(Qt.AlignCenter)

            open_btn = self._make_tool_button(FIF.FOLDER, "打开文件位置")
            open_btn.clicked.connect(lambda checked, r=record: self._open_file_location(r))
            widget._open_btn = open_btn
            btn_layout.addWidget(open_btn)

            del_btn = self._make_tool_button(FIF.DELETE, "删除记录")
            del_btn.clicked.connect(lambda checked, r=record: self._delete_record(r))
            btn_layout.addWidget(del_btn)

            self._row_actions[rid] = widget
        widget._open_btn.setEnabled(bool(record.get("file_exists", False)))
        return widget

    def _sync_row_widgets(self, column=None, order=None):
        """把操作按钮搬回其记录所在行，并回收当前不可见行的按钮"""
        keys = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            record = item.data(Qt.UserRole) if item else None
            if record:
                keys.append(record.get("id"))
        relocate_row_widgets(self.table, 6, self._row_actions, keys)
        if self._title_col_adapter is not None:
            self._title_col_adapter.maybe_apply()

    def _release_action_widgets(self):
        for widget in list(self._row_actions.values()):
            widget.setParent(None)
            widget.deleteLater()
        self._row_actions = {}
    
    def _filter_history(self, text: str):
        """筛选历史记录"""
        history = self.history_manager.get_history()
        
        if not text:
            self._display_history(history)
            return
        
        text = text.lower()
        filtered = [
            r for r in history
            if text in str(r.get("course_name") or "").lower()
            or any(text in str(h).lower() for h in (r.get("homework_titles") or []))
        ]
        
        self._display_history(filtered)
    
    def _open_file_location(self, record: dict):
        """打开文件所在位置"""
        file_path = record.get("file_path", "")
        
        if not os.path.exists(file_path):
            InfoBar.warning(
                title="文件不存在",
                content="该文件可能已被移动或删除",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self.window()
            )
            return
        
        try:
            if platform.system() == "Windows":
                subprocess.Popen(["explorer.exe", f"/select,{os.path.normpath(file_path)}"])
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(["open", "-R", file_path])
            else:  # Linux
                subprocess.Popen(["xdg-open", os.path.dirname(file_path)])
        except Exception as e:
            app_logger.error(f"打开文件位置失败: {e}")
    
    def _delete_record(self, record: dict):
        """删除记录"""
        record_id = record.get("id")
        if record_id and self.history_manager.delete_record(record_id):
            self._load_history()
            InfoBar.success(
                title="已删除",
                content="记录已删除",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self.window()
            )
    
    def _clear_history(self):
        """清空历史"""
        w = MessageBox(
            "确认清空",
            "确定要清空所有导出历史记录吗？此操作不可恢复。",
            self.window()
        )
        
        if w.exec():
            self.history_manager.clear_history()
            self._load_history()
            InfoBar.success(
                title="已清空",
                content="导出历史已清空",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self.window()
            )
    
    def refresh(self):
        """刷新页面"""
        self._load_history()
