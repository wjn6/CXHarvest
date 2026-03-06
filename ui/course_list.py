#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
课程列表页面 - Fluent Design 重构版
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QScrollArea, QFrame, QSizePolicy
)
import threading

from PySide6.QtCore import Qt, Signal, QThread, QSize, QTimer
from PySide6.QtGui import QImage, QPixmap, QFont

from qfluentwidgets import (
    CardWidget, SimpleCardWidget, ElevatedCardWidget,
    BodyLabel, SubtitleLabel, TitleLabel, CaptionLabel, StrongBodyLabel,
    PrimaryPushButton, PushButton, TransparentPushButton, ToolButton,
    SearchLineEdit, ComboBox, InfoBar, InfoBarPosition,
    FlowLayout, SmoothScrollArea, IndeterminateProgressBar
)
from qfluentwidgets import FluentIcon as FIF

from core.enterprise_logger import app_logger
from core.course_manager import CourseManager

# 全局图片缓存（限制大小防止内存溢出）
IMAGE_CACHE = {}
IMAGE_CACHE_MAX_SIZE = 100  # 最大缓存100张图片

# 图片加载并发控制
_image_load_queue = []  # 等待加载的图片队列
_active_image_count = 0  # 当前正在加载的图片数
_max_concurrent_images = 5  # 最大并发加载数

# 线程安全锁，保护 IMAGE_CACHE / _image_load_queue / _active_image_count
_cache_lock = threading.Lock()

def _trim_image_cache():
    """裁剪图片缓存"""
    if len(IMAGE_CACHE) > IMAGE_CACHE_MAX_SIZE:
        # 删除一半旧缓存
        keys_to_remove = list(IMAGE_CACHE.keys())[:len(IMAGE_CACHE) // 2]
        for key in keys_to_remove:
            del IMAGE_CACHE[key]

def _process_image_queue():
    """处理图片加载队列"""
    global _active_image_count
    with _cache_lock:
        while _image_load_queue and _active_image_count < _max_concurrent_images:
            worker, callback = _image_load_queue.pop(0)
            worker.image_loaded.connect(callback)
            worker.finished.connect(_on_image_worker_finished)
            _active_image_count += 1
            worker.start()

def _on_image_worker_finished():
    """图片加载完成，处理下一个"""
    global _active_image_count
    with _cache_lock:
        _active_image_count = max(0, _active_image_count - 1)
    _process_image_queue()

class CourseLoadWorker(QThread):
    """课程数据加载线程"""
    courses_loaded = Signal(list)
    error_occurred = Signal(str)
    
    def __init__(self, login_manager, force_refresh=False):
        super().__init__()
        self.login_manager = login_manager
        self.force_refresh = force_refresh
    
    def run(self):
        try:
            manager = CourseManager(self.login_manager)
            courses = manager.get_course_list(use_cache=not self.force_refresh)
            self.courses_loaded.emit(courses)
        except Exception as e:
            self.error_occurred.emit(str(e))


# 全局保持线程引用，防止运行时被回收
_active_image_workers = set()

class ImageLoadWorker(QThread):
    """图片加载线程"""
    image_loaded = Signal(QImage, str)  # 增加url参数以便缓存
    
    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self.finished.connect(self._cleanup)
        # 将自身加入全局集合，确保运行期间不被GC
        _active_image_workers.add(self)
    
    def run(self):
        try:
            with _cache_lock:
                if self.url in IMAGE_CACHE:
                    self.image_loaded.emit(IMAGE_CACHE[self.url], self.url)
                    return

            import requests
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://chaoxing.com/'
            }
            response = requests.get(self.url, headers=headers, timeout=10)
            if response.status_code == 200 and response.content:
                image = QImage()
                if image.loadFromData(response.content):
                    with _cache_lock:
                        _trim_image_cache()
                        IMAGE_CACHE[self.url] = image
                    self.image_loaded.emit(image, self.url)
        except Exception as e:
            app_logger.debug(f"图片加载失败 {self.url}: {e}")
            
    def _cleanup(self):
        """线程结束清理"""
        if self in _active_image_workers:
            _active_image_workers.remove(self)
        self.deleteLater()


class CourseCard(ElevatedCardWidget):
    """课程卡片组件"""
    course_clicked = Signal(dict)
    
    def __init__(self, course_info: dict, parent=None):
        super().__init__(parent)
        self.course_info = course_info
        self.setFixedSize(420, 110)
        self.setCursor(Qt.PointingHandCursor)
        self.image_worker = None
        
        self._init_ui()
        self._load_image()
    
    def _init_ui(self):
        # 水平主布局：图片 + 文字
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 16, 12)
        main_layout.setSpacing(14)
        
        # 左侧：课程封面图片
        from PySide6.QtWidgets import QLabel
        self.image_label = QLabel(self)
        self.image_label.setFixedSize(80, 80)
        self.image_label.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0;
                border-radius: 6px;
            }
        """)
        self.image_label.setScaledContents(True)
        main_layout.addWidget(self.image_label)
        
        # 右侧：文字信息
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)
        
        # 课程名称
        name = self.course_info.get('name', '') or self.course_info.get('course_name', '未知课程')
        self.name_label = StrongBodyLabel(name, self)
        self.name_label.setWordWrap(True)
        text_layout.addWidget(self.name_label)
        
        # 教师信息
        teacher = self.course_info.get('teacher', '未知教师')
        self.teacher_label = CaptionLabel(f"教师: {teacher}", self)
        self.teacher_label.setStyleSheet("color: #666666;")
        text_layout.addWidget(self.teacher_label)
        
        text_layout.addStretch()
        
        # 状态标签
        status = self.course_info.get('status', '进行中')
        is_open = status in ['进行中', 'active']
        status_text = "进行中" if is_open else "已结课"
        status_color = "#27ae60" if is_open else "#95a5a6"
        self.status_label = CaptionLabel(status_text, self)
        self.status_label.setStyleSheet(f"color: {status_color}; font-weight: 500;")
        text_layout.addWidget(self.status_label, alignment=Qt.AlignRight)
        
        main_layout.addLayout(text_layout, 1)
    
    def _load_image(self):
        """异步加载课程封面图片 - 使用并发控制队列"""
        image_url = self.course_info.get('image') or self.course_info.get('cover_img')
        if not image_url:
            return

        with _cache_lock:
            cached = IMAGE_CACHE.get(image_url)
        if cached is not None:
            self._set_image(cached)
            return

        self.image_worker = ImageLoadWorker(image_url)
        with _cache_lock:
            _image_load_queue.append((self.image_worker, self._on_image_loaded))
        _process_image_queue()
    
    def _on_image_loaded(self, image: QImage, url: str):
        """图片加载完成，在主线程中将 QImage 转为 QPixmap"""
        self._set_image(image)
        
    def _set_image(self, image: QImage):
        if not image.isNull():
            pixmap = QPixmap.fromImage(image)
            scaled = pixmap.scaled(80, 80, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            self.image_label.setPixmap(scaled)
    
    def _disconnect_worker(self):
        """断开线程连接，但不强制终止线程（防止卡死）"""
        if self.image_worker:
            try:
                self.image_worker.image_loaded.disconnect(self._on_image_loaded)
            except Exception:
                pass
            self.image_worker = None
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.course_clicked.emit(self.course_info)
    
    def highlight_keyword(self, keyword: str):
        """高亮显示搜索关键词"""
        if not keyword:
            return
        
        # 高亮课程名称
        name = self.course_info.get('name', '') or self.course_info.get('course_name', '未知课程')
        highlighted_name = self._highlight_text(name, keyword)
        self.name_label.setText(highlighted_name)
        
        # 高亮教师名称
        teacher = self.course_info.get('teacher', '未知教师')
        highlighted_teacher = self._highlight_text(f"教师: {teacher}", keyword)
        self.teacher_label.setText(highlighted_teacher)
    
    def _highlight_text(self, text: str, keyword: str) -> str:
        """在文本中高亮关键词"""
        import re
        if not keyword:
            return text
        # 不区分大小写的替换
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        highlighted = pattern.sub(
            lambda m: f'<span style="background-color: #fff3cd; color: #856404; font-weight: bold;">{m.group()}</span>',
            text
        )
        return highlighted
    
    def deleteLater(self):
        """重写deleteLater"""
        self._disconnect_worker()
        super().deleteLater()


class CourseListFluent(QWidget):
    """课程列表页面"""
    course_selected = Signal(dict)
    login_required = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CourseListInterface")
        
        self.courses = []
        self.card_widgets = [] # 存储所有卡片实例
        self.login_manager = None
        self.load_worker = None
        
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 20, 36, 20)
        layout.setSpacing(16)
        
        # 标题栏
        self._create_header(layout)
        
        # 工具栏（搜索、筛选）
        self._create_toolbar(layout)
        
        # 课程卡片区域
        self._create_content_area(layout)
        
        # 底部统计
        self._create_footer(layout)
        
        # 初始显示空状态
        self._show_empty_state()
    
    def _create_header(self, parent_layout):
        """创建标题栏"""
        header_layout = QHBoxLayout()
        
        self.title_label = TitleLabel("课程列表", self)
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        
        # 刷新按钮
        self.refresh_btn = PushButton("刷新", self, FIF.SYNC)
        self.refresh_btn.clicked.connect(self._on_refresh_clicked)
        header_layout.addWidget(self.refresh_btn)
        
        parent_layout.addLayout(header_layout)
    
    def _create_toolbar(self, parent_layout):
        """创建工具栏"""
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(12)
        
        # 搜索框
        self.search_edit = SearchLineEdit(self)
        self.search_edit.setPlaceholderText("搜索课程名称或教师...")
        self.search_edit.setFixedWidth(300)
        self._search_debounce_timer = QTimer(self)
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.setInterval(300)
        self._search_debounce_timer.timeout.connect(self._filter_courses)
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        toolbar_layout.addWidget(self.search_edit)
        
        # 状态筛选
        self.status_combo = ComboBox(self)
        self.status_combo.addItems(["全部课程", "进行中", "已结课"])
        self.status_combo.setFixedWidth(120)
        self.status_combo.currentIndexChanged.connect(self._filter_courses)
        toolbar_layout.addWidget(self.status_combo)
        
        toolbar_layout.addStretch()
        
        parent_layout.addLayout(toolbar_layout)
    
    def _create_content_area(self, parent_layout):
        """创建内容区域"""
        # 滚动区域
        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            SmoothScrollArea {
                background: transparent; 
                border: none;
            }
            QScrollBar:vertical {
                width: 6px;
                background: transparent;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(0, 0, 0, 0.3);
                border-radius: 3px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(0, 0, 0, 0.5);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)
        
        # 内容容器
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        self.content_layout = FlowLayout(self.content_widget, needAni=True)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setHorizontalSpacing(16)
        self.content_layout.setVerticalSpacing(16)
        
        self.scroll_area.setWidget(self.content_widget)
        parent_layout.addWidget(self.scroll_area, 1)
        
        # 加载状态容器（居中显示）
        self.loading_container = QFrame(self)
        self.loading_container.setStyleSheet("background: transparent;")
        loading_layout = QVBoxLayout(self.loading_container)
        loading_layout.setContentsMargins(0, 100, 0, 0)
        loading_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        
        # 使用进度条替代加载圈
        self.loading_bar = IndeterminateProgressBar(self.loading_container)
        self.loading_bar.setFixedWidth(200)
        
        self.loading_label = CaptionLabel("正在加载课程...", self.loading_container)
        self.loading_label.setStyleSheet("color: #888888;")
        
        loading_layout.addWidget(self.loading_bar, alignment=Qt.AlignCenter)
        loading_layout.addSpacing(12)
        loading_layout.addWidget(self.loading_label, alignment=Qt.AlignCenter)
        loading_layout.addStretch()
        
        parent_layout.addWidget(self.loading_container, 1)
        self.loading_container.hide()
        
        # 空状态提示（作为滚动区域的替代内容）
        self.empty_container = QFrame(self)
        self.empty_container.setStyleSheet("background: transparent;")
        empty_layout = QVBoxLayout(self.empty_container)
        empty_layout.setContentsMargins(0, 100, 0, 0)  # 顶部留白
        empty_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        
        self.empty_label = BodyLabel("暂无课程数据，请先登录", self.empty_container)
        self.empty_label.setAlignment(Qt.AlignCenter)
        
        self.login_hint_btn = PrimaryPushButton("点击登录", self.empty_container)
        self.login_hint_btn.setFixedWidth(120)
        self.login_hint_btn.clicked.connect(lambda: self.login_required.emit())
        
        empty_layout.addWidget(self.empty_label, alignment=Qt.AlignCenter)
        empty_layout.addSpacing(16)
        empty_layout.addWidget(self.login_hint_btn, alignment=Qt.AlignCenter)
        empty_layout.addStretch()
        
        # 将空状态容器添加到主布局
        parent_layout.addWidget(self.empty_container, 1)
        self.empty_container.hide()  # 默认隐藏
    
    def _create_footer(self, parent_layout):
        """创建底部统计"""
        self.stats_label = CaptionLabel("", self)
        self.stats_label.setStyleSheet("color: #888888;")
        parent_layout.addWidget(self.stats_label)
    
    # ==================== 数据操作 ====================
    
    def load_courses(self, login_manager, force_refresh=False):
        """加载课程列表"""
        self.login_manager = login_manager
        
        # 显示加载状态
        self._set_loading(True)
        
        # 启动加载线程
        self.load_worker = CourseLoadWorker(login_manager, force_refresh)
        self.load_worker.courses_loaded.connect(self._on_courses_loaded)
        self.load_worker.error_occurred.connect(self._on_load_error)
        self.load_worker.finished.connect(lambda: self._set_loading(False))
        self.load_worker.start()
    
    def _on_courses_loaded(self, courses: list):
        """课程加载完成"""
        self.courses = courses
        self.filtered_courses = courses.copy() # 初始化过滤列表
        
        # 初始筛选并显示
        self._filter_courses()
        
        app_logger.info(f"加载了 {len(courses)} 门课程")
    
    def _on_load_error(self, error_msg: str):
        """加载错误"""
        # 如果是登录过期，提示重新登录
        if '登录' in error_msg and ('过期' in error_msg or '失效' in error_msg or '未登录' in error_msg):
            InfoBar.warning(
                title="登录已失效",
                content="请重新登录后再试",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self.window()
            )
            self.login_required.emit()
            return
        
        InfoBar.error(
            title="加载失败",
            content=error_msg,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self.window()
        )
        app_logger.error(f"课程加载失败: {error_msg}")
    
    def _clear_content(self):
        """清空内容区域"""
        # 删除所有子控件
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if hasattr(item, 'widget') and item.widget():
                # 立即隐藏并安全删除
                item.widget().hide()
                item.widget().deleteLater()
            elif isinstance(item, QWidget):
                item.hide()
                item.deleteLater()
    
    def _on_search_text_changed(self):
        """搜索文本变化时重启防抖计时器"""
        self._search_debounce_timer.start()

    def _filter_courses(self):
        """筛选课程"""
        keyword = self.search_edit.text().strip().lower()
        status_filter = self.status_combo.currentIndex()  # 0=全部, 1=进行中, 2=已结课
        
        self.filtered_courses = []
        for course in self.courses:
            # 关键词匹配
            name = course.get('name', '').lower()
            teacher = course.get('teacher', '').lower()
            if keyword and keyword not in name and keyword not in teacher:
                continue
            
            # 状态匹配
            status = course.get('status', '进行中')
            is_open = status in ['进行中', 'active']
            
            if status_filter == 1 and not is_open:
                continue
            elif status_filter == 2 and is_open:
                continue
                
            self.filtered_courses.append(course)
        
        self._display_courses()
        self._update_stats()
        
    def _display_courses(self):
        """显示课程卡片 - 分批渲染避免卡死"""
        # 停止之前的分批渲染
        if hasattr(self, '_batch_timer') and self._batch_timer:
            self._batch_timer.stop()
            self._batch_timer = None
        
        # 重建整个内容容器，彻底解决布局错位问题
        if hasattr(self, 'content_widget') and self.content_widget:
            self.scroll_area.takeWidget()
            self.content_widget.deleteLater()
            self.content_widget = None
            
        # 创建新的容器
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        
        # 创建新的流式布局
        # 关闭 needAni (动画) 以解决卡片重叠/错位问题，稳定性优先
        self.content_layout = FlowLayout(self.content_widget, needAni=False)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setHorizontalSpacing(16)
        self.content_layout.setVerticalSpacing(16)
        
        # 设置给滚动区域
        self.scroll_area.setWidget(self.content_widget)
        
        if not self.filtered_courses:
            self.empty_label.setText("没有找到匹配的课程")
            self.login_hint_btn.hide()
            self._show_empty_state()
            return
            
        self._hide_empty_state()
        
        # 分批渲染参数
        self._batch_index = 0
        self._batch_size = 10  # 每批渲染10个卡片
        self._batch_keyword = self.search_edit.text().strip()
        
        # 启动分批渲染
        self._render_next_batch()
    
    def _render_next_batch(self):
        """渲染下一批课程卡片"""
        if not hasattr(self, '_batch_index'):
            return
            
        start = self._batch_index
        end = min(start + self._batch_size, len(self.filtered_courses))
        
        # 渲染当前批次
        for i in range(start, end):
            course = self.filtered_courses[i]
            card = CourseCard(course, self.content_widget)
            card.course_clicked.connect(self._on_card_clicked)
            if self._batch_keyword:
                card.highlight_keyword(self._batch_keyword)
            self.content_layout.addWidget(card)
        
        self._batch_index = end
        
        # 如果还有更多，延迟渲染下一批
        if end < len(self.filtered_courses):
            self._batch_timer = QTimer(self)
            self._batch_timer.setSingleShot(True)
            self._batch_timer.timeout.connect(self._render_next_batch)
            self._batch_timer.start(10)  # 10ms后渲染下一批
        else:
            # 渲染完成，更新布局
            self.content_widget.adjustSize()
            self._batch_timer = None
    
    def _update_stats(self):
        """更新统计信息"""
        total = len(self.courses)
        shown = len(self.filtered_courses)
            
        # 统计进行中
        active = sum(1 for c in self.courses if c.get('status', '进行中') in ['进行中', 'active'])
        
        if total == shown:
            self.stats_label.setText(f"共 {total} 门课程 | {active} 门进行中 | {total - active} 门已结课")
        else:
            self.stats_label.setText(f"显示 {shown}/{total} 门课程")
    
    def _on_card_clicked(self, course_info: dict):
        """卡片点击处理"""
        self.course_selected.emit(course_info)
    
    def _on_refresh_clicked(self):
        """刷新按钮点击"""
        if self.login_manager:
            self.load_courses(self.login_manager, force_refresh=True)
        else:
            self.login_required.emit()
    
    def _set_loading(self, loading: bool):
        """设置加载状态"""
        self.refresh_btn.setEnabled(not loading)
        self.search_edit.setEnabled(not loading)
        self.status_combo.setEnabled(not loading)
        
        if loading:
            self.scroll_area.hide()
            self.empty_container.hide()
            self.loading_container.show()
        else:
            self.loading_container.hide()
            self.scroll_area.show()
    
    def clear_data(self):
        """清空数据"""
        self.courses = []
        self._clear_content()
        
        # 显示登录提示
        self.empty_label.setText("暂无课程数据，请先登录")
        self.login_hint_btn.show()
        self._show_empty_state()
        
        self.stats_label.setText("")
    
    def _show_empty_state(self):
        """显示空状态"""
        self.scroll_area.hide()
        self.empty_container.show()
    
    def _hide_empty_state(self):
        """隐藏空状态"""
        self.empty_container.hide()
        self.scroll_area.show()
