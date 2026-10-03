#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
双因子安全验证 - Fluent Design
第一界面：原生短信验证对话框（程序格式）；
第二界面：点击"获取验证码"后弹出的点选安全验证窗口，仅内嵌超星验证码组件，不使用官方页面。
"""

from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtCore import Qt, QThread, QTimer, Signal, Slot, QObject, QUrl
from PySide6.QtGui import QColor

from qfluentwidgets import (
    MessageBoxBase, SubtitleLabel, BodyLabel, CaptionLabel,
    LineEdit, PushButton, PrimaryPushButton,
)

from core.enterprise_logger import app_logger
from core.login_manager import LoginManager
from ui.worker_lifecycle import retire_worker

# 超星验证码组件配置（与官方 2FA 页面一致）
CAPTCHA_ID = "GcXX5vewqE7DezKGlyvleKCnkTglvGpL"

# 宿主页：origin 为 passport2.chaoxing.com，仅加载验证码组件本身，flex 居中消除空白
_CAPTCHA_HOST_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="/js/jquery.min.js"></script>
<style>
html,body{margin:0;padding:0;width:100%;height:100%;background:transparent;overflow:hidden;
display:flex;justify-content:center;align-items:center;}
#captcha{margin:auto;}
</style>
</head><body>
<div id="captcha"></div>
<script>
if (window.qt && qt.webChannelTransport) {
    new QWebChannel(qt.webChannelTransport, function (ch) { window.py = ch.objects.bridge; });
}
function getTimestamp(t) { return new Date().getTime() + t; }
function loadScript(url, cb) {
    var s = document.createElement('script');
    s.src = url; s.onload = cb;
    s.onerror = function () { if (window.py) window.py.onLoadError('sdk load failed'); };
    document.head.appendChild(s);
}
var capInstance = null;
loadScript('https://captcha.chaoxing.com/load.min.js?t=' + getTimestamp(60000), function () {
    try {
        initCXCaptcha({
            captchaId: '""" + CAPTCHA_ID + """',
            element: '#captcha',
            mode: 'embed',
            language: 'CN',
            type: 'textclick',
            onVerify: function (err, data) {
                if (err) return;
                window.__cx_validate = data.validate;
                if (window.py) window.py.onValidate(data.validate);
                if (capInstance) capInstance.refresh();
            }
        }, function (inst) {
            capInstance = inst;
            if (window.py) window.py.onReady();
        }, function (err) {
            if (window.py) window.py.onLoadError(String(err));
        });
    } catch (e) {
        if (window.py) window.py.onLoadError(String(e));
    }
});
</script></body></html>"""


class _CaptchaBridge(QObject):
    """WebEngine -> Qt 桥：接收验证码组件回调"""
    validated = Signal(str)
    ready = Signal()
    load_error = Signal(str)

    @Slot(str)
    def onValidate(self, validate: str):
        self.validated.emit(validate)

    @Slot()
    def onReady(self):
        self.ready.emit()

    @Slot(str)
    def onLoadError(self, msg: str):
        self.load_error.emit(msg)


class ClickCaptchaDialog(MessageBoxBase):
    """第二界面：点选安全验证窗口（仅内嵌验证码组件）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.validate = ""

        self.titleLabel = SubtitleLabel("请完成安全验证", self)
        self.viewLayout.addWidget(self.titleLabel)

        self.status_label = CaptionLabel("正在加载安全验证...", self)
        self.status_label.setStyleSheet("color: #888888;")
        self.viewLayout.addWidget(self.status_label)

        self.yesButton.hide()
        self.yesButton.deleteLater()
        self.cancelButton.setText("关闭")
        self.widget.setFixedWidth(400)

        self._init_captcha_view()

    def _init_captcha_view(self):
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            from PySide6.QtWebChannel import QWebChannel
        except ImportError:
            self.status_label.setText("缺少 WebEngine 组件，无法加载安全验证")
            self.status_label.setStyleSheet("color: #e74c3c;")
            return

        self.bridge = _CaptchaBridge(self)
        self.bridge.validated.connect(self._on_validated)
        self.bridge.ready.connect(self._on_ready)
        self.bridge.load_error.connect(self._on_load_error)

        self.captcha_view = QWebEngineView(self)
        self.captcha_view.setFixedSize(340, 240)  # 紧凑尺寸，仅容纳组件本体
        channel = QWebChannel(self.captcha_view.page())
        channel.registerObject("bridge", self.bridge)
        self.captcha_view.page().setWebChannel(channel)
        self.captcha_view.page().setBackgroundColor(QColor(0, 0, 0, 0))
        self.captcha_view.setHtml(_CAPTCHA_HOST_HTML, QUrl("https://passport2.chaoxing.com/"))
        self.viewLayout.addWidget(self.captcha_view, 0, Qt.AlignCenter)

    def _on_ready(self):
        self.status_label.setText("请依次点击图中文字完成验证")
        self.status_label.setStyleSheet("color: #888888;")

    def _on_load_error(self, msg: str):
        self.status_label.setText(f"安全验证加载失败：{msg}")
        self.status_label.setStyleSheet("color: #e74c3c;")

    def _on_validated(self, validate: str):
        """点选验证通过，记录 validate 并关闭窗口"""
        self.validate = validate
        self.accept()


class _SendSmsWorker(QThread):
    """发送短信验证码线程"""
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, manager: LoginManager, phone: str, validate: str):
        super().__init__()
        self.manager = manager
        self.phone = phone
        self.validate = validate
        self._stop = False

    def run(self):
        try:
            ret = self.manager.two_factor_send_sms(self.phone, self.validate)
            if self._stop:
                return
            if ret['result']:
                self.finished_ok.emit()
            else:
                self.failed.emit(ret['msg'] or '验证码发送失败')
        except Exception as e:
            if not self._stop:
                self.failed.emit(str(e))

    def stop(self):
        self._stop = True


class _CheckWorker(QThread):
    """提交短信验证码线程"""
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, manager: LoginManager, two_url: str, phone: str, vcode: str):
        super().__init__()
        self.manager = manager
        self.two_url = two_url
        self.phone = phone
        self.vcode = vcode
        self._stop = False

    def run(self):
        try:
            ret = self.manager.two_factor_check(self.two_url, self.phone, self.vcode)
            if self._stop:
                return
            if ret['status']:
                self.finished_ok.emit(ret)
            else:
                self.failed.emit(ret['mes'] or '验证失败')
        except Exception as e:
            if not self._stop:
                self.failed.emit(str(e))

    def stop(self):
        self._stop = True


class _ResetPwdWorker(QThread):
    """弱密码重置线程"""
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, manager: LoginManager, userid: str, token: str,
                 new_password: str, validate: str):
        super().__init__()
        self.manager = manager
        self.userid = userid
        self.token = token
        self.new_password = new_password
        self.validate = validate
        self._stop = False

    def run(self):
        try:
            ret = self.manager.two_factor_reset_password(
                self.userid, self.token, self.new_password, self.validate)
            if self._stop:
                return
            if ret['status']:
                self.finished_ok.emit()
            else:
                self.failed.emit(ret['mes'] or '密码重置失败')
        except Exception as e:
            if not self._stop:
                self.failed.emit(str(e))

    def stop(self):
        self._stop = True


class ResetPasswordDialog(MessageBoxBase):
    """第三界面：服务端强制弱密码重置（原生界面 + 点选验证码）"""
    reset_ok = Signal()

    def __init__(self, login_manager: LoginManager, userid: str, token: str, parent=None):
        super().__init__(parent)
        self.login_manager = login_manager
        self.userid = userid
        self.token = token
        self._validate = ""
        self._worker = None

        self.viewLayout.setSpacing(8)
        self.titleLabel = SubtitleLabel("重置密码", self)
        self.viewLayout.addWidget(self.titleLabel)

        self.tip_label = BodyLabel("检测到弱密码，为保证账号安全，请设置新密码后继续登录", self)
        self.tip_label.setWordWrap(True)
        self.viewLayout.addWidget(self.tip_label)

        from qfluentwidgets import PasswordLineEdit
        self.pwd_edit = PasswordLineEdit(self)
        self.pwd_edit.setPlaceholderText("新密码（8-16位，含数字和字母/符号）")
        self.viewLayout.addWidget(self.pwd_edit)

        self.pwd2_edit = PasswordLineEdit(self)
        self.pwd2_edit.setPlaceholderText("确认新密码")
        self.viewLayout.addWidget(self.pwd2_edit)

        self.status_label = CaptionLabel("提交时将弹出安全验证", self)
        self.status_label.setStyleSheet("color: #888888;")
        self.viewLayout.addWidget(self.status_label)

        self.submit_btn = PrimaryPushButton("重置并登录", self)
        self.submit_btn.clicked.connect(self._on_submit)
        self.viewLayout.addWidget(self.submit_btn)

        self.yesButton.hide()
        self.yesButton.deleteLater()
        self.cancelButton.setText("取消")
        self.widget.setFixedWidth(400)

    def _on_submit(self):
        pwd = self.pwd_edit.text()
        pwd2 = self.pwd2_edit.text()
        if len(pwd) < 8 or len(pwd) > 16:
            self._set_status("密码长度需为 8-16 位", "#e74c3c")
            return
        if pwd != pwd2:
            self._set_status("两次输入的密码不一致", "#e74c3c")
            return
        # 弹出点选安全验证，通过后提交改密
        dialog = ClickCaptchaDialog(self.window())
        dialog.exec()
        if not dialog.validate:
            return
        self._validate = dialog.validate
        self.submit_btn.setEnabled(False)
        self._set_status("正在重置密码...", "#888888")
        self._worker = _ResetPwdWorker(self.login_manager, self.userid, self.token,
                                       pwd, self._validate)
        self._worker.finished_ok.connect(self._on_ok)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_ok(self):
        self._set_status("密码重置成功", "#27ae60")
        self.reset_ok.emit()
        self.accept()

    def _on_failed(self, msg: str):
        self.submit_btn.setEnabled(True)
        self._set_status(f"重置失败：{msg}", "#e74c3c")

    def _set_status(self, text: str, color: str):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};")

    def _retire_workers(self):
        retire_worker(self._worker)
        self._worker = None

    def reject(self):
        self._retire_workers()
        super().reject()

    def hideEvent(self, event):
        """改密成功 accept 后同样要退役，避免线程随对话框回收"""
        self._retire_workers()
        super().hideEvent(event)


class TwoFactorDialog(MessageBoxBase):
    """第一界面：双因子短信安全验证（原生界面）"""
    verified = Signal()

    def __init__(self, login_manager: LoginManager, two_url: str, phone: str, parent=None):
        super().__init__(parent)
        self.login_manager = login_manager
        self.two_url = two_url
        self.phone = phone
        self._validate = ""
        self._send_worker = None
        self._check_worker = None
        self._countdown_timer = None
        self._countdown = 0

        self._init_ui()

    def _init_ui(self):
        self.viewLayout.setSpacing(8)
        self.titleLabel = SubtitleLabel("安全验证", self)
        self.viewLayout.addWidget(self.titleLabel)

        masked = self.phone[:3] + "****" + self.phone[-4:] if len(self.phone) >= 7 else self.phone
        self.tip_label = BodyLabel(f"由于长时间未登录，为保证账号安全，请输入 {masked} 收到的验证码", self)
        self.tip_label.setWordWrap(True)
        self.viewLayout.addWidget(self.tip_label)

        # 验证码输入 + 获取按钮
        code_layout = QHBoxLayout()
        code_layout.setSpacing(8)
        self.code_edit = LineEdit(self)
        self.code_edit.setPlaceholderText("验证码")
        self.code_edit.setMaxLength(6)
        code_layout.addWidget(self.code_edit, 1)

        self.get_code_btn = PushButton("获取验证码", self)
        self.get_code_btn.setFixedWidth(110)
        self.get_code_btn.clicked.connect(self._on_get_code)
        code_layout.addWidget(self.get_code_btn)
        self.viewLayout.addLayout(code_layout)

        # 状态提示
        self.status_label = CaptionLabel("", self)
        self.status_label.setStyleSheet("color: #888888;")
        self.status_label.setWordWrap(True)
        self.viewLayout.addWidget(self.status_label)

        # 验证按钮
        self.verify_btn = PrimaryPushButton("验证", self)
        self.verify_btn.clicked.connect(self._on_verify)
        self.viewLayout.addWidget(self.verify_btn)

        self.yesButton.hide()
        self.yesButton.deleteLater()
        self.cancelButton.setText("取消")

        self.widget.setFixedWidth(400)

    # ---------------------------------------------------------------- 获取验证码
    def _on_get_code(self):
        """点击获取验证码：先弹出点选安全验证窗口，通过后自动发短信"""
        if self._send_worker and self._send_worker.isRunning():
            return
        dialog = ClickCaptchaDialog(self.window())
        dialog.exec()
        if not dialog.validate:
            return
        self._validate = dialog.validate
        self._send_sms()

    def _send_sms(self):
        self.get_code_btn.setEnabled(False)
        self._set_status("安全验证通过，正在发送短信验证码...", "#888888")
        self._send_worker = _SendSmsWorker(self.login_manager, self.phone, self._validate)
        self._send_worker.finished_ok.connect(self._on_sms_sent)
        self._send_worker.failed.connect(self._on_sms_failed)
        self._send_worker.start()

    def _on_sms_sent(self):
        self._set_status("验证码已发送，请注意查收短信", "#27ae60")
        self._countdown = 60
        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._tick_countdown)
        self._countdown_timer.start(1000)
        self._tick_countdown()

    def _tick_countdown(self):
        if self._countdown > 0:
            self.get_code_btn.setText(f"{self._countdown}秒后重试")
            self._countdown -= 1
        else:
            if self._countdown_timer:
                self._countdown_timer.stop()
            self.get_code_btn.setText("获取验证码")
            self.get_code_btn.setEnabled(True)

    def _on_sms_failed(self, msg: str):
        self.get_code_btn.setEnabled(True)
        self._validate = ""
        self._set_status(f"短信发送失败：{msg}（请重新点击获取验证码）", "#e74c3c")

    # ---------------------------------------------------------------- 验证
    def _on_verify(self):
        vcode = self.code_edit.text().strip()
        if not vcode:
            self._set_status("请输入短信验证码", "#e74c3c")
            return
        self.verify_btn.setEnabled(False)
        self._set_status("正在验证...", "#888888")
        self._check_worker = _CheckWorker(self.login_manager, self.two_url, self.phone, vcode)
        self._check_worker.finished_ok.connect(self._on_check_ok)
        self._check_worker.failed.connect(self._on_check_failed)
        self._check_worker.start()

    def _on_check_ok(self, result: dict):
        if result.get('weak_pwd'):
            # 服务端强制弱密码重置：弹出第三界面
            self._set_status("短信验证通过，还需重置弱密码", "#888888")
            dialog = ResetPasswordDialog(self.login_manager, result['userid'],
                                         result['token'], self.window())
            dialog.reset_ok.connect(self._on_reset_ok)
            dialog.exec()
            return
        self._set_status("安全验证成功", "#27ae60")
        self.verified.emit()
        self.accept()

    def _on_reset_ok(self):
        self._set_status("密码重置成功，登录完成", "#27ae60")
        self.verified.emit()
        self.accept()

    def _on_check_failed(self, msg: str):
        self.verify_btn.setEnabled(True)
        self._set_status(f"验证失败：{msg}", "#e74c3c")

    # ---------------------------------------------------------------- 工具
    def _set_status(self, text: str, color: str):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};")

    def _retire_workers(self):
        retire_worker(self._send_worker)
        self._send_worker = None
        retire_worker(self._check_worker)
        self._check_worker = None
        if self._countdown_timer:
            self._countdown_timer.stop()

    def reject(self):
        self._retire_workers()
        super().reject()

    def hideEvent(self, event):
        """验证成功 accept 后同样要退役，避免线程随对话框回收"""
        self._retire_workers()
        super().hideEvent(event)
