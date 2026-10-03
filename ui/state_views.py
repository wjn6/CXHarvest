#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可复用的小视图：可折叠长文本、空状态、加载态"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel, CaptionLabel, SubtitleLabel, TransparentPushButton,
    PrimaryPushButton, IndeterminateProgressBar, IconWidget
)
from qfluentwidgets import FluentIcon as FIF

from ui import palette


class CollapsibleLabel(QWidget):
    """超过阈值先截断并给出“展开/收起”，避免长答案在界面里看不全"""

    def __init__(self, text: str, parent=None, limit: int = 200,
                 color_token: str = 'text_primary'):
        super().__init__(parent)
        self._full = text or ''
        self._limit = max(1, int(limit))
        self._expanded = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.label = BodyLabel('', self)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.label.setStyleSheet(f"color: {palette.color(color_token)};")
        layout.addWidget(self.label, 1)

        self.toggle = TransparentPushButton(self)
        self.toggle.setFixedWidth(52)
        self.toggle.clicked.connect(self._toggle)
        layout.addWidget(self.toggle, 0, Qt.AlignBottom)

        self._refresh()

    @property
    def collapsible(self) -> bool:
        return len(self._full) > self._limit

    def _display_text(self) -> str:
        if self._expanded or not self.collapsible:
            return self._full
        return self._full[:self._limit].rstrip() + '…'

    def _refresh(self):
        self.label.setText(self._display_text())
        self.toggle.setVisible(self.collapsible)
        self.toggle.setText("收起" if self._expanded else "展开")

    def _toggle(self):
        self._expanded = not self._expanded
        self._refresh()


class EmptyStateView(QFrame):
    """空状态：图标 + 一句解释 + 可选主操作"""

    action_clicked = Signal()

    def __init__(self, title: str, hint: str = "", icon=FIF.EDIT,
                 action_text: str = "", parent=None, top_spacing: int = 80):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, top_spacing, 0, 0)
        layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        layout.setSpacing(10)

        self.icon = IconWidget(icon, self)
        self.icon.setFixedSize(44, 44)
        layout.addWidget(self.icon, 0, Qt.AlignHCenter)

        self.title_label = SubtitleLabel(title, self)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet(palette.text_style('text_secondary'))
        layout.addWidget(self.title_label, 0, Qt.AlignHCenter)

        self.hint_label = CaptionLabel(hint, self)
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet(palette.text_style('text_muted'))
        self.hint_label.setVisible(bool(hint))
        layout.addWidget(self.hint_label, 0, Qt.AlignHCenter)

        self.action_btn = PrimaryPushButton(action_text or "点击登录", self)
        self.action_btn.setFixedWidth(140)
        self.action_btn.setVisible(bool(action_text))
        self.action_btn.clicked.connect(self.action_clicked.emit)
        layout.addWidget(self.action_btn, 0, Qt.AlignHCenter)
        layout.addStretch()

    def set_message(self, title: str, hint: str = None, show_action: bool = None):
        self.title_label.setText(title)
        if hint is not None:
            self.hint_label.setText(hint)
            self.hint_label.setVisible(bool(hint))
        if show_action is not None:
            self.action_btn.setVisible(show_action)

    def set_icon(self, icon):
        self.icon.setIcon(icon)


class LoadingView(QFrame):
    """加载态：进度条 + 可变文案"""

    def __init__(self, text: str = "正在加载...", parent=None, top_spacing: int = 80):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, top_spacing, 0, 0)
        layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        layout.setSpacing(12)

        self.bar = IndeterminateProgressBar(self)
        self.bar.setFixedWidth(200)
        layout.addWidget(self.bar, 0, Qt.AlignHCenter)

        self.label = CaptionLabel(text, self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet(palette.text_style('text_muted'))
        layout.addWidget(self.label, 0, Qt.AlignHCenter)
        layout.addStretch()

    def set_text(self, text: str):
        self.label.setText(text)
