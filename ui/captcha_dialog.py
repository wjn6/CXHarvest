#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片验证码对话框 - Fluent Design 
"""

from PySide6.QtWidgets import (QVBoxLayout, QLabel, QFrame, QSizePolicy)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap

from qfluentwidgets import (MessageBoxBase, SubtitleLabel, LineEdit, 
                            InfoBar, InfoBarPosition)
from core.enterprise_logger import app_logger

class CaptchaDialog(MessageBoxBase):
    """图片验证码对话框"""
    
    def __init__(self, session, headers, parent=None, captcha_url=None):
        super().__init__(parent)
        self.session = session
        self.headers = headers
        self.captcha_url = captcha_url
        self.captcha_code = ""
        self.is_cancelled = False
        
        self.init_ui()
        # 延迟加载验证码
        QTimer.singleShot(100, self.load_captcha)
        
    def init_ui(self):
        """初始化用户界面"""
        # 设置标题
        self.titleLabel = SubtitleLabel("安全验证", self)
        self.viewLayout.addWidget(self.titleLabel)
        
        # 验证码区域
        self.create_captcha_area()
        
        # 输入框
        self.code_input = LineEdit(self)
        self.code_input.setPlaceholderText("请输入验证码 (不区分大小写)")
        self.code_input.setMaxLength(6)
        self.code_input.returnPressed.connect(self.accept_captcha)
        self.code_input.textChanged.connect(self.on_text_changed)
        self.viewLayout.addWidget(self.code_input)
        
        # 配置按钮
        self.yesButton.setText("确认")
        self.cancelButton.setText("取消")
        
        self.yesButton.setEnabled(False)
        self.yesButton.clicked.disconnect()
        self.yesButton.clicked.connect(self.accept_captcha)
        
        self.cancelButton.clicked.disconnect()
        self.cancelButton.clicked.connect(self.cancel_captcha)
        
        # 设置宽度
        self.widget.setFixedWidth(360)

    def create_captcha_area(self):
        """创建验证码显示区域"""
        captcha_container = QFrame(self)
        captcha_container.setFixedHeight(80)
        captcha_container.setStyleSheet("""
            QFrame {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                background-color: #f9f9f9;
            }
        """)
        
        layout = QVBoxLayout(captcha_container)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setAlignment(Qt.AlignCenter)
        
        self.captcha_label = QLabel("正在获取...", self)
        self.captcha_label.setAlignment(Qt.AlignCenter)
        self.captcha_label.setStyleSheet("border: none; background: transparent; color: #666;")
        self.captcha_label.setCursor(Qt.PointingHandCursor)
        self.captcha_label.mousePressEvent = self.refresh_captcha
        
        layout.addWidget(self.captcha_label)
        self.viewLayout.addWidget(captcha_container)

    def refresh_captcha(self, event=None):
        self.captcha_label.setText("刷新中...")
        self.load_captcha()
        
    def load_captcha(self):
        """加载验证码图片"""
        try:
            captcha_url = self.captcha_url if self.captcha_url else "https://passport2.chaoxing.com/num/code"
            # 简单GET请求
            response = self.session.get(captcha_url, headers=self.headers, timeout=5)
            
            if response.status_code == 200:
                pixmap = QPixmap()
                if pixmap.loadFromData(response.content):
                    scaled = pixmap.scaled(200, 70, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.captcha_label.setPixmap(scaled)
                    return
            
            self.captcha_label.setText("加载失败")
        except Exception:
            self.captcha_label.setText("网络错误")

    def on_text_changed(self, text):
        self.yesButton.setEnabled(len(text.strip()) >= 3)
        
    def accept_captcha(self):
        code = self.code_input.text().strip()
        if len(code) < 3:
            return
        self.captcha_code = code
        self.is_cancelled = False
        self.accept()
        
    def cancel_captcha(self):
        self.captcha_code = ""
        self.is_cancelled = True
        self.reject()
        
    def get_captcha_code(self):
        return "" if self.is_cancelled else self.captcha_code