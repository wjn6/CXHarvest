#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
登录对话框 - Fluent Design 重构版
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QLabel, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer, QSize
from PySide6.QtGui import QPixmap, QFont

from qfluentwidgets import (
    MessageBoxBase, SubtitleLabel, BodyLabel, CaptionLabel,
    PrimaryPushButton, PushButton, TransparentPushButton,
    LineEdit, PasswordLineEdit, ProgressRing,
    SegmentedWidget, InfoBar, InfoBarPosition,
    ImageLabel, CardWidget
)
import threading
from qfluentwidgets import FluentIcon as FIF

from core.enterprise_logger import app_logger
from core.login_manager import LoginManager
from core.config_manager import get_config_manager

# 尝试导入 IndeterminateProgressPushButton，如果没有则使用兼容实现
try:
    from qfluentwidgets import IndeterminateProgressPushButton
except ImportError:
    class IndeterminateProgressPushButton(PrimaryPushButton):
        """兼容性实现：带加载状态的按钮"""
        def __init__(self, text, parent=None):
            super().__init__(parent=parent)
            self.setText(text)
            self._original_text = text
            
        def setLoading(self, is_loading):
            self.setEnabled(not is_loading)
            if is_loading:
                self._original_text = self.text()
                self.setText("处理中...")
            else:
                self.setText(self._original_text)


class VerificationCodeWorker(QThread):
    """验证码发送线程"""
    send_success = Signal()
    send_error = Signal(str)
    captcha_needed = Signal(object, object)  # session, headers
    
    def __init__(self, phone: str, login_manager: LoginManager):
        super().__init__()
        self.phone = phone
        self.login_manager = login_manager
        self.captcha_event = threading.Event()
        self.captcha_result = ""
    
    def run(self):
        try:
            # 注入验证码处理回调
            self.login_manager.captcha_handler = self._handle_captcha_request
            
            result = self.login_manager.send_verification_code(self.phone)
            if result:
                self.send_success.emit()
            else:
                self.send_error.emit("验证码发送失败，请稍后重试")
        except Exception as e:
            self.send_error.emit(str(e))
        finally:
            # 清理回调，防止循环引用或误调用
            self.login_manager.captcha_handler = None
            
    def _handle_captcha_request(self, session, headers):
        """处理验证码请求（在工作线程中调用）"""
        self.captcha_result = ""
        self.captcha_event.clear()
        
        # 发送信号请求主线程显示验证码对话框
        self.captcha_needed.emit(session, headers)
        
        # 等待主线程处理结果（超时120秒防止永久挂起）
        if not self.captcha_event.wait(timeout=120):
            return ""
        return self.captcha_result
        
    def submit_captcha_result(self, code: str):
        """提交验证码结果（由主线程调用）"""
        self.captcha_result = code
        self.captcha_event.set()


class LoginWorker(QThread):
    """登录线程"""
    login_success = Signal(dict)
    login_progress = Signal(str)
    qr_code_ready = Signal(str)
    qr_code_expired = Signal()  # 二维码过期信号
    login_error = Signal(str)
    
    def __init__(self, login_type: str, login_manager: LoginManager, **kwargs):
        super().__init__()
        self.login_type = login_type
        self.login_manager = login_manager
        self.username = kwargs.get('username', '')
        self.password = kwargs.get('password', '')
        self.phone = kwargs.get('phone', '')
        self.code = kwargs.get('code', '')
        self._stop_requested = False
    
    def run(self):
        try:
            if self.login_type == 'password':
                self.login_progress.emit("正在登录...")
                result = self.login_manager.login_with_password(self.username, self.password)
            elif self.login_type == 'sms':
                self.login_progress.emit("正在验证...")
                result = self.login_manager.login_with_verification_code(self.phone, self.code)
            elif self.login_type == 'qrcode':
                self.login_progress.emit("正在获取二维码...")
                qr_path = self.login_manager.get_qr_code()
                if qr_path:
                    self.qr_code_ready.emit(qr_path)
                    # 等待扫码
                    self.login_progress.emit("请使用学习通APP扫描二维码...")
                    result = self.login_manager.wait_for_qr_login(
                        stop_flag=lambda: self._stop_requested
                    )
                    # 如果返回False且不是被停止，说明二维码过期
                    if not result and not self._stop_requested:
                        self.qr_code_expired.emit()
                        return
                else:
                    result = None
            else:
                result = None
            
            if result and not self._stop_requested:
                # 获取用户信息
                user_info = self.login_manager.get_user_info()
                user_info['login_manager'] = self.login_manager
                self.login_success.emit(user_info)
            elif not self._stop_requested and self.login_type != 'qrcode':
                self.login_error.emit("登录失败，请检查账号信息")
                
        except Exception as e:
            if not self._stop_requested:
                self.login_error.emit(str(e))
    
    def stop(self):
        self._stop_requested = True


class LoginDialogFluent(MessageBoxBase):
    """登录对话框"""
    login_success = Signal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.login_manager = None
        self.login_worker = None
        self.code_worker = None
        self.countdown_timer = None
        self.countdown_seconds = 0
        self.current_login_type = "password"  # 跟踪当前登录方式
        self._pending_workers = []  # 保存待清理的线程引用，防止被垃圾回收
        
        self._init_ui()
        self._load_saved_credentials()
    
    def _init_ui(self):
        """初始化界面"""
        self.titleLabel = SubtitleLabel("登录超星学习通", self)
        self.viewLayout.addWidget(self.titleLabel)
        
        # 登录方式选择
        self.segment = SegmentedWidget(self)
        self.segment.addItem("password", "账号密码")
        self.segment.addItem("sms", "短信验证")
        self.segment.addItem("qrcode", "扫码登录")
        self.segment.setCurrentItem("password")
        self.segment.currentItemChanged.connect(self._on_tab_changed)
        self.viewLayout.addWidget(self.segment)
        
        # 内容区域
        self.content_stack = QStackedWidget(self)
        self.viewLayout.addWidget(self.content_stack)
        
        # 创建三种登录方式的页面
        self._create_password_page()
        self._create_sms_page()
        self._create_qrcode_page()
        
        # 状态显示区域
        status_container = QWidget(self)
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(0, 8, 0, 8)
        status_layout.setSpacing(8)
        
        # 状态文字 (加载圈移至按钮内)
        self.status_label = CaptionLabel("", status_container)
        self.status_label.setStyleSheet("color: #888888;")
        status_layout.addWidget(self.status_label)
        
        status_layout.addStretch()
        self.viewLayout.addWidget(status_container)
        
        # 替换默认的 yesButton 为 IndeterminateProgressPushButton
        self.yesButton.hide()
        self.yesButton.deleteLater()
        
        self.login_btn = IndeterminateProgressPushButton("登录", self)
        self.login_btn.clicked.connect(self._on_login_clicked)
        
        self.cancelButton.setText("取消")
        
        # 强制设置两个按钮平分宽度 (Stretch Factor = 1:1)
        self.cancelButton.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.login_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        
        # 重新添加到布局以确保 stretch 参数生效
        self.buttonLayout.removeWidget(self.cancelButton)
        self.buttonLayout.addWidget(self.cancelButton, 1)
        self.buttonLayout.addWidget(self.login_btn, 1)
        
        # 设置对话框大小
        self.widget.setFixedWidth(400)
    
    def _create_password_page(self):
        """创建账号密码登录页面"""
        from qfluentwidgets import CheckBox
        
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(16)
        
        # 用户名输入
        self.username_edit = LineEdit(page)
        self.username_edit.setPlaceholderText("请输入手机号/学号/邮箱")
        self.username_edit.setClearButtonEnabled(True)
        layout.addWidget(self.username_edit)
        
        # 密码输入
        self.password_edit = PasswordLineEdit(page)
        self.password_edit.setPlaceholderText("请输入密码")
        layout.addWidget(self.password_edit)
        
        # 记住密码复选框
        self.remember_password_cb = CheckBox("记住密码", page)
        self.remember_password_cb.setChecked(True)
        layout.addWidget(self.remember_password_cb)
        
        # 保存登录状态复选框（从配置读取初始状态）
        self.save_login_cb = CheckBox("保存登录状态（下次自动登录）", page)
        self.save_login_cb.setChecked(self._get_save_login_config())
        layout.addWidget(self.save_login_cb)
        
        # 提示
        tip_label = CaptionLabel("使用您的超星学习通账号登录", page)
        tip_label.setStyleSheet("color: #888888;")
        layout.addWidget(tip_label)
        
        layout.addStretch()
        self.content_stack.addWidget(page)
    
    def _create_sms_page(self):
        """创建短信验证登录页面"""
        from qfluentwidgets import CheckBox
        
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(16)
        
        # 手机号输入
        self.phone_edit = LineEdit(page)
        self.phone_edit.setPlaceholderText("请输入手机号")
        self.phone_edit.setClearButtonEnabled(True)
        layout.addWidget(self.phone_edit)
        
        # 验证码输入 + 获取按钮
        code_layout = QHBoxLayout()
        self.code_edit = LineEdit(page)
        self.code_edit.setPlaceholderText("请输入验证码")
        code_layout.addWidget(self.code_edit)
        
        self.send_code_btn = PushButton("获取验证码", page)
        self.send_code_btn.setFixedWidth(120)
        self.send_code_btn.clicked.connect(self._on_send_code)
        code_layout.addWidget(self.send_code_btn)
        
        layout.addLayout(code_layout)
        
        # 记住手机号复选框
        self.remember_phone_cb = CheckBox("记住手机号", page)
        self.remember_phone_cb.setChecked(True)
        layout.addWidget(self.remember_phone_cb)
        
        # 保存登录状态复选框（短信登录页面，从配置读取初始状态）
        self.save_login_sms_cb = CheckBox("保存登录状态（下次自动登录）", page)
        self.save_login_sms_cb.setChecked(self._get_save_login_config())
        layout.addWidget(self.save_login_sms_cb)
        
        # 提示
        tip_label = CaptionLabel("验证码将发送至您的手机", page)
        tip_label.setStyleSheet("color: #888888;")
        layout.addWidget(tip_label)
        
        layout.addStretch()
        self.content_stack.addWidget(page)
    
    def _create_qrcode_page(self):
        """创建扫码登录页面"""
        from qfluentwidgets import CheckBox
        
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignCenter)
        
        # 二维码显示区域
        self.qr_container = CardWidget(page)
        self.qr_container.setFixedSize(200, 200)
        qr_layout = QVBoxLayout(self.qr_container)
        qr_layout.setAlignment(Qt.AlignCenter)
        
        self.qr_label = QLabel(self.qr_container)
        self.qr_label.setFixedSize(180, 180)
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setText("点击登录按钮\n获取二维码")
        qr_layout.addWidget(self.qr_label)
        
        layout.addWidget(self.qr_container, alignment=Qt.AlignCenter)
        
        # 提示
        self.qr_tip_label = CaptionLabel("请使用学习通APP扫描二维码", page)
        self.qr_tip_label.setStyleSheet("color: #888888;")
        layout.addWidget(self.qr_tip_label, alignment=Qt.AlignCenter)
        
        # 刷新按钮
        self.refresh_qr_btn = TransparentPushButton("刷新二维码", page)
        self.refresh_qr_btn.clicked.connect(self._on_refresh_qr)
        self.refresh_qr_btn.hide()
        layout.addWidget(self.refresh_qr_btn, alignment=Qt.AlignCenter)
        
        # 保存登录状态复选框（扫码登录页面）
        self.save_login_qr_cb = CheckBox("保存登录状态（下次自动登录）", page)
        self.save_login_qr_cb.setChecked(self._get_save_login_config())
        layout.addWidget(self.save_login_qr_cb, alignment=Qt.AlignCenter)
        
        layout.addStretch()
        self.content_stack.addWidget(page)
    
    def _on_tab_changed(self, key: str):
        """切换登录方式"""
        # 如果有正在进行的登录线程，停止它
        self._stop_current_login()
        
        self.current_login_type = key  # 保存当前选中的登录方式
        index_map = {"password": 0, "sms": 1, "qrcode": 2}
        self.content_stack.setCurrentIndex(index_map.get(key, 0))
        
        # 更新登录按钮文本
        if key == "qrcode":
            self.login_btn.setText("获取二维码")
        else:
            self.login_btn.setText("登录")
        
        # 重置状态
        self._set_loading(False)
        self.status_label.setText("")
        
        # 重置二维码区域
        self._reset_qrcode_area()
    
    def _get_login_manager(self) -> LoginManager:
        """获取登录管理器（懒加载）"""
        if not self.login_manager:
            self.login_manager = LoginManager()
        return self.login_manager
    
    def _on_login_clicked(self):
        """登录按钮点击"""
        if self.current_login_type == "password":
            self._login_with_password()
        elif self.current_login_type == "sms":
            self._login_with_sms()
        elif self.current_login_type == "qrcode":
            self._login_with_qrcode()
    
    def _login_with_password(self):
        """账号密码登录"""
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        
        if not username:
            self._show_error("请输入账号")
            return
        if not password:
            self._show_error("请输入密码")
            return
        
        self._start_login("password", username=username, password=password)
    
    def _login_with_sms(self):
        """短信验证登录"""
        phone = self.phone_edit.text().strip()
        code = self.code_edit.text().strip()
        
        if not phone:
            self._show_error("请输入手机号")
            return
        if not code:
            self._show_error("请输入验证码")
            return
        
        self._start_login("sms", phone=phone, code=code)
    
    def _login_with_qrcode(self):
        """扫码登录"""
        self._start_login("qrcode")
    
    def _start_login(self, login_type: str, **kwargs):
        """启动登录"""
        self._set_loading(True)
        
        manager = self._get_login_manager()
        self.login_worker = LoginWorker(login_type, manager, **kwargs)
        self.login_worker.login_success.connect(self._on_login_success)
        self.login_worker.login_progress.connect(self._on_login_progress)
        self.login_worker.qr_code_ready.connect(self._on_qr_ready)
        self.login_worker.qr_code_expired.connect(self._on_qr_expired)
        self.login_worker.login_error.connect(self._on_login_error)
        self.login_worker.finished.connect(lambda: self._set_loading(False))
        self.login_worker.start()
    
    def _on_login_success(self, user_info: dict):
        """登录成功"""
        self.status_label.setText("登录成功")
        self.status_label.setStyleSheet("color: #27ae60;")
        
        # 保存凭据（如果用户选择记住）
        self._save_credentials()
        
        # 根据用户选择决定是否保存登录状态
        save_login = self._should_save_login()
        
        # 保存用户选择到配置文件
        self._set_save_login_config(save_login)
        
        if save_login:
            # 保存cookies用于下次自动登录
            self.login_manager.save_cookies()
            app_logger.info("已保存登录状态，下次将自动登录")
        else:
            # 不保存登录状态，只删除cookies文件，不清除session中的cookies
            try:
                from core.common import PathManager
                session_path = PathManager.get_file_path("session.txt", "data")
                if session_path.exists():
                    session_path.unlink()
            except Exception:
                pass
        
        # 发送信号
        self.login_success.emit(user_info)
        
        # 关闭对话框
        self.accept()
    
    def _should_save_login(self) -> bool:
        """检查用户是否选择保存登录状态"""
        if self.current_login_type == "password":
            return self.save_login_cb.isChecked()
        elif self.current_login_type == "sms":
            return self.save_login_sms_cb.isChecked()
        elif self.current_login_type == "qrcode":
            return self.save_login_qr_cb.isChecked()
        return False
    
    def _stop_current_login(self):
        """停止当前进行的登录线程"""
        if self.login_worker:
            worker = self.login_worker
            self.login_worker = None
            
            if worker.isRunning():
                worker.stop()
                # 断开信号连接，防止已停止的线程发送信号
                try:
                    worker.login_success.disconnect()
                    worker.login_progress.disconnect()
                    worker.qr_code_ready.disconnect()
                    worker.qr_code_expired.disconnect()
                    worker.login_error.disconnect()
                    worker.finished.disconnect()
                except Exception:
                    pass
                
                # 保存到待清理列表，防止被垃圾回收导致崩溃
                self._pending_workers.append(worker)
                # 线程结束后从列表移除
                worker.finished.connect(lambda w=worker: self._cleanup_worker(w))
                
                app_logger.info("已停止登录线程")
    
    def _cleanup_worker(self, worker):
        """清理已完成的线程"""
        try:
            if worker in self._pending_workers:
                self._pending_workers.remove(worker)
        except Exception:
            pass
    
    def _reset_qrcode_area(self):
        """重置二维码区域到初始状态"""
        self.qr_label.clear()
        self.qr_label.setText("点击登录按钮\n获取二维码")
        self.qr_tip_label.setText("请使用学习通APP扫描二维码")
        self.qr_tip_label.setStyleSheet("color: #888888;")
        self.refresh_qr_btn.hide()
    
    def _get_save_login_config(self) -> bool:
        """从配置读取保存登录状态选项"""
        try:
            config = get_config_manager().get_config()
            return config.save_login_info
        except Exception:
            return False
    
    def _set_save_login_config(self, value: bool):
        """保存登录状态选项到配置"""
        try:
            from core.config_manager import update_app_config
            update_app_config(save_login_info=value)
        except Exception as e:
            app_logger.warning(f"保存配置失败: {e}")
    
    def _load_saved_credentials(self):
        """加载保存的凭据"""
        try:
            manager = self._get_login_manager()
            saved_info = manager.load_login_info()
            
            if saved_info:
                # 加载账号密码页面的信息
                username = saved_info.get('username', '')
                password = saved_info.get('password', '')
                if username:
                    self.username_edit.setText(username)
                if password:
                    self.password_edit.setText(password)
                
                # 加载手机号
                phone = saved_info.get('phone', '')
                if phone:
                    self.phone_edit.setText(phone)
                    
                app_logger.debug("已加载保存的登录信息")
        except Exception as e:
            app_logger.debug(f"加载保存的凭据失败: {e}")
    
    def _save_credentials(self):
        """保存凭据到文件"""
        try:
            manager = self._get_login_manager()
            info = {}
            
            # 保存账号密码（如果勾选了记住密码）
            if self.remember_password_cb.isChecked():
                info['username'] = self.username_edit.text().strip()
                info['password'] = self.password_edit.text()
            
            # 保存手机号（如果勾选了记住手机号）
            if self.remember_phone_cb.isChecked():
                info['phone'] = self.phone_edit.text().strip()
            
            if info:
                manager.save_login_info(info)
                app_logger.debug("已保存登录信息")
        except Exception as e:
            app_logger.debug(f"保存凭据失败: {e}")
    
    def _on_login_progress(self, message: str):
        """登录进度"""
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: #888888;")
    
    def _on_qr_ready(self, qr_path: str):
        """二维码就绪"""
        pixmap = QPixmap(qr_path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(180, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.qr_label.setPixmap(scaled)
            self.refresh_qr_btn.show()
            self.qr_tip_label.setText("请使用学习通APP扫描二维码")
            self.qr_tip_label.setStyleSheet("color: #888888;")
    
    def _on_qr_expired(self):
        """二维码过期"""
        self.qr_label.setText("二维码已过期\n请点击刷新")
        self.qr_tip_label.setText("二维码已过期，请刷新后重试")
        self.qr_tip_label.setStyleSheet("color: #e74c3c;")
        self.status_label.setText("二维码已过期")
        self.status_label.setStyleSheet("color: #e74c3c;")
        self.refresh_qr_btn.show()
        self._set_loading(False)
    
    def _on_login_error(self, error_msg: str):
        """登录失败"""
        self._show_error(error_msg)
    
    def _on_send_code(self):
        """发送验证码"""
        phone = self.phone_edit.text().strip()
        
        if not phone or len(phone) != 11:
            self._show_error("请输入正确的手机号")
            return
        
        self.send_code_btn.setEnabled(False)
        
        manager = self._get_login_manager()
        self.code_worker = VerificationCodeWorker(phone, manager)
        self.code_worker.send_success.connect(self._on_code_sent)
        self.code_worker.send_error.connect(self._on_code_error)
        self.code_worker.captcha_needed.connect(self._on_captcha_needed)
        self.code_worker.start()
    
    def _on_captcha_needed(self, session, headers):
        """处理验证码显示请求"""
        # 延迟导入以避免循环依赖
        from ui.captcha_dialog import CaptchaDialog
        
        dialog = CaptchaDialog(session, headers, self)
        if dialog.exec():
            # 用户确认输入
            code = dialog.get_captcha_code()
            self.code_worker.submit_captcha_result(code)
        else:
            # 用户取消
            self.code_worker.submit_captcha_result("")
    
    def _on_code_sent(self):
        """验证码发送成功"""
        self.status_label.setText("验证码已发送")
        self.status_label.setStyleSheet("color: #27ae60;")
        
        # 开始倒计时
        self.countdown_seconds = 60
        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self._update_countdown)
        self.countdown_timer.start(1000)
        self._update_countdown()
    
    def _on_code_error(self, error_msg: str):
        """验证码发送失败"""
        self.send_code_btn.setEnabled(True)
        self._show_error(error_msg)
    
    def _update_countdown(self):
        """更新倒计时"""
        if self.countdown_seconds > 0:
            self.send_code_btn.setText(f"{self.countdown_seconds}秒后重试")
            self.countdown_seconds -= 1
        else:
            self.countdown_timer.stop()
            self.send_code_btn.setText("获取验证码")
            self.send_code_btn.setEnabled(True)
    
    def _on_refresh_qr(self):
        """刷新二维码"""
        self._login_with_qrcode()
    
    def _set_loading(self, loading: bool):
        """设置加载状态"""
        self.login_btn.setLoading(loading)
        # 不禁用segment，允许用户随时切换登录方式来中断当前登录
        # self.segment.setEnabled(not loading)
    
    def _show_error(self, message: str):
        """显示错误消息"""
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: #e74c3c;")
    
    def reject(self):
        """取消时停止登录线程"""
        if self.login_worker and self.login_worker.isRunning():
            self.login_worker.stop()
            self.login_worker.blockSignals(True)
            self.login_worker.wait(3000)
        
        if hasattr(self, 'code_worker') and self.code_worker and self.code_worker.isRunning():
            self.code_worker.blockSignals(True)
            self.code_worker.wait(2000)
        
        if self.countdown_timer:
            self.countdown_timer.stop()
        
        super().reject()
