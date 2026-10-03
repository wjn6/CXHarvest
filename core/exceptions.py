#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一异常处理模块
包含所有自定义异常类
"""

from datetime import datetime
from typing import Dict, Any

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

# 导出所有异常类
__all__ = ['AppError', 'LoginError', 'NetworkError', 'ParseError']
