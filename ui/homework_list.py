#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
作业列表页面 - Fluent Design 重构版
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QHeaderView, QTableWidgetItem
)
from PySide6.QtCore import Qt, Signal, QThread

from qfluentwidgets import (
    SimpleCardWidget,
    SubtitleLabel, TitleLabel, CaptionLabel,
    PrimaryPushButton, PushButton, TransparentPushButton, ToolButton,
    SearchLineEdit, ComboBox, CheckBox,
    InfoBar, InfoBarPosition, TableWidget
)
from qfluentwidgets import FluentIcon as FIF

from core.enterprise_logger import app_logger
from core.homework_manager import HomeworkManager
from core.homework_question_parser import HomeworkQuestionParser
from ui import palette
from ui.screen_metrics import apply_page_margins
from ui.state_views import EmptyStateView, LoadingView
from ui.table_utils import (KeyedItem, install_adaptive_width, polish_table,
                            relocate_row_widgets,
                            status_item as table_status_item)
from ui.worker_lifecycle import retire_worker

import re
import time


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


class BatchExportWorker(QThread):
    """批量导出工作线程"""
    progress = Signal(str, int)  # 消息, 百分比
    questions_ready = Signal(list, list, str)  # 题目列表, 作业标题列表, 课程名称
    error = Signal(str)
    
    def __init__(self, homework_list: list, login_manager, course_name: str):
        super().__init__()
        self.homework_list = homework_list
        self.login_manager = login_manager
        self.course_name = course_name
        self._cancelled = False

    def cancel(self):
        """请求在当前作业解析完成后停止后续批处理。"""
        self._cancelled = True
    
    def run(self):
        try:
            all_questions = []
            homework_titles = []
            total = len(self.homework_list)
            parser = HomeworkQuestionParser(self.login_manager)
            
            for i, homework in enumerate(self.homework_list):
                if self._cancelled or self.isInterruptionRequested():
                    return
                title = homework.get('title', '未知作业')
                self.progress.emit(f'正在解析: {title}', int((i / total) * 100))
                homework_url = homework.get('url', '')
                questions = parser.parse_homework_questions(homework_url, title)
                
                if questions:
                    all_questions.extend(questions)
                    homework_titles.append(title)
            
            if not self._cancelled:
                self.progress.emit('解析完成', 100)
                self.questions_ready.emit(all_questions, homework_titles, self.course_name)
            
        except Exception as e:
            self.error.emit(str(e))


def _parse_homework_status(raw_status: str):
    """统一解析作业状态，返回 (display_text, color, is_completed, is_expired)"""
    s = str(raw_status or '').strip()
    lowered = s.lower()
    # 否定词必须先判断；旧逻辑按“完成/提交”子串匹配，会把“未完成、待提交”
    # 错误标记为已完成。
    if any(word in s for word in ("未完成", "待完成", "未提交", "待提交")) \
            or lowered in {'0', 'pending', 'not submitted'}:
        return "待完成", "#e74c3c", False, False
    if "过期" in s or "已截止" in s or lowered in {'2', 'expired'}:
        return "已过期", "#95a5a6", False, True
    if any(word in s for word in ("待批阅", "待批改", "待评分", "批阅中", "批改中")) \
            or lowered in {'reviewing', 'pending review'}:
        return "待批阅", "#f39c12", False, False
    if any(word in s for word in ("已完成", "已提交", "提交成功", "已批阅", "已批改", "已评分")) \
            or lowered in {'1', '完成', '提交', 'completed', 'submitted', 'graded'}:
        return "已完成", "#27ae60", True, False
    return "待完成", "#e74c3c", False, False


# 状态列排序秩：越靠前越"急"
_STATUS_RANK = {"待完成": 0, "待批阅": 1, "已完成": 2, "已过期": 3}

# 状态色块用的语义色 token（配色定义见 ui.palette）
_STATUS_TOKEN = {"待完成": "danger", "待批阅": "warning",
                 "已完成": "success", "已过期": "neutral"}


def _deadline_sort_key(deadline: str) -> str:
    """把 '2026-03-05 10:00' / '03-05 10:00' 归一为可字典序比较的数字串"""
    digits = re.sub(r'\D', '', deadline or '')
    if not digits:
        return '9' * 14          # 无截止时间排最后
    if len(digits) <= 8:         # 页面省略了年份，补当前年再比
        digits = time.strftime('%Y') + digits
    return digits.rjust(12, '0')[:14]


class HomeworkListFluent(QWidget):
    """作业列表页面"""
    homework_selected = Signal(dict)
    back_requested = Signal()
    login_required = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HomeworkListInterface")
        
        self.homework_list = []
        self.filtered_list = []
        self.current_course = None
        self.login_manager = None
        self.load_worker = None
        self.batch_worker = None
        # 行内“查看”按钮按作业 key 复用，排序/筛选只搬不重建
        self._view_buttons = {}
        self._syncing_selection = False
        self._title_col_adapter = None
        # 勾选集合：按作业唯一键记录，与表格行位置解耦（排序/筛选不丢失、不错位）
        self._selected_ids = set()
        
        self._init_ui()
    
    def resizeEvent(self, event):
        """窄屏收紧左右留白，把宽度让给内容"""
        super().resizeEvent(event)
        apply_page_margins(self, 20, 20)

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
        card._value_label = value_label
        
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
        palette.ensure_readable_font(self.refresh_btn, self)
        self.refresh_btn.clicked.connect(self._on_refresh)
        toolbar_layout.addWidget(self.refresh_btn)
        
        parent_layout.addLayout(toolbar_layout)
    
    def _create_table(self, parent_layout):
        """创建作业表格"""
        self.table = TableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["选择", "作业标题", "状态", "截止时间", "操作"])

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setMinimumSectionSize(56)
        self.table.setColumnWidth(0, 48)
        # 标题列：视口够宽就拉伸，不够宽保 220 起并交给横向滚动
        self._title_col_adapter = install_adaptive_width(self.table, 1, min_width=220)

        polish_table(self.table, row_height=44, hand_cursor=True)
        self.table.itemChanged.connect(self._on_item_changed)

        # 启用排序
        self.table.setSortingEnabled(True)
        header.setSortIndicatorShown(True)
        header.setSortIndicator(1, Qt.AscendingOrder)
        # 排序只移动 Item 不移动 cellWidget，排序后把“查看”按钮搬回对应行
        self.table.horizontalHeader().sortIndicatorChanged.connect(self._sync_row_widgets)

        # 双击进入详情
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)
        
        parent_layout.addWidget(self.table, 1)
        
        # 加载态（loading_label 保留给解析进度文案）
        self.loading_container = LoadingView("正在加载作业列表...", self)
        self.loading_label = self.loading_container.label
        parent_layout.addWidget(self.loading_container, 1)
        self.loading_container.hide()

        # 空状态
        self.empty_container = EmptyStateView("请选择课程查看作业",
                                              icon=FIF.DOCUMENT, action_text="点击登录",
                                              parent=self)
        self.empty_container.action_clicked.connect(lambda: self.login_required.emit())
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
        
        # 批量导出
        self.batch_export_btn = PrimaryPushButton("批量导出", self)
        self.batch_export_btn.clicked.connect(self._on_batch_export)
        self.batch_export_btn.setEnabled(False)
        footer_layout.addWidget(self.batch_export_btn)
        
        parent_layout.addLayout(footer_layout)
    
    # ==================== 数据操作 ====================
    
    def load_homework(self, course_info: dict, login_manager):
        """加载作业列表"""
        # 清理之前的线程
        self._cleanup_workers()

        previous_key = self._course_key(self.current_course)
        next_key = self._course_key(course_info)
        if previous_key != next_key:
            # 切换课程时不能在失败后重新显示上一门课程的作业。
            self.homework_list = []
            self.filtered_list = []
            self.table.setRowCount(0)
            self.table.hide()
            self.empty_container.set_message("正在加载作业列表...", show_action=False)
            self.empty_container.show()
            self.search_edit.blockSignals(True)
            self.status_combo.blockSignals(True)
            self.search_edit.clear()
            self.status_combo.setCurrentIndex(0)
            self.search_edit.blockSignals(False)
            self.status_combo.blockSignals(False)
        
        # 切换课程时清空上一课程的勾选
        self._selected_ids = set()
        self.select_all_cb.setChecked(False)
        self._update_selection_count()
        self._update_stats()
        
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
        self.load_worker.finished.connect(self._on_load_finished)
        self.load_worker.start()

    @staticmethod
    def _course_key(course_info: dict) -> str:
        if not course_info:
            return ""
        return str(course_info.get('id') or course_info.get('link') or course_info.get('name') or '')

    def _on_load_finished(self):
        worker = self.sender()
        if self.load_worker is worker:
            self.load_worker = None
            self._set_loading(False)
        if worker is not None:
            worker.deleteLater()
    
    def _cleanup_workers(self):
        """安全退役工作线程（不阻塞 UI，防止运行中 QThread 被回收崩溃）"""
        retire_worker(getattr(self, 'load_worker', None))
        self.load_worker = None
        retire_worker(getattr(self, 'batch_worker', None))
        self.batch_worker = None
    
    def _on_homework_loaded(self, homework_list: list):
        """作业加载完成"""
        if self.sender() is not None and self.sender() is not self.load_worker:
            return
        self.homework_list = homework_list
        self._remember_homework_count(len(homework_list))
        self._filter_homework()
        self._update_stats()

        app_logger.info(f"加载了 {len(homework_list)} 个作业")

    def _remember_homework_count(self, count: int):
        """把真实作业数回写本地缓存，课程列表下次直接读，省一次列表请求"""
        course_id = (self.current_course or {}).get('id')
        if not course_id:
            return
        try:
            from core.homework_count_manager import HomeworkCountManager
            HomeworkCountManager().remember_count(course_id, count)
            self.current_course['homework_count'] = count
        except Exception as e:
            app_logger.debug(f"回写作业数量失败: {e}")
    
    def _on_load_error(self, error_msg: str):
        """加载错误"""
        if self.sender() is not None and self.sender() is not self.load_worker:
            return
        self.homework_list = []
        self.filtered_list = []
        self._selected_ids.clear()
        self.table.setRowCount(0)
        self._update_selection_count()
        self._update_stats()
        expired = '登录' in error_msg and any(k in error_msg for k in ('过期', '失效', '未登录'))
        self.empty_container.set_message(
            "登录已失效，请重新登录" if expired else "作业加载失败，请重试",
            show_action=expired)
        self.table.hide()
        self.empty_container.show()
        InfoBar.error(
            title="登录已失效" if expired else "加载失败",
            content=error_msg,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self.window()
        )
        if expired:
            self.login_required.emit()
        app_logger.error(f"作业加载失败: {error_msg}")
    
    def _display_homework(self):
        """显示作业列表"""
        sorting_enabled = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        
        if not self.filtered_list:
            self.table.hide()
            # 根据登录状态显示不同提示
            if self.login_manager:
                self.empty_container.set_message("暂无作业数据", show_action=False)
            else:
                self.empty_container.set_message("暂无作业数据，请先登录", show_action=True)
            self.empty_container.show()
            self.select_all_cb.blockSignals(True)
            self.select_all_cb.setChecked(False)
            self.select_all_cb.blockSignals(False)
            self._update_selection_count()
            self.table.setSortingEnabled(sorting_enabled)
            return
        
        self.empty_container.hide()
        self.table.show()

        self.table.setRowCount(len(self.filtered_list))

        for row, homework in enumerate(self.filtered_list):
            key = self._hw_key(homework)

            # 勾选：用可勾选 Item 而非 cellWidget，排序时随行走且每行少一个控件
            check_item = QTableWidgetItem()
            check_item.setFlags((check_item.flags() | Qt.ItemIsUserCheckable)
                                & ~Qt.ItemIsEditable)
            check_item.setCheckState(Qt.Checked if key in self._selected_ids else Qt.Unchecked)
            check_item.setData(Qt.UserRole, key)
            check_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, check_item)

            # 标题（截断后 tooltip 给出全文，排序按标题文本）
            title = homework.get('title', '未知作业')
            title_item = KeyedItem(title)
            title_item.setData(Qt.UserRole, homework)
            self.table.setItem(row, 1, title_item)

            # 状态：圆点色块 + 中文，按 待完成→待批阅→已完成→已过期 排序
            raw_status = str(homework.get('status', '待完成'))
            display_status, _, _, _ = _parse_homework_status(raw_status)
            status_cell = table_status_item(display_status,
                                            _STATUS_RANK.get(display_status, 9),
                                            _STATUS_TOKEN.get(display_status, 'text_muted'))
            self.table.setItem(row, 2, status_cell)

            # 截止时间：文本按原样显示，排序用归一化数字串
            deadline = homework.get('deadline', '')  # 注意：manager返回的是deadline不是endTime
            deadline_item = KeyedItem(deadline, _deadline_sort_key(deadline))
            self.table.setItem(row, 3, deadline_item)

            # 操作按钮：同一作业复用同一个按钮，排序/筛选只搬不移除
            view_btn = self._view_buttons.get(key)
            if view_btn is None:
                view_btn = PushButton("查看", self)
                view_btn.setFixedWidth(64)
                view_btn.clicked.connect(lambda checked, h=homework: self._on_view_clicked(h))
                self._view_buttons[key] = view_btn
            self.table.setCellWidget(row, 4, view_btn)
        self.table.setSortingEnabled(sorting_enabled)
        self._sync_row_widgets()
        self._update_selection_count()
    @staticmethod
    def _hw_key(homework: dict) -> str:
        """作业唯一标识：url 优先，退化为 title"""
        url = homework.get('url') or ''
        if url:
            return f"url:{url}"
        return f"title:{homework.get('title', '')}"

    def _row_key(self, row: int):
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def _on_item_changed(self, item):
        """勾选状态改变：按作业唯一键维护选中集合"""
        if item.column() != 0 or self._syncing_selection:
            return
        key = item.data(Qt.UserRole)
        if not key:
            return
        if item.checkState() == Qt.Checked:
            self._selected_ids.add(key)
        else:
            self._selected_ids.discard(key)
        self._update_selection_count()

    def _sync_row_widgets(self, column=None, order=None):
        """排序/筛选后把“查看”按钮搬回其作业所在行，并回收不可见行的按钮"""
        keys = [k for k in (self._row_key(row) for row in range(self.table.rowCount())) if k]
        relocate_row_widgets(self.table, 4, self._view_buttons, keys)
        if self._title_col_adapter is not None:
            self._title_col_adapter.maybe_apply()
    
    def _filter_homework(self):
        """筛选作业"""
        keyword = self.search_edit.text().strip().lower()
        status_filter = self.status_combo.currentIndex()  # 0=全部, 1=待完成, 2=已完成, 3=已过期
        
        self.filtered_list = []
        for hw in self.homework_list:
            # 关键词匹配
            title = str(hw.get('title') or '').lower()
            if keyword and keyword not in title:
                continue
            
            # 状态匹配
            _, _, is_completed, is_expired = _parse_homework_status(hw.get('status', ''))
            
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
            _, _, is_completed, is_expired = _parse_homework_status(hw.get('status', ''))
            if is_completed:
                completed += 1
            elif not is_expired:
                pending += 1
        
        # 更新统计卡片
        if hasattr(self.pending_card, '_value_label'):
            self.pending_card._value_label.setText(str(pending))
        if hasattr(self.completed_card, '_value_label'):
            self.completed_card._value_label.setText(str(completed))
        if hasattr(self.total_card, '_value_label'):
            self.total_card._value_label.setText(str(total))
    
    def _update_selection_count(self):
        """更新选中数量"""
        count = len(self._selected_ids)
        self.selected_label.setText(f"已选择 {count} 项")
        self.batch_export_btn.setEnabled(count > 0)
        visible_keys = {self._hw_key(h) for h in self.filtered_list}
        self.select_all_cb.blockSignals(True)
        self.select_all_cb.setChecked(bool(visible_keys) and visible_keys.issubset(self._selected_ids))
        self.select_all_cb.blockSignals(False)
    
    def _on_select_all_changed(self, state):
        """全选/取消当前筛选结果，不在筛选内的行保持原勾选"""
        checked = (state == Qt.CheckState.Checked.value or state == Qt.CheckState.Checked)
        visible_keys = {self._hw_key(h) for h in self.filtered_list}
        if checked:
            self._selected_ids |= visible_keys
        else:
            self._selected_ids -= visible_keys
        self._syncing_selection = True
        try:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item is not None:
                    item.setCheckState(
                        Qt.Checked if item.data(Qt.UserRole) in self._selected_ids
                        else Qt.Unchecked)
        finally:
            self._syncing_selection = False
        self._update_selection_count()
    
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
    
    def _on_batch_export(self):
        """批量导出"""
        if not self.loading_container.isHidden():
            return
        if not self._selected_ids:
            return
        if self.batch_worker is not None and self.batch_worker.isRunning():
            return
        # 勾选集合是全局的（筛选只影响可见行），按课程作业原始顺序取全部勾选项，
        # 与"已选择 N 项"的计数口径保持一致
        selected = [h for h in self.homework_list if self._hw_key(h) in self._selected_ids]
        if not selected:
            return
        
        # 显示加载状态
        self._set_loading(True)
        self.loading_label.setText(f"正在解析 {len(selected)} 个作业...")
        
        # 启动批量解析线程
        course_name = self.current_course.get('name', '') if self.current_course else ''
        self.batch_worker = BatchExportWorker(selected, self.login_manager, course_name)
        self.batch_worker.progress.connect(self._on_batch_progress)
        self.batch_worker.questions_ready.connect(self._on_batch_questions_ready)
        self.batch_worker.error.connect(self._on_batch_error)
        self.batch_worker.finished.connect(self._on_batch_finished)
        self.batch_worker.start()

    def _on_batch_finished(self):
        worker = self.sender()
        if self.batch_worker is worker:
            self.batch_worker = None
        if worker is not None:
            worker.deleteLater()
    
    def _on_batch_progress(self, message: str, percentage: int):
        """批量解析进度"""
        self.loading_label.setText(message)
    
    def _on_batch_questions_ready(self, questions: list, homework_titles: list, course_name: str):
        """批量解析完成"""
        self._set_loading(False)
        
        if not questions:
            InfoBar.warning(
                title="无题目",
                content="所选作业中没有找到题目",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self.window()
            )
            return
        
        # 弹出导出对话框
        from ui.export_dialog import ExportDialog
        homework_title = f"{len(homework_titles)}个作业合集"
        dialog = ExportDialog(questions, homework_title, course_name, self.window(),
                              session=getattr(self.login_manager, 'session', None))
        dialog.exec()
        
        app_logger.info(f"批量导出: {len(questions)} 道题目，来自 {len(homework_titles)} 个作业")
    
    def _on_batch_error(self, error_msg: str):
        """批量解析错误"""
        self._set_loading(False)
        expired = '登录' in error_msg and any(k in error_msg for k in ('过期', '失效', '未登录'))
        InfoBar.error(
            title="登录已失效" if expired else "解析失败",
            content=error_msg,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self.window()
        )
        if expired:
            self.login_required.emit()
    
    def _on_refresh(self):
        """刷新"""
        if self.current_course and self.login_manager:
            self.load_homework(self.current_course, self.login_manager)
    
    def _set_loading(self, loading: bool):
        """设置加载状态"""
        self.search_edit.setEnabled(not loading)
        self.status_combo.setEnabled(not loading)
        self.refresh_btn.setEnabled(not loading)
        self.batch_export_btn.setEnabled(not loading and bool(self._selected_ids))
        
        if loading:
            if self.loading_container.isHidden():
                self._content_before_loading = (
                    'table' if not self.table.isHidden() else 'empty'
                )
            self.table.hide()
            self.empty_container.hide()
            self.loading_container.show()
        else:
            self.loading_container.hide()
            # 成功回调会主动显示 table/empty；失败或取消时恢复加载前页面。
            if self.table.isHidden() and self.empty_container.isHidden():
                if getattr(self, '_content_before_loading', 'empty') == 'table' and self.filtered_list:
                    self.table.show()
                else:
                    self.empty_container.show()
    
    def clear_data(self):
        """清空数据"""
        self._cleanup_workers()
        self.homework_list = []
        self.filtered_list = []
        self.current_course = None
        self._selected_ids = set()
        self.select_all_cb.setChecked(False)
        self._update_selection_count()
        self.table.setRowCount(0)
        # 释放复用的“查看”按钮，避免脱离表格后仍挂在页面下
        for btn in self._view_buttons.values():
            btn.setParent(None)
            btn.deleteLater()
        self._view_buttons = {}
        self.course_label.setText("")
        
        # 显示空状态提示
        self.empty_container.set_message("请选择课程查看作业", show_action=False)
        self.table.hide()
        self.empty_container.show()
        self._set_loading(False)
        
        # 重置统计
        if hasattr(self.pending_card, '_value_label'):
            self.pending_card._value_label.setText("0")
        if hasattr(self.completed_card, '_value_label'):
            self.completed_card._value_label.setText("0")
        if hasattr(self.total_card, '_value_label'):
            self.total_card._value_label.setText("0")
