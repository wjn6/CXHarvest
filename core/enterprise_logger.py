#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业级日志记录模块
提供统一的、专业的日志记录功能，符合企业开发标准

优化说明：
- 统一日志接口，减少重复实例
- 支持异常堆栈跟踪
- 增强日志格式支持调试
- 详细的 Debug 格式：毫秒精度 + 行号
- 日志文件轮转支持
"""

# =============================================================================
# 标准库导入
# =============================================================================
import logging
import logging.handlers
import os
import sys
import traceback
from datetime import datetime
from typing import Any, Dict, Optional, Union
from enum import Enum
from pathlib import Path

# =============================================================================
# 第三方库导入
# =============================================================================
# None

# =============================================================================
# 项目内部导入
# =============================================================================
# None


class LogLevel(Enum):
    """日志级别枚举"""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class EnterpriseLogger:
    """企业级日志记录器
    
    提供标准化的日志记录功能，支持多种输出格式和日志级别。
    遵循企业开发标准，避免使用表情符号等非正式元素。
    
    Attributes:
        name: 日志记录器名称
        level: 日志级别
        logger: Python标准日志记录器实例
    """
    
    def __init__(self, name: str = "Application", level: LogLevel = LogLevel.INFO):
        """初始化企业级日志记录器
        
        Args:
            name: 日志记录器名称
            level: 日志级别
        """
        self.name = name
        self.level = level
        self.logger = self._setup_logger()
        
    # 日志格式常量
    # 控制台格式：简洁，适合实时查看
    CONSOLE_FORMAT = '[%(asctime)s.%(msecs)03d] [%(levelname)-5s] [%(name)s] %(message)s'
    CONSOLE_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
    
    # 文件格式：详细，适合调试和问题追踪
    FILE_FORMAT = '[%(asctime)s.%(msecs)03d] [%(levelname)-5s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s'
    FILE_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
    
    # 日志文件轮转配置
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
    BACKUP_COUNT = 5  # 保留5个备份文件
    
    def _setup_logger(self) -> logging.Logger:
        """设置日志记录器配置
        
        Returns:
            配置好的日志记录器实例
        """
        logger = logging.getLogger(self.name)
        logger.setLevel(self.level.value)
        
        # 避免重复添加处理器
        if logger.handlers:
            return logger
            
        # 创建控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self.level.value)
        
        # 控制台格式化器（简洁版）
        console_formatter = logging.Formatter(
            fmt=self.CONSOLE_FORMAT,
            datefmt=self.CONSOLE_DATE_FORMAT
        )
        console_handler.setFormatter(console_formatter)
        
        # 添加处理器
        logger.addHandler(console_handler)
        
        # 创建文件处理器（如果需要）
        self._setup_file_handler(logger)
        
        return logger
    
    def _setup_file_handler(self, logger: logging.Logger):
        """设置文件日志处理器（支持轮转）
        
        Args:
            logger: 日志记录器实例
        """
        try:
            # 使用 PathManager 获取日志目录
            from .common import PathManager
            log_dir = PathManager.get_logs_dir()
            
            # 创建日志文件
            log_file = log_dir / f"{self.name.lower()}_{datetime.now().strftime('%Y%m%d')}.log"
            
            # 使用 RotatingFileHandler 支持日志轮转
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=self.MAX_FILE_SIZE,
                backupCount=self.BACKUP_COUNT,
                encoding='utf-8'
            )
            file_handler.setLevel(LogLevel.DEBUG.value)
            
            # 文件格式化器（详细版，包含函数名和行号）
            file_formatter = logging.Formatter(
                fmt=self.FILE_FORMAT,
                datefmt=self.FILE_DATE_FORMAT
            )
            file_handler.setFormatter(file_formatter)
            
            logger.addHandler(file_handler)
            
        except Exception as e:
            # 如果文件日志设置失败，只记录到控制台
            logger.warning(f"Failed to setup file logging: {e}")
    
    # =========================================================================
    # 基础日志方法
    # =========================================================================
    
    def debug(self, message: str, details: Optional[Dict[str, Any]] = None):
        """记录调试信息
        
        Args:
            message: 日志消息
            details: 额外的详细信息
        """
        self._log(logging.DEBUG, message, details)
    
    def info(self, message: str, details: Optional[Dict[str, Any]] = None):
        """记录一般信息
        
        Args:
            message: 日志消息
            details: 额外的详细信息
        """
        self._log(logging.INFO, message, details)
    
    def warning(self, message: str, details: Optional[Dict[str, Any]] = None):
        """记录警告信息
        
        Args:
            message: 日志消息
            details: 额外的详细信息
        """
        self._log(logging.WARNING, message, details)
    
    def error(self, message: str, details: Optional[Dict[str, Any]] = None):
        """记录错误信息
        
        Args:
            message: 日志消息
            details: 额外的详细信息
        """
        self._log(logging.ERROR, message, details)
    
    def critical(self, message: str, details: Optional[Dict[str, Any]] = None):
        """记录严重错误信息
        
        Args:
            message: 日志消息
            details: 额外的详细信息
        """
        self._log(logging.CRITICAL, message, details)
    
    # =========================================================================
    # 增强日志方法
    # =========================================================================
    
    def exception(self, message: str, exc: Optional[Exception] = None,
                  details: Optional[Dict[str, Any]] = None):
        """记录异常信息，自动捕获堆栈跟踪
        
        Args:
            message: 日志消息
            exc: 异常对象（可选，如果不提供将尝试从当前上下文获取）
            details: 额外的详细信息
        """
        details = details.copy() if details else {}
        
        if exc:
            # 使用提供的异常
            trace_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
            details['exception_type'] = type(exc).__name__
            details['exception_message'] = str(exc)
        else:
            # 尝试从当前上下文获取异常
            exc_info = sys.exc_info()
            if exc_info[0] is not None:
                trace_lines = traceback.format_exception(*exc_info)
                details['exception_type'] = exc_info[0].__name__
                details['exception_message'] = str(exc_info[1])
            else:
                trace_lines = []
        
        if trace_lines:
            details['traceback'] = ''.join(trace_lines).strip()
        
        self._log(logging.ERROR, f"异常: {message}", details)
    
    def success(self, message: str, details: Optional[Dict[str, Any]] = None):
        """记录成功操作信息
        
        Args:
            message: 日志消息
            details: 额外的详细信息
        """
        self._log(logging.INFO, f"成功: {message}", details)
    
    def operation(self, operation: str, status: str = "开始", 
                  details: Optional[Dict[str, Any]] = None):
        """记录操作信息
        
        Args:
            operation: 操作名称
            status: 操作状态
            details: 额外的详细信息
        """
        message = f"操作 [{status}]: {operation}"
        self._log(logging.INFO, message, details)
    
    # =========================================================================
    # 专用日志方法
    # =========================================================================
    
    def network_request(self, method: str, url: str, status_code: Optional[int] = None, 
                        details: Optional[Dict[str, Any]] = None):
        """记录网络请求信息
        
        Args:
            method: HTTP方法
            url: 请求URL
            status_code: 响应状态码
            details: 额外的详细信息
        """
        status_info = f" [{status_code}]" if status_code else ""
        message = f"网络请求: {method} {url}{status_info}"
        self._log(logging.DEBUG, message, details)
    
    def file_operation(self, operation: str, file_path: str, 
                       details: Optional[Dict[str, Any]] = None):
        """记录文件操作信息
        
        Args:
            operation: 操作类型
            file_path: 文件路径
            details: 额外的详细信息
        """
        message = f"文件操作: {operation} {file_path}"
        self._log(logging.DEBUG, message, details)
    
    def session_event(self, event: str, details: Optional[Dict[str, Any]] = None):
        """记录会话事件
        
        Args:
            event: 事件描述
            details: 额外的详细信息
        """
        message = f"会话事件: {event}"
        self._log(logging.INFO, message, details)
    
    def performance_metric(self, metric_name: str, value: Union[int, float], 
                           unit: str = "", details: Optional[Dict[str, Any]] = None):
        """记录性能指标
        
        Args:
            metric_name: 指标名称
            value: 指标值
            unit: 单位
            details: 额外的详细信息
        """
        unit_str = f" {unit}" if unit else ""
        message = f"性能指标: {metric_name} = {value}{unit_str}"
        self._log(logging.DEBUG, message, details)
    
    # =========================================================================
    # 内部方法
    # =========================================================================
    
    def _log(self, level: int, message: str, details: Optional[Dict[str, Any]] = None):
        """内部日志记录方法
        
        Args:
            level: 日志级别
            message: 日志消息
            details: 额外的详细信息
        """
        if details:
            # 过滤掉 traceback 以保持日志简洁，traceback 单独处理
            main_details = {k: v for k, v in details.items() if k != 'traceback'}
            if main_details:
                detail_str = " | ".join([f"{k}={v}" for k, v in main_details.items()])
                full_message = f"{message} | {detail_str}"
            else:
                full_message = message
            
            # 如果有 traceback，在消息后面追加
            if 'traceback' in details:
                full_message += f"\n{details['traceback']}"
        else:
            full_message = message
            
        self.logger.log(level, full_message)
    
    def set_level(self, level: LogLevel):
        """设置日志级别
        
        Args:
            level: 新的日志级别
        """
        self.level = level
        self.logger.setLevel(level.value)
        for handler in self.logger.handlers:
            handler.setLevel(level.value)


# =============================================================================
# 全局日志记录器实例
# =============================================================================

# 主应用日志（通用）
app_logger = EnterpriseLogger("AppCore", LogLevel.INFO)

# 网络请求日志（专用于网络相关操作）
network_logger = EnterpriseLogger("Network", LogLevel.INFO)

# 文件操作日志（专用于文件读写操作）
file_logger = EnterpriseLogger("FileOps", LogLevel.INFO)


# =============================================================================
# 便捷函数
# =============================================================================

def get_logger(name: str = "Application") -> EnterpriseLogger:
    """获取指定名称的日志记录器
    
    Args:
        name: 日志记录器名称
        
    Returns:
        日志记录器实例
    """
    return EnterpriseLogger(name)


def set_global_log_level(level: LogLevel):
    """设置全局日志级别
    
    Args:
        level: 日志级别
    """
    for logger_instance in [app_logger, network_logger, file_logger]:
        logger_instance.set_level(level)
