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
import html

from PySide6.QtCore import Qt, Signal, QThread, QSize, QTimer, QRect
from PySide6.QtGui import QImage, QPixmap, QFont, QPainter, QPainterPath, QColor

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
from core.homework_count_manager import HomeworkCountManager
from ui import palette
from ui.screen_metrics import apply_page_margins
from ui.state_views import EmptyStateView, LoadingView
from ui.worker_lifecycle import retire_worker


def _rounded_pixmap(pixmap: QPixmap, radius: int = 8) -> QPixmap:
    """封面裁圆角，避免方形硬边贴在圆角卡片上"""
    if pixmap.isNull():
        return pixmap
    out = QPixmap(pixmap.size())
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, pixmap.width(), pixmap.height(), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return out


def _placeholder_pixmap(title: str, size: int = 80) -> QPixmap:
    """无封面或封面加载失败时的占位：柔和底色 + 课程首字"""
    base = QPixmap(size, size)
    base.fill(QColor(palette.color('card_border')))
    painter = QPainter(base)
    painter.setRenderHint(QPainter.Antialiasing)
    font = painter.font()
    font.setPointSize(22)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(palette.color('text_muted')))
    stripped = (title or '').strip()
    painter.drawText(base.rect(), Qt.AlignCenter, stripped[0] if stripped else '?')
    painter.end()
    return base

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


def _remove_queued_image_worker(worker) -> bool:
    """从尚未启动的全局队列移除 worker，避免队列持有已删除卡片的回调。"""
    with _cache_lock:
        for index, (queued_worker, _callback) in enumerate(_image_load_queue):
            if queued_worker is worker:
                _image_load_queue.pop(index)
                return True
    return False

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

            from core.common import AppConstants
            import requests
            headers = {
                'User-Agent': AppConstants.DEFAULT_HEADERS['User-Agent'],
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
        name = self.course_info.get('name', '') or self.course_info.get('course_name', '未知课程')
        self.image_label = QLabel(self)
        self.image_label.setFixedSize(80, 80)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: transparent;")
        # 无封面时先用课程首字占位，避免出现空洞的灰块
        self.image_label.setPixmap(_placeholder_pixmap(name))
        main_layout.addWidget(self.image_label)

        # 右侧：文字信息
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(3)

        self.name_label = StrongBodyLabel(name, self)
        self.name_label.setWordWrap(True)
        text_layout.addWidget(self.name_label)

        teacher = self.course_info.get('teacher', '未知教师')
        self.teacher_label = CaptionLabel(f"教师: {teacher}", self)
        self.teacher_label.setStyleSheet(palette.text_style('text_muted'))
        text_layout.addWidget(self.teacher_label)

        text_layout.addStretch()

        # 底部信息行：状态 · 作业数 · 进度（都是解析阶段已拿到的数据，之前没展示）
        meta_layout = QHBoxLayout()
        meta_layout.setSpacing(10)

        status = self.course_info.get('status', '进行中')
        is_open = status in ['进行中', 'active']
        self.status_label = CaptionLabel("进行中" if is_open else "已结课", self)
        self.status_label.setStyleSheet(
            f"color: {palette.color('success' if is_open else 'neutral')}; font-weight: 500;")
        meta_layout.addWidget(self.status_label)

        count = int(self.course_info.get('homework_count', 0) or 0)
        self.count_label = CaptionLabel(f"作业 {count}" if count else "作业数未同步", self)
        self.count_label.setStyleSheet(palette.text_style('text_muted'))
        meta_layout.addWidget(self.count_label)

        progress = str(self.course_info.get('progress_percent', '') or '').strip()
        self.progress_label = CaptionLabel(f"进度 {progress}" if progress and '无' not in progress else "",
                                           self)
        self.progress_label.setStyleSheet(palette.text_style('text_muted'))
        meta_layout.addWidget(self.progress_label)

        meta_layout.addStretch()
        text_layout.addLayout(meta_layout)

        main_layout.addLayout(text_layout, 1)

    def set_homework_count(self, count: int):
        """回填本地缓存的作业数量（不额外发请求）"""
        self.count_label.setText(f"作业 {count}" if count else "作业数未同步")
    
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
        if not image or image.isNull():
            return
        pixmap = QPixmap.fromImage(image)
        side = min(pixmap.width(), pixmap.height())
        if side > 0 and (pixmap.width() != side or pixmap.height() != side):
            # 先居中裁成正方形，避免 KeepAspectRatioByExpanding 的随机裁边
            x = (pixmap.width() - side) // 2
            y = (pixmap.height() - side) // 2
            pixmap = pixmap.copy(QRect(x, y, side, side))
        self.image_label.setPixmap(
            _rounded_pixmap(pixmap.scaled(80, 80, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)))
    
    def _disconnect_worker(self):
        """移出未启动的排队项，并断开已启动线程的卡片回调。"""
        worker, self.image_worker = self.image_worker, None
        if worker is None:
            return
        if _remove_queued_image_worker(worker):
            _active_image_workers.discard(worker)
            worker.deleteLater()
            return
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                worker.image_loaded.disconnect(self._on_image_loaded)
            except (RuntimeError, TypeError, ValueError):
                pass
    
    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
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
        escaped_keyword = html.escape(str(keyword))
        pattern = re.compile(re.escape(escaped_keyword), re.IGNORECASE)
        escaped_text = html.escape(str(text))
        highlighted = pattern.sub(
            lambda m: f'<span style="background-color: #fff3cd; color: #856404; font-weight: bold;">{m.group()}</span>',
            escaped_text
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
        self.filtered_courses = []
        self.card_widgets = [] # 存储所有卡片实例
        self.login_manager = None
        self.load_worker = None
        # 作业数量只读本地缓存（由作业页回写），不在课程列表发请求
        self.count_manager = HomeworkCountManager()
        # 加载代号：每次发起加载递增，用于丢弃上一轮线程的迟到结果
        self._load_generation = 0
        
        self._init_ui()
    
    def resizeEvent(self, event):
        """窄屏收紧左右留白，把宽度让给内容"""
        super().resizeEvent(event)
        apply_page_margins(self, 20, 20)

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
        
        # 加载态
        self.loading_container = LoadingView("正在加载课程...", self, top_spacing=100)
        self.loading_label = self.loading_container.label
        parent_layout.addWidget(self.loading_container, 1)
        self.loading_container.hide()

        # 空状态（作为滚动区域的替代内容）
        self.empty_container = EmptyStateView("暂无课程数据，请先登录",
                                              icon=FIF.BOOK_SHELF, action_text="点击登录",
                                              parent=self, top_spacing=100)
        self.empty_container.action_clicked.connect(lambda: self.login_required.emit())
        parent_layout.addWidget(self.empty_container, 1)
        self.empty_container.hide()  # 默认隐藏
    
    def _create_footer(self, parent_layout):
        """创建底部统计"""
        self.stats_label = CaptionLabel("", self)
        self.stats_label.setStyleSheet("color: #888888;")
        parent_layout.addWidget(self.stats_label)
    
    # ==================== 数据操作 ====================
    
    def _cleanup_workers(self):
        """退役上一轮加载线程

        课程列表会被多处重复触发（登录成功、下拉刷新、Ctrl+R）。
        若直接覆盖 load_worker，旧线程仍会 emit 结果，
        造成列表重复渲染、加载态被提前关闭。

        线程退役统一委托给 ui.worker_lifecycle.retire_worker（项目共享工具）：
        它断开全部信号、请求协作式停止，并在线程结束后安全销毁。
        这里只负责清空引用；丢弃过期结果另由 _load_generation 负责。
        """
        worker = getattr(self, 'load_worker', None)
        if worker is None:
            return
        try:
            retire_worker(worker)
        except Exception as e:
            app_logger.debug(f"退役课程加载线程失败: {e}")
        self.load_worker = None

    def _is_stale(self, gen: int) -> bool:
        """该代号的结果是否已过期（期间又发起了新的加载）"""
        return gen != self._load_generation

    def load_courses(self, login_manager, force_refresh=False):
        """加载课程列表"""
        self.login_manager = login_manager
        self._cleanup_workers()

        self._load_generation += 1
        gen = self._load_generation
        
        # 显示加载状态
        self._set_loading(True)
        
        # 启动加载线程
        self.load_worker = CourseLoadWorker(login_manager, force_refresh)
        worker = self.load_worker
        worker.courses_loaded.connect(
            lambda courses, g=gen: self._on_courses_loaded(courses, g))
        worker.error_occurred.connect(
            lambda msg, g=gen: self._on_load_error(msg, g))
        worker.finished.connect(lambda g=gen, w=worker: self._on_load_finished(g, w))
        worker.start()

    def _on_load_finished(self, gen: int, worker):
        """加载线程结束"""
        if not self._is_stale(gen):
            self._set_loading(False)
            if self.load_worker is worker:
                self.load_worker = None
        worker.deleteLater()
    
    def _on_courses_loaded(self, courses: list, gen: int = None):
        """课程加载完成"""
        if gen is not None and self._is_stale(gen):
            app_logger.info("忽略过期的课程加载结果")
            return
        self.courses = courses
        # 作业数量从本地缓存补齐（由作业页加载后回写），不发额外请求
        for course in self.courses:
            cached = self.count_manager.peek_cached_count(course.get('id'))
            if cached:
                course['homework_count'] = cached
        self.filtered_courses = courses.copy() # 初始化过滤列表
        
        # 初始筛选并显示
        self._filter_courses()
        
        app_logger.info(f"加载了 {len(courses)} 门课程")
    
    def _on_load_error(self, error_msg: str, gen: int = None):
        """加载错误"""
        if gen is not None and self._is_stale(gen):
            return
        # 如果是登录过期，提示重新登录
        if '登录' in error_msg and ('过期' in error_msg or '失效' in error_msg or '未登录' in error_msg):
            self.empty_container.set_message("登录已失效，请重新登录", show_action=True)
            self._show_empty_state()
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

        if not self.courses:
            self.empty_container.set_message("课程加载失败，请重试", show_action=False)
            self._show_empty_state()
        
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
            name = str(course.get('name') or '').lower()
            teacher = str(course.get('teacher') or '').lower()
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
            self.empty_container.set_message("没有找到匹配的课程", show_action=False)
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
            if self.loading_container.isHidden():
                self._content_before_loading = (
                    'scroll' if not self.scroll_area.isHidden() else 'empty'
                )
            self.scroll_area.hide()
            self.empty_container.hide()
            self.loading_container.show()
        else:
            self.loading_container.hide()
            if self.scroll_area.isHidden() and self.empty_container.isHidden():
                if getattr(self, '_content_before_loading', 'empty') == 'scroll' and self.filtered_courses:
                    self.scroll_area.show()
                else:
                    self.empty_container.show()
    
    def clear_data(self):
        """清空数据"""
        self._cleanup_workers()
        self._load_generation += 1
        if getattr(self, '_batch_timer', None):
            self._batch_timer.stop()
            self._batch_timer = None
        self.courses = []
        self.filtered_courses = []
        self._clear_content()
        
        # 显示登录提示
        self.empty_container.set_message("暂无课程数据，请先登录", show_action=True)
        self._show_empty_state()
        self._set_loading(False)
        
        self.stats_label.setText("")
    
    def _show_empty_state(self):
        """显示空状态"""
        self.scroll_area.hide()
        self.empty_container.show()
    
    def _hide_empty_state(self):
        """隐藏空状态"""
        self.empty_container.hide()
        self.scroll_area.show()
