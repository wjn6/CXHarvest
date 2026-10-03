#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""外观 token：一处定义配色与字体，避免每个页面各写一份 isDarkTheme 分支"""

from PySide6.QtGui import QFont
from qfluentwidgets import isDarkTheme


def app_font() -> QFont:
    """应用级默认字体，启动时设置一次，各处就不必再兜底字号"""
    from core.common import AppConstants
    return QFont(AppConstants.DEFAULT_FONT_FAMILY, AppConstants.DEFAULT_FONT_SIZE)


def ensure_readable_font(widget, reference=None, fallback_pt: int = 9):
    """纯图标控件可能拿不到有效字号，按参考控件或应用字体兜底一次"""
    font = widget.font()
    if font.pointSize() > 0:
        return widget
    base = reference.font().pointSize() if reference is not None else -1
    font.setPointSize(base if base > 0 else fallback_pt)
    widget.setFont(font)
    return widget

_TOKENS = {
    # 文本
    'text_primary':    ('#333333', '#dddddd'),
    'text_secondary':  ('#555555', '#bbbbbb'),
    'text_muted':      ('#888888', '#999999'),
    'text_faint':      ('#aaaaaa', '#777777'),
    'caption':         ('#666666', '#aaaaaa'),
    # 语义色（深色下略微提亮保证对比度）
    'accent':          ('#0891b2', '#22b8cf'),
    'success':         ('#27ae60', '#2ecc71'),
    'warning':         ('#f39c12', '#f5b041'),
    'danger':          ('#e74c3c', '#ff6b6b'),
    'neutral':         ('#95a5a6', '#8a9698'),
    # 面与描边
    'surface':         ('#f5f5f5', '#2d2d2d'),
    'card':            ('#ffffff', '#383838'),
    'card_border':     ('#e2e2e2', '#454545'),
    'title_bar':       ('#f0f0f0', '#1f1f1f'),
    'title_bar_border': ('#e0e0e0', '#333333'),
    'toolbar':         ('#ffffff', '#2d2d2d'),
    'footer_bar':      ('#fafafa', '#252525'),
    'canvas':          ('#f5f5f5', '#1a1a1a'),
    'divider':         ('#e0e0e0', '#3d3d3d'),
    'divider_strong':  ('#d0d0d0', '#4d4d4d'),
    'chip_bg':         ('rgba(0, 0, 0, 0.04)', 'rgba(255, 255, 255, 0.08)'),
    'chip_border':     ('rgba(0, 0, 0, 0.08)', 'rgba(255, 255, 255, 0.12)'),
    'hover_overlay':   ('rgba(0, 0, 0, 0.05)', 'rgba(255, 255, 255, 0.10)'),
    'press_overlay':   ('rgba(0, 0, 0, 0.10)', 'rgba(255, 255, 255, 0.05)'),
    'scrollbar_track': ('#f0f0f0', '#2d2d2d'),
    'scrollbar_handle': ('#c0c0c0', '#5a5a5a'),
    'scrollbar_handle_hover': ('#a0a0a0', '#6a6a6a'),
}

# 旧代码里按浅色调色、期望自动反色的简写
_SHORT_ALIASES = {
    '#333': 'text_primary', '#333333': 'text_primary',
    '#555': 'text_secondary', '#555555': 'text_secondary',
    '#666': 'text_muted', '#666666': 'text_muted',
    '#888': 'text_muted', '#888888': 'text_muted',
    '#aaa': 'text_faint', '#aaaaaa': 'text_faint',
}


def color(token: str) -> str:
    """取当前主题下的 token 值"""
    pair = _TOKENS.get(token)
    if pair is None:
        return token                      # 允许直接透传字面色值
    return pair[1] if isDarkTheme() else pair[0]


def text_color(light_value: str) -> str:
    """兼容旧写法：传入浅色调色板里的字面色，返回当前主题对应值"""
    token = _SHORT_ALIASES.get(light_value.lower())
    return color(token) if token else light_value


def text_style(token: str = 'text_secondary') -> str:
    """返回可直接 setStyleSheet 的文本色样式"""
    return f"color: {color(token)};"


def surface_qss(object_name: str = 'QDialog') -> str:
    """对话框/页面底色 + 卡片描边，替代各页面重复的 dark/light 分支"""
    return f"""
        {object_name} {{
            background-color: {color('surface')};
            border: 1px solid {color('card_border')};
        }}
        CardWidget {{
            background-color: {color('card')};
            border: 1px solid {color('card_border')};
            border-radius: 8px;
        }}
        QLabel {{ color: {color('text_primary')}; }}
    """


def title_bar_qss(object_name: str) -> str:
    """无边框对话框自绘标题栏"""
    return f"""
        #{object_name} {{
            background-color: {color('title_bar')};
            border-bottom: 1px solid {color('title_bar_border')};
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
        }}
    """


def scroll_bar_qss(width: int = 10) -> str:
    """跟随主题的滚动条配色"""
    return f"""
        QScrollBar:vertical, QScrollBar:horizontal {{
            background-color: {color('scrollbar_track')};
            width: {width}px;
            height: {width}px;
        }}
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
            background-color: {color('scrollbar_handle')};
            border-radius: {width // 2}px;
            min-height: 30px;
            min-width: 30px;
        }}
        QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
            background-color: {color('scrollbar_handle_hover')};
        }}
        QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    """
