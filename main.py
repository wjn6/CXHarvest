#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
超星学习通自动化工具 - Fluent Design 版本启动入口
"""

import sys
import traceback
from pathlib import Path

# 获取应用目录 (兼容打包环境)
if getattr(sys, 'frozen', False):
    current_dir = Path(sys.executable).parent
else:
    current_dir = Path(__file__).parent

sys.path.insert(0, str(current_dir))

try:
    from core.enterprise_logger import app_logger
    from core.version import __version__, APP_NAME
except Exception as e:
    # 如果核心模块加载失败，写入 fallback 日志（优先 TEMP，因 Program Files 只读）
    import os, tempfile
    err_path = Path(tempfile.gettempdir()) / "CXHarvest_startup_error.txt"
    try:
        with open(err_path, "w", encoding="utf-8") as f:
            f.write(f"核心模块加载失败: {e}\n")
            traceback.print_exc(file=f)
    except Exception:
        pass
    # 同时输出到 stderr（命令行调试用）
    print(f"核心模块加载失败: {e}", file=sys.stderr)
    traceback.print_exc()
    sys.exit(1)



def main():
    """主程序入口"""
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        app_logger.info(f"启动 {APP_NAME} v{__version__}")
        
        # 创建应用
        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        app.setApplicationVersion(__version__)

        from qfluentwidgets import setTheme, Theme, FluentWindow

        qt_binding = None
        for cls in FluentWindow.mro():
            module_name = getattr(cls, '__module__', '')
            if module_name.startswith('PySide6'):
                qt_binding = 'PySide6'
                break
            if module_name.startswith('PyQt'):
                qt_binding = module_name.split('.', 1)[0]
                break
        if qt_binding and qt_binding != 'PySide6':
            app_logger.error(
                f"检测到 qfluentwidgets 使用 {qt_binding}，但当前项目使用 PySide6。"
                "请使用项目 .venv 运行，或安装 PySide6-Fluent-Widgets 并避免 PyQt 版 qfluentwidgets。"
            )
            sys.exit(1)
        
        from ui.main_window import MainWindowFluent
        
        # 设置主题
        setTheme(Theme.LIGHT)  # 可选: Theme.DARK, Theme.AUTO
        
        # 创建并显示主窗口
        window = MainWindowFluent()
        window.show()
        
        sys.exit(app.exec())
        
    except ImportError as e:
        app_logger.error(f"缺少必要依赖: {e}")
        app_logger.info("请运行: pip install PySide6-Fluent-Widgets")
        sys.exit(1)
        
    except Exception as e:
        app_logger.error(f"程序启动失败: {e}")
        # 写入错误日志到 TEMP 方便打包环境排查
        import tempfile
        err_path = Path(tempfile.gettempdir()) / "CXHarvest_startup_error.txt"
        try:
            with open(err_path, "w", encoding="utf-8") as f:
                f.write(f"程序启动失败: {e}\n")
                traceback.print_exc(file=f)
        except Exception:
            pass
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
