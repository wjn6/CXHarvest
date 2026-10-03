#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工作线程安全退役工具

Qt6 中，QThread 对象在仍运行时被销毁（垃圾回收 / 父对象析构 / 变量被置 None）
会触发 "QThread: Destroyed while thread is still running" 并 qFatal 崩溃。

本模块提供统一的退役机制：
1. 断开线程全部信号（防止退役后线程仍向 UI 发送过期数据）
2. 请求协作式停止（stop / cancel）
3. 若仍在运行则保留模块级引用，等待线程结束后再安全销毁
"""

from typing import List, Optional

from PySide6.QtCore import QThread

# 模块级引用表：持有退役时仍在运行的线程，防止其被垃圾回收导致崩溃
_retired_workers: List[QThread] = []


def _finalize_worker(worker: QThread) -> None:
    """线程结束后清理：移出引用表并安全销毁

    注意：finished 信号只在 run() 返回后发出，因此调用本函数时线程必然已停止，
    此时 deleteLater / GC 均安全（Qt >= 5.10 保证）。
    """
    try:
        if worker in _retired_workers:
            _retired_workers.remove(worker)
    except Exception:
        pass
    try:
        worker.deleteLater()
    except Exception:
        pass


def _disconnect_all_signals(worker: QThread) -> None:
    """断开线程的全部信号连接（SignalInstance），防止过期数据回写 UI"""
    import warnings
    try:
        for name in dir(worker):
            if name.startswith('_'):
                continue
            try:
                attr = getattr(worker, name)
            except Exception:
                continue
            if attr is None:
                continue
            if type(attr).__name__ == 'SignalInstance' and hasattr(attr, 'disconnect'):
                # PySide6 对无连接的信号 disconnect() 会打印 RuntimeWarning（纯噪音）
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    try:
                        attr.disconnect()
                    except (RuntimeError, TypeError):
                        pass
    except Exception:
        pass


def retire_worker(worker: Optional[QThread], wait_ms: int = 0) -> bool:
    """安全退役工作线程

    Args:
        worker: QThread 实例或 None
        wait_ms: 请求停止后最多阻塞等待的毫秒数（默认 0 不阻塞，保持 UI 流畅）

    Returns:
        bool: 退役时线程是否已结束（不再运行）
    """
    if worker is None:
        return True

    try:
        # 1. 断开全部信号，防止退役后线程仍向 UI 发送过期数据
        _disconnect_all_signals(worker)

        # 2. 请求协作式停止（线程若提供 stop / cancel 方法）
        stop_method = getattr(worker, 'stop', None) or getattr(worker, 'cancel', None)
        if stop_method:
            try:
                stop_method()
            except Exception:
                pass
        try:
            worker.requestInterruption()
        except Exception:
            pass

        # 3. 已结束则直接清理
        if not worker.isRunning():
            _finalize_worker(worker)
            return True

        # 4. 仍在运行：保留模块级引用，等待结束后清理
        if worker not in _retired_workers:
            worker.finished.connect(lambda w=worker: _finalize_worker(w))
            _retired_workers.append(worker)

        if wait_ms > 0:
            worker.wait(wait_ms)

        # 5. 若等待期间线程已结束（finished 可能早于连接发出），手动清理兜底
        if not worker.isRunning():
            _finalize_worker(worker)
            return True
        return False

    except RuntimeError:
        # C++ 对象已被销毁，无需处理
        return True
    except Exception:
        return False
