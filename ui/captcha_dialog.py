#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片验证码对话框 - Fluent Design 
"""

from PySide6.QtWidgets import (QVBoxLayout, QLabel, QFrame, QSizePolicy)
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QPixmap

from qfluentwidgets import (MessageBoxBase, SubtitleLabel, LineEdit, 
                            InfoBar, InfoBarPosition)
from core.enterprise_logger import app_logger

class CaptchaLoadWorker(QThread):
    """验证码图片加载线程

    原实现在主线程直接发网络请求，网络慢时整个界面会冻结；
    且验证码对话框是模态的（exec() 阻塞），期间用户完全无法操作。
    """
    loaded = Signal(bytes)
    failed = Signal(str)

    def __init__(self, session, headers, url, parent=None):
        super().__init__(parent)
        self.session = session
        self.headers = headers
        self.url = url

    def run(self):
        try:
            response = self.session.get(self.url, headers=self.headers, timeout=10)
            if response.status_code == 200 and response.content:
                self.loaded.emit(response.content)
            else:
                self.failed.emit(f"HTTP {response.status_code}")
        except Exception as e:
            self.failed.emit(str(e))


# 全局保持线程引用：防止对话框提前销毁时 QThread 被一并删除
# （QThread 在运行中被销毁会直接崩溃），线程结束后自我移除
_active_captcha_workers = set()


class CaptchaDialog(MessageBoxBase):
    """图片验证码对话框"""
    
    def __init__(self, session, headers, parent=None, captcha_url=None):
        super().__init__(parent)
        self.session = session
        self.headers = headers
        self.captcha_url = captcha_url
        self.captcha_code = ""
        self.is_cancelled = False
        self.captcha_worker = None
        
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
        """异步加载验证码图片（不阻塞主线程）"""
        # 上一次加载尚未结束时不重复发起，避免并发请求
        if self.captcha_worker is not None and self.captcha_worker.isRunning():
            return

        self.captcha_label.setText("正在获取...")

        captcha_url = self.captcha_url or "https://passport2.chaoxing.com/num/code"
        # 不挂到对话框上：对话框销毁不带走运行中的线程
        self.captcha_worker = CaptchaLoadWorker(self.session, self.headers, captcha_url)
        _active_captcha_workers.add(self.captcha_worker)
        self.captcha_worker.finished.connect(
            lambda w=self.captcha_worker: self._on_worker_finished(w))
        self.captcha_worker.loaded.connect(self._on_captcha_loaded)
        self.captcha_worker.failed.connect(self._on_captcha_failed)
        self.captcha_worker.start()

    def _on_worker_finished(self, worker):
        """仅在线程真正结束后销毁，避免 loaded 信号与 run 返回之间的竞态。"""
        _active_captcha_workers.discard(worker)
        if self.captcha_worker is worker:
            self.captcha_worker = None
        worker.deleteLater()

    def _on_captcha_loaded(self, data: bytes):
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            scaled = pixmap.scaled(200, 70, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.captcha_label.setPixmap(scaled)
        else:
            self.captcha_label.setText("图片解析失败")

    def _on_captcha_failed(self, msg: str):
        app_logger.warning(f"验证码加载失败: {msg}")
        self.captcha_label.setText("加载失败，点击重试")

    def _stop_worker(self):
        """对话框关闭时断开工作线程的数据回调

        只断开 loaded/failed，保留 finished 上的自清理连接，
        线程自然结束后仍会从 _active_captcha_workers 中移除。
        （不能用 blockSignals(True)：那会连 finished 一起屏蔽，集合将永久泄漏）
        """
        worker = getattr(self, 'captcha_worker', None)
        if worker is None:
            return
        try:
            worker.loaded.disconnect()
            worker.failed.disconnect()
        except (TypeError, RuntimeError):
            pass
        self.captcha_worker = None
        # 安排销毁：运行中的线程不能立即销毁（会崩溃），
        # 等 finished 后再 deleteLater；已结束的可直接调度销毁
        try:
            if worker.isRunning():
                # load_captcha 已连接统一 finished 清理；这里只断开 UI 数据回调。
                pass
            else:
                self._on_worker_finished(worker)
        except RuntimeError:
            pass

    def closeEvent(self, event):
        self._stop_worker()
        super().closeEvent(event)

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
