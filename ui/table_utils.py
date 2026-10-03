#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""表格通用观感、排序键与列宽自适应

QTableWidget 默认排序只比 DisplayRole 的字符串，且排序只移动 Item 不移动
cellWidget；这里统一补齐：显式排序键、行内按钮复用、窄屏列宽保底。
"""

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidgetItem

from qfluentwidgets import TableWidget, isDarkTheme

from ui import palette

_DOT_CACHE = {}


def _dot_pixmap(color_token: str) -> QPixmap:
    """状态色圆点：按 token + 主题缓存，切主题不会留旧色"""
    key = (color_token, isDarkTheme())
    cached = _DOT_CACHE.get(key)
    if cached is not None:
        return cached
    pix = QPixmap(10, 10)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(palette.color(color_token)))
    painter.drawEllipse(1, 1, 8, 8)
    painter.end()
    _DOT_CACHE[key] = pix
    return pix


def status_item(text: str, sort_key=None, color_token: str = 'text_muted') -> 'KeyedItem':
    """状态列：圆点 + 着色文本，做出类色块的观感但不引入行内控件"""
    item = KeyedItem(text, sort_key)
    item.setForeground(QColor(palette.color(color_token)))
    item.setData(Qt.DecorationRole, _dot_pixmap(color_token))
    item.setTextAlignment(Qt.AlignCenter)
    return item


class KeyedItem(QTableWidgetItem):
    """带显式排序键的单元格：显示秩中文名/日期文本，按秩或规范化时间排序"""

    def __init__(self, text: str, sort_key=None, tooltip: str = None):
        super().__init__(text)
        self._sort_key = text if sort_key is None else sort_key
        if tooltip is None and text:
            tooltip = text
        if tooltip is not None:
            self.setData(Qt.ToolTipRole, tooltip)

    def __lt__(self, other):
        if isinstance(other, KeyedItem):
            return self._sort_key < other._sort_key
        return str(self._sort_key) < str(other.text())


def polish_table(table: TableWidget, row_height: int = 44, hand_cursor: bool = False):
    """统一两张表的观感与滚动行为"""
    table.verticalHeader().hide()
    table.verticalHeader().setDefaultSectionSize(row_height)
    table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
    table.setAlternatingRowColors(True)
    table.setTextElideMode(Qt.ElideRight)
    table.setWordWrap(False)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
    table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
    table.horizontalHeader().setHighlightSections(False)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    if hand_cursor:
        table.setCursor(Qt.PointingHandCursor)


class _AdaptiveWidthFilter(QObject):
    """视口够宽时标题列拉伸，不够宽时保最小列宽并交给横向滚动"""

    def __init__(self, table: TableWidget, column: int, min_width: int):
        super().__init__(table)
        self._table = table
        self._column = column
        self._min_width = min_width
        self._stretching = None

    def maybe_apply(self):
        header = self._table.horizontalHeader()
        others = sum(header.sectionSize(c) for c in range(self._table.columnCount())
                     if c != self._column)
        wide = self._table.viewport().width() >= others + self._min_width
        if self._stretching is wide:
            return
        self._stretching = wide
        if wide:
            header.setSectionResizeMode(self._column, QHeaderView.Stretch)
        else:
            header.setSectionResizeMode(self._column, QHeaderView.Interactive)
            self._table.setColumnWidth(self._column, self._min_width)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Resize:
            self.maybe_apply()
        return super().eventFilter(watched, event)


def install_adaptive_width(table: TableWidget, column: int, min_width: int = 220):
    """安装标题列自适应策略，返回过滤器以便后续手动触发"""
    table.setColumnWidth(column, min_width)
    adapter = _AdaptiveWidthFilter(table, column, min_width)
    table.viewport().installEventFilter(adapter)
    table.horizontalHeader().installEventFilter(adapter)
    return adapter


def relocate_row_widgets(table: TableWidget, column: int, widgets_by_key, keys_in_row_order):
    """按当前行顺序复用已有控件，避免排序/筛选时反复创建按钮控件"""
    for row, key in enumerate(keys_in_row_order):
        widget = widgets_by_key.get(key)
        if widget is None:
            continue
        if table.cellWidget(row, column) is not widget:
            table.setCellWidget(row, column, widget)
    keep = set(keys_in_row_order)
    for key in [k for k in widgets_by_key if k not in keep]:
        widget = widgets_by_key.pop(key)
        widget.setParent(None)
        widget.deleteLater()
