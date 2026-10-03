#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""屏幕可用尺寸换算：让固定像素的窗口/对话框在小屏与高缩放下也能完整显示"""

from PySide6.QtCore import QSize
from PySide6.QtGui import QGuiApplication

_EDGE_MARGIN = 16


def available_size():
    """主屏可用区（已扣除任务栏），取不到时退回 1024x768"""
    screen = None
    app = QGuiApplication.instance()
    if app is not None:
        screen = app.primaryScreen()
    if screen is None:
        return QSize(1024, 768)
    return screen.availableGeometry().size()


def fit_size(preferred_w: int, preferred_h: int, min_w: int = 320,
             min_h: int = 360) -> QSize:
    """把首选尺寸压进可用区，且不低于系统下限"""
    avail = available_size()
    limit_w = max(min_w, avail.width() - _EDGE_MARGIN * 2)
    limit_h = max(min_h, avail.height() - _EDGE_MARGIN * 2)
    return QSize(min(max(preferred_w, min_w), limit_w),
                 min(max(preferred_h, min_h), limit_h))


def min_window_size(width_cap: int, height_cap: int) -> QSize:
    """窗口最小尺寸：不能超过可用区本身，否则小屏上无法缩放"""
    avail = available_size()
    return QSize(min(width_cap, max(480, avail.width() - _EDGE_MARGIN * 2)),
                 min(height_cap, max(360, avail.height() - _EDGE_MARGIN * 2)))


def page_margins(widget_width: int, wide: int = 36, narrow: int = 16) -> int:
    """页面左右留白：窄屏收紧，把宽度让给内容"""
    return wide if widget_width >= 900 else narrow


def apply_page_margins(widget, top: int = 20, bottom: int = 20) -> bool:
    """按当前宽度调整页面左右留白，返回是否发生了改变"""
    layout = widget.layout()
    if layout is None:
        return False
    margin = page_margins(widget.width())
    if layout.contentsMargins().left() == margin:
        return False
    layout.setContentsMargins(margin, top, margin, bottom)
    return True
