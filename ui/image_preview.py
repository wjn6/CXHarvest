#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片预览组件 - Fluent风格
支持缩放、旋转、拖动、复制
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDialog, QFrame, QToolButton
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QCursor, QTransform

from qfluentwidgets import (
    BodyLabel, SmoothScrollArea,
    InfoBar, InfoBarPosition, isDarkTheme, StrongBodyLabel
)
from qfluentwidgets import FluentIcon as FIF


class ClickableImageLabel(QLabel):
    """可点击的图片标签"""
    clicked = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(QCursor(Qt.PointingHandCursor))
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ImagePreviewDialog(QDialog):
    """
    增强版图片预览对话框 - Fluent风格
    
    功能:
    - 缩放: 滚轮/按钮/快捷键(+/-)
    - 旋转: 按钮/快捷键(R/L)
    - 拖动: 鼠标拖动平移
    - 复制: 双击/Ctrl+C/按钮
    - 重置: 按钮/快捷键(0)
    
    使用方法:
    >>> from ui.image_preview import ImagePreviewDialog
    >>> dialog = ImagePreviewDialog(pixmap, parent)
    >>> dialog.exec()
    """
    
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle("图片预览")
        self.setModal(True)
        self.setAttribute(Qt.WA_DeleteOnClose)  # 关闭时自动删除，释放内存
        
        # 设置无边框窗口
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._title_drag_pos = None
        
        # 保存原始图片（复制一份，避免外部引用问题）
        self.original_pixmap = pixmap.copy()
        self._cached_rotated = None  # 缓存旋转后的图片
        self._cache_angle = None
        
        self.current_scale = 1.0
        self.min_scale = 0.1
        self.max_scale = 5.0
        self.rotation_angle = 0
        
        # 拖动状态
        self._dragging = False
        self._drag_start_pos = None
        self._scroll_start_h = 0
        self._scroll_start_v = 0
        
        # 计算屏幕限制
        screen = self.screen().availableGeometry()
        self.max_width = int(screen.width() * 0.85)
        self.max_height = int(screen.height() * 0.85)
        
        # 初始缩放适应屏幕
        if pixmap.width() > self.max_width or pixmap.height() > self.max_height:
            scale_w = self.max_width / pixmap.width()
            scale_h = self.max_height / pixmap.height()
            self.current_scale = min(scale_w, scale_h)
        
        self._init_ui()
        self._update_image()
        
        # 设置窗口大小
        img_w = int(self.original_pixmap.width() * self.current_scale)
        img_h = int(self.original_pixmap.height() * self.current_scale)
        self.resize(min(img_w + 40, self.max_width), min(img_h + 120, self.max_height))
    
    def _create_tool_btn(self, icon, tooltip):
        """创建工具栏按钮 - 使用原生QToolButton避免QFont错误"""
        btn = QToolButton(self)
        btn.setIcon(icon.icon())
        btn.setIconSize(QSize(16, 16))
        btn.setFixedSize(32, 32)
        btn.setToolTip(tooltip)
        btn.setAutoRaise(True)
        return btn
    
    def _init_ui(self):
        """初始化UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # ===== 自定义标题栏 =====
        self._create_title_bar(main_layout)
        
        # ===== 顶部工具栏 =====
        toolbar_widget = QWidget()
        toolbar_widget.setObjectName("toolbar")
        toolbar = QHBoxLayout(toolbar_widget)
        toolbar.setContentsMargins(16, 10, 16, 10)
        toolbar.setSpacing(8)
        
        # 状态信息
        self.scale_label = BodyLabel(self._get_status_text(), self)
        self.scale_label.setObjectName("statusLabel")
        toolbar.addWidget(self.scale_label)
        
        toolbar.addStretch()
        
        # 缩放控制组
        zoom_out_btn = self._create_tool_btn(FIF.REMOVE, "缩小 (−)")
        zoom_out_btn.clicked.connect(lambda: self._zoom(-0.1))
        toolbar.addWidget(zoom_out_btn)
        
        self.zoom_label = BodyLabel(f"{int(self.current_scale * 100)}%", self)
        self.zoom_label.setFixedWidth(45)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_label.setObjectName("zoomLabel")
        toolbar.addWidget(self.zoom_label)
        
        zoom_in_btn = self._create_tool_btn(FIF.ADD, "放大 (+)")
        zoom_in_btn.clicked.connect(lambda: self._zoom(0.1))
        toolbar.addWidget(zoom_in_btn)
        
        # 分隔
        self._add_separator(toolbar)
        
        # 旋转按钮 - 顺时针旋转90°
        rotate_btn = self._create_tool_btn(FIF.SYNC, "旋转90° (R)")
        rotate_btn.clicked.connect(lambda: self._rotate(90))
        toolbar.addWidget(rotate_btn)
        
        # 分隔
        self._add_separator(toolbar)
        
        # 重置按钮
        reset_btn = self._create_tool_btn(FIF.HOME, "重置 (0)")
        reset_btn.clicked.connect(self._reset_all)
        toolbar.addWidget(reset_btn)
        
        # 复制按钮
        copy_btn = self._create_tool_btn(FIF.COPY, "复制图片 (Ctrl+C)")
        copy_btn.clicked.connect(self._copy_image)
        toolbar.addWidget(copy_btn)
        
        # 分隔
        self._add_separator(toolbar)
        
        # 关闭按钮
        close_btn = self._create_tool_btn(FIF.CLOSE, "关闭 (ESC)")
        close_btn.clicked.connect(self.close)
        toolbar.addWidget(close_btn)
        
        main_layout.addWidget(toolbar_widget)
        
        # ===== 图片区域 =====
        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("imageScrollArea")
        
        self.img_container = QWidget()
        self.img_container.setObjectName("imageContainer")
        container_layout = QVBoxLayout(self.img_container)
        container_layout.setAlignment(Qt.AlignCenter)
        container_layout.setContentsMargins(20, 20, 20, 20)
        
        self.img_label = QLabel(self.img_container)
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setObjectName("imageLabel")
        container_layout.addWidget(self.img_label)
        
        self.scroll_area.setWidget(self.img_container)
        main_layout.addWidget(self.scroll_area, 1)
        
        # ===== 底部提示栏 =====
        hint_widget = QWidget()
        hint_widget.setObjectName("hintBar")
        hint_layout = QHBoxLayout(hint_widget)
        hint_layout.setContentsMargins(16, 8, 16, 8)
        
        hint_label = BodyLabel("滚轮缩放 · 拖动平移 · R/L旋转 · 双击复制 · ESC关闭", self)
        hint_label.setObjectName("hintLabel")
        hint_layout.addWidget(hint_label)
        
        hint_layout.addStretch()
        
        # 图片尺寸信息
        size_text = f"{self.original_pixmap.width()} × {self.original_pixmap.height()} px"
        size_label = BodyLabel(size_text, self)
        size_label.setObjectName("sizeLabel")
        hint_layout.addWidget(size_label)
        
        main_layout.addWidget(hint_widget)
        
        # ===== 应用样式 =====
        self._apply_style()
    
    def _create_title_bar(self, parent_layout):
        """创建自定义标题栏"""
        title_bar = QFrame(self)
        title_bar.setFixedHeight(40)
        title_bar.setObjectName("titleBar")
        
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(16, 0, 8, 0)
        title_layout.setSpacing(12)
        
        # 图标和标题
        title_label = StrongBodyLabel("🖼️ 图片预览", title_bar)
        title_layout.addWidget(title_label)
        
        title_layout.addStretch()
        
        # 关闭按钮
        close_btn = self._create_tool_btn(FIF.CLOSE, "关闭")
        close_btn.clicked.connect(self.close)
        title_layout.addWidget(close_btn)
        
        parent_layout.addWidget(title_bar)
    
    def _add_separator(self, layout):
        """添加分隔线"""
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setObjectName("separator")
        sep.setFixedWidth(1)
        sep.setFixedHeight(20)
        layout.addWidget(sep)
    
    def _apply_style(self):
        """应用Fluent风格样式 - 跟随系统主题"""
        if isDarkTheme():
            self.setStyleSheet("""
                QDialog {
                    background-color: #1a1a1a;
                }
                #titleBar {
                    background-color: #1f1f1f;
                    border-bottom: 1px solid #333333;
                }
                #toolbar {
                    background-color: #2d2d2d;
                    border-bottom: 1px solid #3d3d3d;
                }
                #statusLabel, #hintLabel, #sizeLabel {
                    color: #aaaaaa;
                    font-size: 12px;
                }
                #zoomLabel {
                    color: #ffffff;
                    font-size: 12px;
                }
                #separator {
                    background-color: #4d4d4d;
                }
                #imageScrollArea {
                    border: none;
                    background-color: #1a1a1a;
                }
                #imageContainer {
                    background-color: #1a1a1a;
                }
                #imageLabel {
                    background-color: transparent;
                }
                #hintBar {
                    background-color: #252525;
                    border-top: 1px solid #3d3d3d;
                }
                QToolButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 4px;
                }
                QToolButton:hover {
                    background-color: rgba(255, 255, 255, 0.1);
                }
                QToolButton:pressed {
                    background-color: rgba(255, 255, 255, 0.05);
                }
                QScrollBar:vertical, QScrollBar:horizontal {
                    background-color: #2d2d2d;
                    width: 10px;
                    height: 10px;
                }
                QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                    background-color: #5a5a5a;
                    border-radius: 5px;
                    min-height: 30px;
                    min-width: 30px;
                }
                QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
                    background-color: #6a6a6a;
                }
                QScrollBar::add-line, QScrollBar::sub-line {
                    height: 0; width: 0;
                }
            """)
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f5f5f5;
                }
                #titleBar {
                    background-color: #f3f3f3;
                    border-bottom: 1px solid #e0e0e0;
                }
                #toolbar {
                    background-color: #ffffff;
                    border-bottom: 1px solid #e0e0e0;
                }
                #statusLabel, #hintLabel, #sizeLabel {
                    color: #666666;
                    font-size: 12px;
                }
                #zoomLabel {
                    color: #333333;
                    font-size: 12px;
                }
                #separator {
                    background-color: #d0d0d0;
                }
                #imageScrollArea {
                    border: none;
                    background-color: #f5f5f5;
                }
                #imageContainer {
                    background-color: #f5f5f5;
                }
                #imageLabel {
                    background-color: transparent;
                }
                #hintBar {
                    background-color: #fafafa;
                    border-top: 1px solid #e0e0e0;
                }
                QToolButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 4px;
                }
                QToolButton:hover {
                    background-color: rgba(0, 0, 0, 0.05);
                }
                QToolButton:pressed {
                    background-color: rgba(0, 0, 0, 0.1);
                }
                QScrollBar:vertical, QScrollBar:horizontal {
                    background-color: #f0f0f0;
                    width: 10px;
                    height: 10px;
                }
                QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                    background-color: #c0c0c0;
                    border-radius: 5px;
                    min-height: 30px;
                    min-width: 30px;
                }
                QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
                    background-color: #a0a0a0;
                }
                QScrollBar::add-line, QScrollBar::sub-line {
                    height: 0; width: 0;
                }
            """)
    
    def _get_status_text(self):
        """获取状态文本"""
        if self.rotation_angle == 0:
            return "原图"
        return f"旋转 {self.rotation_angle}°"
    
    def _update_image(self):
        """更新显示的图片（带缓存优化）"""
        # 使用缓存优化旋转性能
        if self.rotation_angle != self._cache_angle:
            transform = QTransform().rotate(self.rotation_angle)
            self._cached_rotated = self.original_pixmap.transformed(transform, Qt.SmoothTransformation)
            self._cache_angle = self.rotation_angle
        
        rotated = self._cached_rotated if self._cached_rotated else self.original_pixmap
        
        # 应用缩放
        new_width = int(rotated.width() * self.current_scale)
        new_height = int(rotated.height() * self.current_scale)
        scaled = rotated.scaled(new_width, new_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        self.img_label.setPixmap(scaled)
        self._update_labels()
    
    def _update_labels(self):
        """更新标签显示"""
        self.zoom_label.setText(f"{int(self.current_scale * 100)}%")
        self.scale_label.setText(self._get_status_text())
    
    def _zoom(self, delta):
        """缩放图片"""
        new_scale = self.current_scale + delta
        if self.min_scale <= new_scale <= self.max_scale:
            self.current_scale = round(new_scale, 2)  # 避免浮点数误差
            self._update_image()
    
    def _reset_all(self):
        """重置缩放和旋转"""
        self.current_scale = 1.0
        self.rotation_angle = 0
        self._cached_rotated = None
        self._cache_angle = None
        self._update_image()
    
    def _rotate(self, angle):
        """旋转图片"""
        self.rotation_angle = (self.rotation_angle + angle) % 360
        self._update_image()
    
    def _copy_image(self):
        """复制图片到剪贴板"""
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setPixmap(self.original_pixmap)
        InfoBar.success(
            title="已复制",
            content="图片已复制到剪贴板",
            parent=self,
            position=InfoBarPosition.TOP,
            duration=1500
        )
    
    def wheelEvent(self, event):
        """鼠标滚轮缩放"""
        delta = event.angleDelta().y()
        self._zoom(0.1 if delta > 0 else -0.1)
    
    def mouseDoubleClickEvent(self, event):
        """双击复制图片"""
        self._copy_image()
    
    def keyPressEvent(self, event):
        """快捷键"""
        key = event.key()
        if key == Qt.Key_Escape:
            self.close()
        elif key in (Qt.Key_Plus, Qt.Key_Equal):
            self._zoom(0.1)
        elif key == Qt.Key_Minus:
            self._zoom(-0.1)
        elif key == Qt.Key_0:
            self._reset_all()
        elif key == Qt.Key_C and event.modifiers() == Qt.ControlModifier:
            self._copy_image()
        elif key == Qt.Key_R:
            self._rotate(90)
        elif key == Qt.Key_L:
            self._rotate(-90)
        super().keyPressEvent(event)
    
    def mousePressEvent(self, event):
        """鼠标按下 - 开始拖动"""
        if event.button() == Qt.LeftButton:
            # 标题栏区域（前40px）用于拖动窗口
            if event.position().y() < 40:
                self._title_drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            else:
                # 其他区域用于拖动图片
                self._dragging = True
                self._drag_start_pos = event.globalPosition().toPoint()
                self._scroll_start_h = self.scroll_area.horizontalScrollBar().value()
                self._scroll_start_v = self.scroll_area.verticalScrollBar().value()
                self.setCursor(QCursor(Qt.ClosedHandCursor))
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """鼠标移动 - 拖动平移"""
        # 标题栏拖动窗口
        if self._title_drag_pos is not None and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._title_drag_pos)
        # 图片拖动
        elif self._dragging and self._drag_start_pos:
            delta = event.globalPosition().toPoint() - self._drag_start_pos
            self.scroll_area.horizontalScrollBar().setValue(self._scroll_start_h - delta.x())
            self.scroll_area.verticalScrollBar().setValue(self._scroll_start_v - delta.y())
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """鼠标释放 - 结束拖动"""
        if event.button() == Qt.LeftButton:
            self._title_drag_pos = None
            self._dragging = False
            self._drag_start_pos = None
            self.setCursor(QCursor(Qt.ArrowCursor))
        super().mouseReleaseEvent(event)
    
    def closeEvent(self, event):
        """关闭时清理资源"""
        self._cached_rotated = None
        self.original_pixmap = None
        self.img_label.clear()
        super().closeEvent(event)


def show_image_preview(pixmap: QPixmap, parent=None):
    """
    便捷函数：显示图片预览对话框
    
    Args:
        pixmap: 要预览的图片
        parent: 父窗口
    """
    dialog = ImagePreviewDialog(pixmap, parent)
    dialog.exec()
