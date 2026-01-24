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
    # 如果核心模块加载失败，写入 fallback 日志
    with open(current_dir / "startup_error.txt", "w", encoding="utf-8") as f:
        f.write(f"核心模块加载失败: {e}\n")
        traceback.print_exc(file=f)
    sys.exit(1)



def main():
    """主程序入口"""
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from qfluentwidgets import setTheme, Theme
        
        from ui.main_window import MainWindowFluent
        
        app_logger.info(f"启动 {APP_NAME} v{__version__}")
        
        # 创建应用
        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        app.setApplicationVersion(__version__)
        
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
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
