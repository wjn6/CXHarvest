#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导出历史页面 - Fluent Design
"""

import os
import subprocess
import platform
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFileDialog
)
from PySide6.QtCore import Qt, Signal

from qfluentwidgets import (
    BodyLabel, SubtitleLabel, TitleLabel, CaptionLabel,
    PrimaryPushButton, PushButton, TransparentToolButton,
    InfoBar, InfoBarPosition, MessageBox,
    CardWidget, SearchLineEdit, TableWidget
)
from qfluentwidgets import FluentIcon as FIF

from core.enterprise_logger import app_logger
from core.export_history import get_export_history_manager


class ExportHistoryFluent(QWidget):
    """导出历史页面"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.history_manager = get_export_history_manager()
        self._init_ui()
        self._load_history()
    
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
        self.table.setWordWrap(False)
        
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "时间", "课程", "作业", "题目数", "格式", "状态", "操作"
        ])
        
        # 设置表格样式
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().hide()
        
        # 设置列宽
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        
        self.table.setColumnWidth(0, 150)  # 时间
        self.table.setColumnWidth(3, 80)   # 题目数
        self.table.setColumnWidth(4, 80)   # 格式
        self.table.setColumnWidth(5, 80)   # 状态
        self.table.setColumnWidth(6, 140)  # 操作
        
        # 设置行高
        self.table.verticalHeader().setDefaultSectionSize(50)
        
        parent_layout.addWidget(self.table, 1)
        
        # 空状态提示
        self.empty_label = BodyLabel("暂无导出记录", self)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.hide()
        parent_layout.addWidget(self.empty_label)
    
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
            self.table.hide()
            self.empty_label.show()
            return
        
        self.empty_label.hide()
        self.table.show()
        self.table.setRowCount(len(history))
        
        for row, record in enumerate(history):
            # 时间
            time_item = QTableWidgetItem(record.get("timestamp", ""))
            time_item.setData(Qt.UserRole, record)  # 保存完整记录
            self.table.setItem(row, 0, time_item)
            
            # 课程
            course_item = QTableWidgetItem(record.get("course_name", ""))
            self.table.setItem(row, 1, course_item)
            
            # 作业
            homework_titles = record.get("homework_titles", [])
            if len(homework_titles) > 2:
                homework_text = f"{homework_titles[0]} 等{len(homework_titles)}个"
            else:
                homework_text = ", ".join(homework_titles)
            homework_item = QTableWidgetItem(homework_text)
            homework_item.setToolTip("\n".join(homework_titles))
            self.table.setItem(row, 2, homework_item)
            
            # 题目数
            question_item = QTableWidgetItem(str(record.get("question_count", 0)))
            question_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, question_item)
            
            # 格式
            format_item = QTableWidgetItem(record.get("export_format", ""))
            format_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 4, format_item)
            
            # 文件状态
            file_exists = record.get("file_exists", False)
            status_text = "存在" if file_exists else "已删除"
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignCenter)
            if not file_exists:
                status_item.setForeground(Qt.gray)
            self.table.setItem(row, 5, status_item)
            
            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            btn_layout.setSpacing(4)
            btn_layout.setAlignment(Qt.AlignCenter)
            
            # 打开文件按钮 - 使用TransparentToolButton自动适配主题
            open_btn = TransparentToolButton(FIF.FOLDER, btn_widget)
            open_btn.setFixedSize(32, 32)
            open_btn_font = open_btn.font()
            if open_btn_font.pointSize() <= 0:
                base_point_size = self.font().pointSize()
                open_btn_font.setPointSize(base_point_size if base_point_size > 0 else 9)
                open_btn.setFont(open_btn_font)
            open_btn.setEnabled(file_exists)
            open_btn.clicked.connect(lambda checked, r=record: self._open_file_location(r))
            btn_layout.addWidget(open_btn)
            
            # 删除记录按钮
            del_btn = TransparentToolButton(FIF.DELETE, btn_widget)
            del_btn.setFixedSize(32, 32)
            del_btn_font = del_btn.font()
            if del_btn_font.pointSize() <= 0:
                base_point_size = self.font().pointSize()
                del_btn_font.setPointSize(base_point_size if base_point_size > 0 else 9)
                del_btn.setFont(del_btn_font)
            del_btn.clicked.connect(lambda checked, r=record: self._delete_record(r))
            btn_layout.addWidget(del_btn)
            
            self.table.setCellWidget(row, 6, btn_widget)
    
    def _filter_history(self, text: str):
        """筛选历史记录"""
        history = self.history_manager.get_history()
        
        if not text:
            self._display_history(history)
            return
        
        text = text.lower()
        filtered = [
            r for r in history
            if text in r.get("course_name", "").lower()
            or any(text in h.lower() for h in r.get("homework_titles", []))
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
                subprocess.run(["explorer", f"/select,{file_path}"])
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", "-R", file_path])
            else:  # Linux
                subprocess.run(["xdg-open", os.path.dirname(file_path)])
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
