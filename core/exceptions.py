#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一异常处理模块
包含所有自定义异常类和异常处理装饰器
"""

import json
from datetime import datetime
from typing import Dict, Any
import requests
from .enterprise_logger import app_logger

# =============================================================================
# 统一异常处理系统
# =============================================================================
class AppError(Exception):
    """应用自定义异常基类"""
    def __init__(self, message: str, error_code: str = None, details: Dict = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "APP_ERROR"
        self.details = details or {}
        self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'error_type': self.__class__.__name__,
            'error_code': self.error_code,
            'message': self.message,
            'details': self.details,
            'timestamp': self.timestamp.isoformat()
        }

    def __str__(self):
        return f"{self.error_code}: {self.message}"


class LoginError(AppError):
    """登录相关异常"""
    def __init__(self, message: str, details: Dict = None):
        super().__init__(message, "LOGIN_ERROR", details)

class NetworkError(AppError):
    """网络相关异常"""
    def __init__(self, message: str, status_code: int = None, details: Dict = None):
        details = details or {}
        if status_code:
            details['status_code'] = status_code
        super().__init__(message, "NETWORK_ERROR", details)

class ParseError(AppError):
    """解析相关异常"""
    def __init__(self, message: str, source: str = None, details: Dict = None):
        details = details or {}
        if source:
            details['source'] = source
        super().__init__(message, "PARSE_ERROR", details)

class ValidationError(AppError):
    """验证相关异常"""
    def __init__(self, message: str, field: str = None, details: Dict = None):
        details = details or {}
        if field:
            details['field'] = field
        super().__init__(message, "VALIDATION_ERROR", details)

class FileOperationError(AppError):
    """文件操作异常"""
    def __init__(self, message: str, file_path: str = None, details: Dict = None):
        details = details or {}
        if file_path:
            details['file_path'] = file_path
        super().__init__(message, "FILE_ERROR", details)

class HomeworkError(AppError):
    """作业相关异常"""
    def __init__(self, message: str, homework_id: str = None, details: Dict = None):
        details = details or {}
        if homework_id:
            details['homework_id'] = homework_id
        super().__init__(message, "HOMEWORK_ERROR", details)

class QuestionError(AppError):
    """题目相关异常"""
    def __init__(self, message: str, question_id: str = None, details: Dict = None):
        details = details or {}
        if question_id:
            details['question_id'] = question_id
        super().__init__(message, "QUESTION_ERROR", details)

# =============================================================================
# 统一异常处理装饰器
# =============================================================================
def handle_exceptions(func):
    """统一异常处理装饰器"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except AppError as e:
            # 应用自定义异常，直接传播
            app_logger.info(f"应用异常 {e.error_code}: {e.message}")
            if e.details:
                app_logger.info(f"详细信息: {e.details}")
            raise
        except requests.exceptions.RequestException as e:
            app_logger.debug(f"网络异常详情: {e}")
            raise NetworkError("网络请求失败，请检查网络连接")
        except json.JSONDecodeError as e:
            app_logger.debug(f"JSON解析异常详情: {e}")
            raise ParseError("数据解析失败")
        except (IOError, OSError) as e:
            app_logger.debug(f"文件操作异常详情: {e}")
            raise FileOperationError("文件操作失败")
        except Exception as e:
            app_logger.error(f"未预期的错误: {type(e).__name__}")
            app_logger.debug(f"异常详情: {e}")
            raise AppError("发生未知错误", "UNKNOWN_ERROR")
    return wrapper

def safe_execute(func, default_value=None, error_message="操作失败"):
    """安全执行函数，捕获异常并返回默认值"""
    try:
        return func()
    except AppError as e:
        app_logger.info(f"{error_message}: {e.message}")
        return default_value
    except Exception as e:
        app_logger.info(f"{error_message}: {str(e)}")
        return default_value

def log_exception(e: Exception, context: str = ""):
    """记录异常信息"""
    if isinstance(e, AppError):
        app_logger.info(f"异常日志 [{context}]: {e.to_dict()}")
    else:
        app_logger.info(f"异常日志 [{context}]: {type(e).__name__}: {str(e)}")

# 导出所有异常类和工具函数
__all__ = [
    'AppError', 'LoginError', 'NetworkError', 'ParseError', 
    'ValidationError', 'FileOperationError', 'HomeworkError', 'QuestionError',
    'handle_exceptions', 'safe_execute', 'log_exception'
]
