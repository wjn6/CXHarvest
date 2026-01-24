#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主窗口 - Fluent Design 重构版
层级导航：课程列表 → 作业列表 → 题目列表
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QLabel
from PySide6.QtCore import Qt, Signal, QTimer, QThread
from PySide6.QtGui import QFont, QKeySequence, QShortcut

from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, 
    PrimaryPushButton, PushButton, TransparentPushButton,
    BodyLabel, SubtitleLabel, TitleLabel, CaptionLabel,
    InfoBar, InfoBarPosition, StateToolTip,
    BreadcrumbBar, MessageBoxBase, HyperlinkButton,
    setTheme, Theme
)
from qfluentwidgets import FluentIcon as FIF
import webbrowser

from core.enterprise_logger import app_logger
from core.version import __version__, APP_NAME, GITHUB_URL


class MainWindowFluent(FluentWindow):
    """主窗口 - Fluent Design 版本"""
    
    def __init__(self):
        super().__init__()
        
        # 状态变量
        self.current_course = None
        self.current_homework = None
        self.login_manager = None
        self.user_info = None
        
        # 初始化界面
        self._init_window()
        self._init_interfaces()
        self._init_navigation()
        self._connect_signals()
        self._init_shortcuts()
        self._load_theme_from_config()
        
        app_logger.info("主窗口初始化完成")
    
    def _init_window(self):
        """初始化窗口属性"""
        self.setWindowTitle(f"{APP_NAME} v{__version__}")
        self.resize(1000, 700)  # 默认使用最小尺寸
        self.setMinimumSize(1000, 700)
        
        # 居中显示
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        self.move((screen.width() - 1000) // 2, (screen.height() - 700) // 2)
    
    def _init_interfaces(self):
        """初始化各个页面"""
        # 延迟导入避免循环依赖
        from ui.course_list import CourseListFluent
        from ui.homework_list import HomeworkListFluent
        from ui.question_list import QuestionListFluent
        from ui.login_dialog import LoginDialogFluent
        
        # 创建页面
        self.course_list = CourseListFluent(self)
        self.homework_list = HomeworkListFluent(self)
        self.question_list = QuestionListFluent(self)
        
        # 设置对象名称（用于导航识别）
        self.course_list.setObjectName("CourseListInterface")
        self.homework_list.setObjectName("HomeworkListInterface")
        self.question_list.setObjectName("QuestionListInterface")
        
        # 保存登录对话框类引用
        self._login_dialog_class = LoginDialogFluent
    
    def _init_navigation(self):
        """初始化导航栏"""
        # 添加主要导航项
        self.addSubInterface(
            self.course_list,
            FIF.BOOK_SHELF,
            "课程列表"
        )
        self.addSubInterface(
            self.homework_list,
            FIF.DOCUMENT,
            "作业列表"
        )
        self.addSubInterface(
            self.question_list,
            FIF.EDIT,
            "题目列表"
        )
        
        # 底部导航项
        self.navigationInterface.addSeparator()
        
        # 主题切换按钮
        self.navigationInterface.addItem(
            routeKey="theme",
            icon=FIF.CONSTRACT,
            text="深色模式",
            onClick=self._toggle_theme,
            selectable=False,
            position=NavigationItemPosition.BOTTOM
        )
        
        # 添加登录/用户按钮（动态显示）
        self.navigationInterface.addItem(
            routeKey="login",
            icon=FIF.PEOPLE,
            text="登录",
            onClick=self._on_login_clicked,
            selectable=False,
            position=NavigationItemPosition.BOTTOM
        )
        
        # 关于按钮
        self.navigationInterface.addItem(
            routeKey="about",
            icon=FIF.INFO,
            text="关于",
            onClick=self._show_about_dialog,
            selectable=False,
            position=NavigationItemPosition.BOTTOM
        )
    
    def _connect_signals(self):
        """连接信号"""
        # 课程列表信号
        self.course_list.course_selected.connect(self._on_course_selected)
        self.course_list.login_required.connect(self.show_login_dialog)
        
        # 作业列表信号
        self.homework_list.homework_selected.connect(self._on_homework_selected)
        self.homework_list.back_requested.connect(self._back_to_courses)
        self.homework_list.login_required.connect(self.show_login_dialog)
        
        # 题目列表信号
        self.question_list.back_requested.connect(self._back_to_homework)
        self.question_list.export_requested.connect(self._on_export_requested)
        self.question_list.login_required.connect(self.show_login_dialog)
    
    # ==================== 登录相关 ====================
    
    def _on_login_clicked(self):
        """登录按钮点击"""
        if self.user_info:
            # 已登录，显示用户菜单或退出
            self._show_user_menu()
        else:
            self.show_login_dialog()
    
    def show_login_dialog(self):
        """显示登录对话框"""
        dialog = self._login_dialog_class(self)
        dialog.login_success.connect(self._on_login_success)
        dialog.exec()
    
    def _on_login_success(self, user_info: dict):
        """登录成功处理"""
        self.user_info = user_info
        self.login_manager = user_info.get('login_manager')
        
        # 更新导航栏显示
        username = user_info.get('name', '用户')
        self.navigationInterface.widget("login").setText(username)
        
        # 显示成功消息
        InfoBar.success(
            title="登录成功",
            content=f"欢迎回来，{username}，正在加载课程...",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self
        )
        
        # 确保切换到课程列表页面
        self.switchTo(self.course_list)
        
        # 延迟一小段时间后加载课程（强制刷新，不使用缓存）
        QTimer.singleShot(300, lambda: self.course_list.load_courses(self.login_manager, force_refresh=True))
        
        app_logger.info(f"用户登录成功: {username}")
    
    def _show_user_menu(self):
        """显示用户菜单"""
        from PySide6.QtWidgets import QMenu
        from qfluentwidgets import RoundMenu, Action
        
        menu = RoundMenu(parent=self)
        menu.addAction(Action(FIF.PEOPLE, f"当前用户: {self.user_info.get('name', '未知')}", triggered=lambda: None))
        menu.addSeparator()
        menu.addAction(Action(FIF.SYNC, "刷新课程", triggered=self._refresh_courses))
        menu.addAction(Action(FIF.POWER_BUTTON, "退出登录", triggered=self._logout))
        
        # 获取按钮位置
        btn = self.navigationInterface.widget("login")
        pos = btn.mapToGlobal(btn.rect().topRight())
        menu.exec(pos)
    
    def _logout(self):
        """退出登录"""
        self.user_info = None
        self.login_manager = None
        self.current_course = None
        self.current_homework = None
        
        # 清空各页面数据
        self.course_list.clear_data()
        self.homework_list.clear_data()
        self.question_list.clear_data()
        
        # 恢复导航栏
        self.navigationInterface.widget("login").setText("登录")
        
        # 切换到课程列表
        self.switchTo(self.course_list)
        
        InfoBar.info(
            title="已退出登录",
            content="请重新登录以使用完整功能",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000,
            parent=self
        )
        
        app_logger.info("用户已退出登录")
    
    def _refresh_courses(self):
        """刷新课程列表"""
        if self.login_manager:
            self.course_list.load_courses(self.login_manager, force_refresh=True)
    
    # ==================== 导航相关 ====================
    
    def _on_course_selected(self, course_info: dict):
        """课程选择处理"""
        self.current_course = course_info
        
        # 加载作业列表
        self.homework_list.load_homework(course_info, self.login_manager)
        
        # 切换到作业列表页面
        self.switchTo(self.homework_list)
        
        app_logger.info(f"选择课程: {course_info.get('name', '未知')}")
    
    def _on_homework_selected(self, homework_info: dict):
        """作业选择处理"""
        self.current_homework = homework_info
        
        # 加载题目列表
        self.question_list.load_questions(homework_info, self.login_manager)
        
        # 切换到题目列表页面
        self.switchTo(self.question_list)
        
        app_logger.info(f"选择作业: {homework_info.get('title', '未知')}")
    
    def _back_to_courses(self):
        """返回课程列表"""
        self.current_homework = None
        self.switchTo(self.course_list)
    
    def _back_to_homework(self):
        """返回作业列表"""
        self.switchTo(self.homework_list)
    
    # ==================== 导出相关 ====================
    
    def _on_export_requested(self, questions: list):
        """导出请求处理"""
        from ui.export_dialog import ExportDialogFluent
        
        dialog = ExportDialogFluent(questions, self)
        dialog.exec()
    
    # ==================== 工具方法 ====================
    
    def show_message(self, title: str, content: str, msg_type: str = "info"):
        """显示消息通知"""
        info_bar_map = {
            "info": InfoBar.info,
            "success": InfoBar.success,
            "warning": InfoBar.warning,
            "error": InfoBar.error
        }
        
        func = info_bar_map.get(msg_type, InfoBar.info)
        func(
            title=title,
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000,
            parent=self
        )
    
    def show_state_tooltip(self, title: str, content: str):
        """显示状态提示（加载中）"""
        self.state_tooltip = StateToolTip(title, content, self)
        self.state_tooltip.move(self.width() - 300, 50)
        self.state_tooltip.show()
    
    def hide_state_tooltip(self, success: bool = True):
        """隐藏状态提示"""
        if hasattr(self, 'state_tooltip') and self.state_tooltip:
            self.state_tooltip.setContent("操作完成" if success else "操作失败")
            self.state_tooltip.setState(success)
            self.state_tooltip = None
    
    # ==================== 快捷键相关 ====================
    
    def _init_shortcuts(self):
        """初始化快捷键"""
        # Ctrl+R: 刷新当前页面
        self.shortcut_refresh = QShortcut(QKeySequence("Ctrl+R"), self)
        self.shortcut_refresh.activated.connect(self._on_shortcut_refresh)
        
        # Esc: 返回上一级
        self.shortcut_back = QShortcut(QKeySequence("Escape"), self)
        self.shortcut_back.activated.connect(self._handle_back)
        
        # Ctrl+E: 导出（在题目列表页面时）
        self.shortcut_export = QShortcut(QKeySequence("Ctrl+E"), self)
        self.shortcut_export.activated.connect(self._on_shortcut_export)
    
    def _on_shortcut_refresh(self):
        """快捷键: 刷新当前页面"""
        current_widget = self.stackedWidget.currentWidget()
        
        if current_widget == self.course_list and self.login_manager:
            self.course_list.load_courses(self.login_manager, force_refresh=True)
            self.show_message("刷新", "正在刷新课程列表...", "info")
        elif current_widget == self.homework_list and self.current_course:
            self.homework_list.load_homework(self.current_course, self.login_manager)
            self.show_message("刷新", "正在刷新作业列表...", "info")
        elif current_widget == self.question_list and self.current_homework:
            self.question_list.load_questions(self.current_homework, self.login_manager)
            self.show_message("刷新", "正在重新解析题目...", "info")
    
    def _handle_back(self):
        """快捷键: 返回上一级"""
        current_widget = self.stackedWidget.currentWidget()
        
        if current_widget == self.question_list:
            self._back_to_homework()
        elif current_widget == self.homework_list:
            self._back_to_courses()
    
    def _on_shortcut_export(self):
        """快捷键: 导出题目"""
        current_widget = self.stackedWidget.currentWidget()
        
        if current_widget == self.question_list and self.question_list.questions:
            self.question_list._on_export_all()
    
    # ==================== 主题相关 ====================
    
    def _load_theme_from_config(self):
        """从配置加载主题设置"""
        try:
            from core.config_manager import get_app_config
            config = get_app_config()
            theme = config.ui.theme
            
            self.is_dark_theme = (theme == "dark")
            
            if self.is_dark_theme:
                setTheme(Theme.DARK)
                self.navigationInterface.widget("theme").setText("浅色模式")
            else:
                setTheme(Theme.LIGHT)
                self.navigationInterface.widget("theme").setText("深色模式")
                
            app_logger.info(f"加载主题设置: {theme}")
        except Exception as e:
            self.is_dark_theme = False
            app_logger.debug(f"加载主题设置失败: {e}")
    
    def _toggle_theme(self):
        """切换深色/浅色主题"""
        self.is_dark_theme = not self.is_dark_theme
        
        if self.is_dark_theme:
            setTheme(Theme.DARK)
            self.navigationInterface.widget("theme").setText("浅色模式")
        else:
            setTheme(Theme.LIGHT)
            self.navigationInterface.widget("theme").setText("深色模式")
        
        # 保存主题设置到配置
        self._save_theme_to_config()
        app_logger.info(f"主题切换为: {'深色' if self.is_dark_theme else '浅色'}")
    
    def _save_theme_to_config(self):
        """保存主题设置到配置文件"""
        try:
            from core.config_manager import get_config_manager
            config_manager = get_config_manager()
            config = config_manager.get_config()
            config.ui.theme = "dark" if self.is_dark_theme else "light"
            config_manager.save_config()
        except Exception as e:
            app_logger.debug(f"保存主题设置失败: {e}")
    
    def _show_about_dialog(self):
        """显示关于对话框"""
        about_dialog = AboutDialog(self)
        about_dialog.exec()


class AboutDialog(MessageBoxBase):
    """关于对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # ========== 应用信息区域 ==========
        # 标题
        title_label = TitleLabel(APP_NAME)
        title_label.setAlignment(Qt.AlignCenter)
        self.viewLayout.addWidget(title_label)
        
        # 版本号
        version_label = SubtitleLabel(f"v{__version__}")
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setStyleSheet("color: #3498db;")
        self.viewLayout.addWidget(version_label)
        
        self.viewLayout.addSpacing(12)
        
        # 描述
        desc_label = BodyLabel(
            "一款现代化的超星学习通作业题目导出桌面应用\n"
            "支持多种登录方式、多种导出格式"
        )
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setWordWrap(True)
        self.viewLayout.addWidget(desc_label)
        
        self.viewLayout.addSpacing(20)
        
        # ========== 操作按钮区域 ==========
        # 检查更新按钮
        self.check_update_btn = PushButton("检查更新", self)
        self.check_update_btn.setIcon(FIF.SYNC)
        self.check_update_btn.clicked.connect(self._check_update)
        self.viewLayout.addWidget(self.check_update_btn, alignment=Qt.AlignCenter)
        
        # 更新状态标签（初始隐藏）
        self.update_status_label = CaptionLabel("")
        self.update_status_label.setAlignment(Qt.AlignCenter)
        self.update_status_label.hide()
        self.viewLayout.addWidget(self.update_status_label)
        
        self.viewLayout.addSpacing(16)
        
        # ========== 链接区域 ==========
        # GitHub 链接
        github_btn = HyperlinkButton(
            url=GITHUB_URL,
            text="GitHub 开源地址",
            parent=self
        )
        github_btn.setIcon(FIF.GITHUB)
        self.viewLayout.addWidget(github_btn, alignment=Qt.AlignCenter)
        
        # QFluentWidgets 链接 (小字)
        qfluent_label = CaptionLabel("Powered by QFluentWidgets")
        qfluent_label.setAlignment(Qt.AlignCenter)
        qfluent_label.setStyleSheet("color: #3498db;")
        qfluent_label.setCursor(Qt.PointingHandCursor)
        qfluent_label.mousePressEvent = lambda e: __import__('webbrowser').open('https://qfluentwidgets.com/')
        self.viewLayout.addWidget(qfluent_label)
        
        self.viewLayout.addSpacing(20)
        
        # ========== 底部信息区域 ==========
        # 许可证
        license_label = CaptionLabel("开源许可: GPL-3.0")
        license_label.setAlignment(Qt.AlignCenter)
        license_label.setStyleSheet("color: #7f8c8d;")
        self.viewLayout.addWidget(license_label)
        
        # 版权与作者 (合并为一行，放大)
        footer_label = BodyLabel("Copyright © 2026 wjn6 · By 重庆彭于晏")
        footer_label.setAlignment(Qt.AlignCenter)
        footer_label.setStyleSheet("color: #7f8c8d;")
        self.viewLayout.addWidget(footer_label)
        
        # 隐藏取消按钮
        self.cancelButton.hide()
        self.yesButton.setText("知道了")
        
        # 设置宽度
        self.widget.setMinimumWidth(380)
    
    def _check_update(self):
        """检查更新（异步）"""
        from qfluentwidgets import IndeterminateProgressRing
        
        self.check_update_btn.setEnabled(False)
        self.check_update_btn.setText("检查中...")
        self.update_status_label.hide()
        
        # 启动异步检查线程
        self.update_worker = UpdateCheckWorker()
        self.update_worker.check_finished.connect(self._on_update_check_finished)
        self.update_worker.start()
    
    def _on_update_check_finished(self, result: dict):
        """更新检查完成回调"""
        self.check_update_btn.setEnabled(True)
        self.check_update_btn.setText("检查更新")
        
        if result.get("error"):
            self.update_status_label.setText(result["error"])
            self.update_status_label.setStyleSheet("color: #e74c3c;")
            self.update_status_label.show()
            return
        
        if result.get("has_update"):
            # 有新版本 - 显示详细对话框
            self.update_status_label.setText(f"发现新版本: v{result['version']}")
            self.update_status_label.setStyleSheet("color: #27ae60;")
            self.update_status_label.show()
            
            # 显示更新详情对话框
            update_dialog = UpdateInfoDialog(result, self.window())
            update_dialog.exec()
        else:
            self.update_status_label.setText("已是最新版本")
            self.update_status_label.setStyleSheet("color: #3498db;")
            self.update_status_label.show()


class UpdateCheckWorker(QThread):
    """更新检查工作线程"""
    check_finished = Signal(dict)
    
    def run(self):
        import requests
        
        try:
            api_url = "https://api.github.com/repos/wjn6/CXHarvest/releases/latest"
            resp = requests.get(api_url, timeout=15)
            
            if resp.status_code == 200:
                data = resp.json()
                latest_version = data.get("tag_name", "").lstrip("v")
                
                # 比较版本号
                has_update = self._compare_versions(latest_version, __version__) > 0
                
                # 获取下载链接
                download_url = None
                download_size = 0
                assets = data.get("assets", [])
                for asset in assets:
                    if asset.get("name", "").endswith(".zip"):
                        download_url = asset.get("browser_download_url")
                        download_size = asset.get("size", 0)
                        break
                
                self.check_finished.emit({
                    "has_update": has_update,
                    "version": latest_version,
                    "current_version": __version__,
                    "release_url": data.get("html_url", GITHUB_URL),
                    "download_url": download_url,
                    "download_size": download_size,
                    "changelog": data.get("body", "暂无更新说明"),
                    "published_at": data.get("published_at", ""),
                    "name": data.get("name", f"v{latest_version}")
                })
            elif resp.status_code == 404:
                self.check_finished.emit({"error": "暂无发布版本"})
            else:
                self.check_finished.emit({"error": "检查失败，请稍后重试"})
                
        except requests.exceptions.Timeout:
            self.check_finished.emit({"error": "请求超时，请检查网络"})
        except Exception as e:
            self.check_finished.emit({"error": f"检查失败: {str(e)}"})
    
    def _compare_versions(self, v1: str, v2: str) -> int:
        """比较版本号"""
        try:
            parts1 = [int(x) for x in v1.split(".")]
            parts2 = [int(x) for x in v2.split(".")]
            max_len = max(len(parts1), len(parts2))
            parts1.extend([0] * (max_len - len(parts1)))
            parts2.extend([0] * (max_len - len(parts2)))
            for p1, p2 in zip(parts1, parts2):
                if p1 > p2:
                    return 1
                elif p1 < p2:
                    return -1
            return 0
        except:
            return 0


class UpdateInfoDialog(MessageBoxBase):
    """更新详情对话框"""
    
    def __init__(self, update_info: dict, parent=None):
        super().__init__(parent)
        self.update_info = update_info
        
        # 标题
        title = TitleLabel(f"发现新版本 v{update_info['version']}")
        title.setAlignment(Qt.AlignCenter)
        self.viewLayout.addWidget(title)
        
        # 版本对比
        version_info = CaptionLabel(f"当前版本: v{update_info['current_version']} → 新版本: v{update_info['version']}")
        version_info.setAlignment(Qt.AlignCenter)
        version_info.setStyleSheet("color: #27ae60;")
        self.viewLayout.addWidget(version_info)
        
        # 发布时间
        if update_info.get("published_at"):
            from datetime import datetime
            try:
                pub_time = datetime.fromisoformat(update_info["published_at"].replace("Z", "+00:00"))
                time_str = pub_time.strftime("%Y-%m-%d %H:%M")
                time_label = CaptionLabel(f"发布时间: {time_str}")
                time_label.setAlignment(Qt.AlignCenter)
                time_label.setStyleSheet("color: #95a5a6;")
                self.viewLayout.addWidget(time_label)
            except:
                pass
        
        self.viewLayout.addSpacing(12)
        
        # 更新日志标题
        changelog_title = SubtitleLabel("更新日志")
        self.viewLayout.addWidget(changelog_title)
        
        # 更新日志内容（滚动区域）
        from PySide6.QtWidgets import QScrollArea, QFrame
        from qfluentwidgets import TextEdit
        
        changelog_text = TextEdit(self)
        changelog_text.setReadOnly(True)
        changelog_text.setMarkdown(update_info.get("changelog", "暂无更新说明"))
        changelog_text.setMaximumHeight(150)
        changelog_text.setStyleSheet("""
            TextEdit {
                border: 1px solid #ddd;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        self.viewLayout.addWidget(changelog_text)
        
        self.viewLayout.addSpacing(12)
        
        # 下载大小
        if update_info.get("download_size"):
            size_mb = update_info["download_size"] / (1024 * 1024)
            size_label = CaptionLabel(f"下载大小: {size_mb:.1f} MB")
            size_label.setAlignment(Qt.AlignCenter)
            self.viewLayout.addWidget(size_label)
        
        # 按钮区域
        from PySide6.QtWidgets import QHBoxLayout
        btn_layout = QHBoxLayout()
        
        # 浏览器下载按钮
        browser_btn = PushButton("浏览器下载", self)
        browser_btn.setIcon(FIF.GLOBE)
        browser_btn.clicked.connect(self._open_in_browser)
        btn_layout.addWidget(browser_btn)
        
        # 直接下载按钮（如果有下载链接）
        if update_info.get("download_url"):
            download_btn = PrimaryPushButton("下载到本地", self)
            download_btn.setIcon(FIF.DOWNLOAD)
            download_btn.clicked.connect(self._download_to_local)
            btn_layout.addWidget(download_btn)
        
        self.viewLayout.addLayout(btn_layout)
        
        # 下载进度条（初始隐藏）
        from qfluentwidgets import ProgressBar
        self.progress_bar = ProgressBar(self)
        self.progress_bar.hide()
        self.viewLayout.addWidget(self.progress_bar)
        
        self.progress_label = CaptionLabel("")
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.hide()
        self.viewLayout.addWidget(self.progress_label)
        
        # 隐藏默认按钮
        self.yesButton.setText("关闭")
        self.cancelButton.hide()
        
        self.widget.setMinimumWidth(420)
    
    def _open_in_browser(self):
        """在浏览器中打开"""
        webbrowser.open(self.update_info.get("release_url", GITHUB_URL))
    
    def _download_to_local(self):
        """下载到本地"""
        from PySide6.QtWidgets import QFileDialog
        
        # 选择保存位置
        default_name = f"超星收割机_v{self.update_info['version']}.zip"
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存更新包",
            default_name,
            "ZIP 文件 (*.zip)"
        )
        
        if not save_path:
            return
        
        # 显示进度条
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.progress_label.setText("正在下载...")
        self.progress_label.show()
        
        # 启动下载线程
        self.download_worker = DownloadWorker(
            self.update_info["download_url"],
            save_path
        )
        self.download_worker.progress_updated.connect(self._on_download_progress)
        self.download_worker.download_finished.connect(self._on_download_finished)
        self.download_worker.start()
    
    def _on_download_progress(self, percentage: int, speed: str):
        """下载进度更新"""
        self.progress_bar.setValue(percentage)
        self.progress_label.setText(f"下载中: {percentage}% ({speed})")
    
    def _on_download_finished(self, success: bool, message: str):
        """下载完成"""
        self.progress_bar.hide()
        
        if success:
            self.progress_label.setText("下载完成！")
            self.progress_label.setStyleSheet("color: #27ae60;")
            
            InfoBar.success(
                title="下载完成",
                content=message,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self.window()
            )
        else:
            self.progress_label.setText(f"下载失败: {message}")
            self.progress_label.setStyleSheet("color: #e74c3c;")


class DownloadWorker(QThread):
    """下载工作线程"""
    progress_updated = Signal(int, str)  # percentage, speed
    download_finished = Signal(bool, str)  # success, message
    
    def __init__(self, url: str, save_path: str):
        super().__init__()
        self.url = url
        self.save_path = save_path
    
    def run(self):
        import requests
        import time
        
        try:
            resp = requests.get(self.url, stream=True, timeout=30)
            total_size = int(resp.headers.get("content-length", 0))
            
            downloaded = 0
            start_time = time.time()
            
            with open(self.save_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # 计算进度和速度
                        if total_size > 0:
                            percentage = int(downloaded * 100 / total_size)
                        else:
                            percentage = 0
                        
                        elapsed = time.time() - start_time
                        if elapsed > 0:
                            speed = downloaded / elapsed
                            if speed > 1024 * 1024:
                                speed_str = f"{speed / 1024 / 1024:.1f} MB/s"
                            elif speed > 1024:
                                speed_str = f"{speed / 1024:.1f} KB/s"
                            else:
                                speed_str = f"{speed:.0f} B/s"
                        else:
                            speed_str = "计算中..."
                        
                        self.progress_updated.emit(percentage, speed_str)
            
            self.download_finished.emit(True, f"已保存到: {self.save_path}")
            
        except Exception as e:
            self.download_finished.emit(False, str(e))
