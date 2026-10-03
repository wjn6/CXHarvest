#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一Session管理模块
提供基础的Session管理功能，避免代码重复
"""

# =============================================================================
# 标准库导入
# =============================================================================
import threading
from typing import Optional

# =============================================================================
# 第三方库导入
# =============================================================================
import requests

# =============================================================================
# 项目内部导入
# =============================================================================
from .common import NetworkError, LoginError
from .enterprise_logger import app_logger

_tls = threading.local()


def thread_local_session(base_session):
    """返回基会话的线程本地副本（Session 的 headers/cookie jar 并非线程安全）

    HTTPAdapter 按对象共享以保留连接复用与重试，可变的 cookie/headers 各自快照。
    """
    if base_session is None:
        return None

    cache = getattr(_tls, 'sessions', None)
    if cache is None:
        cache = _tls.sessions = {}

    clone = cache.get(base_session)
    if clone is not None:
        return clone

    clone = requests.Session()
    clone.headers.update(dict(getattr(base_session, 'headers', None) or {}))
    try:
        clone.cookies.update(requests.utils.dict_from_cookiejar(base_session.cookies))
    except Exception as e:
        app_logger.warning("复制会话 cookie 失败", {"error": str(e)})
    for prefix, adapter in dict(getattr(base_session, 'adapters', None) or {}).items():
        clone.mount(prefix, adapter)
    clone.verify = getattr(base_session, 'verify', True)
    clone.proxies = dict(getattr(base_session, 'proxies', None) or {})
    clone.trust_env = getattr(base_session, 'trust_env', True)
    cache[base_session] = clone
    return clone


class SessionManagerMixin:
    """Session管理Mixin类，为其他管理器提供统一的session管理功能
    
    提供统一的Session管理接口，包括登录状态检查、Session验证、
    自动失效处理等功能。使用Mixin模式避免代码重复。
    
    Attributes:
        _login_manager: 登录管理器实例
        _session: 缓存的Session对象
        _session_valid: Session有效性标记
    """
    
    def __init__(self, login_manager=None):
        """初始化Session管理器
        
        Args:
            login_manager: 登录管理器实例
        """
        self._login_manager = login_manager
        self._session = None
        self._session_valid = False
        
    @property
    def login_manager(self):
        """获取登录管理器实例
        
        Returns:
            LoginManager: 登录管理器实例
        """
        if not self._login_manager:
            from .login_manager import LoginManager
            self._login_manager = LoginManager()
            app_logger.info("创建新的登录管理器实例")
        return self._login_manager
    
    @login_manager.setter
    def login_manager(self, value):
        """设置登录管理器实例"""
        self._login_manager = value
        self._session = None  # 重置session
        self._session_valid = False
    
    def get_session(self):
        """获取有效的Session实例
        
        Returns:
            requests.Session: 有效的session实例
            
        Raises:
            LoginError: 用户未登录
            NetworkError: 网络连接失败
        """
        # 如果session已缓存且有效，直接返回
        if self._session and self._session_valid:
            return self._session
            
        # 检查登录状态
        if not self.login_manager.check_login_status():
            raise LoginError("用户未登录，请先完成登录")
            
        # 获取session（本线程独立副本，不与其它工作线程共用）
        self._session = thread_local_session(self.login_manager.get_session())
        if not self._session:
            raise NetworkError("无法获取有效的网络会话")
            
        # 验证session有效性
        if not self._validate_session():
            raise NetworkError("Session验证失败，请重新登录")
            
        self._session_valid = True
        app_logger.success("Session管理器获取有效会话", 
                          {"cookies_count": len(self._session.cookies)})
        return self._session
    
    def _validate_session(self):
        """验证Session有效性（先看cookie，再做一次轻量请求以确认200/302）
        
        Returns:
            bool: Session是否有效
        """
        try:
            if not self._session or not self._session.cookies:
                return False
            # 检查是否有必要的cookies
            required_cookies = ['_uid', 'UID', 'lv']
            available_cookies = [cookie.name for cookie in self._session.cookies]
            has_user_cookie = any(cookie in available_cookies for cookie in required_cookies)
            if not has_user_cookie:
                return False

            # 进行轻量网络校验：避免下载大量内容，禁止重定向
            try:
                test_url = 'https://i.chaoxing.com/base'
                headers = getattr(self, 'headers', {}) or {}
                response = self._session.get(test_url, headers=headers, allow_redirects=False, timeout=8)
                # 200 认为有效；302/303/307/308 大概率跳登录页，视为无效
                if response.status_code == 200:
                    return True
                if response.status_code in (301, 302, 303, 307, 308):
                    return False
                # 其他情况（如 403/401），按无效处理
                if response.status_code in (401, 403):
                    return False
                # 保守策略：其它状态也归为无效
                return False
            except requests.exceptions.RequestException as req_err:
                app_logger.warning("Session轻量校验网络异常", {"error": str(req_err)})
                # 网络暂时异常时，保留 cookie 结果
                return True

        except Exception as e:
            app_logger.warning("Session验证失败", {"error": str(e)})
            return False
    
    def invalidate_session(self):
        """使Session无效，强制下次重新获取"""
        self._session = None
        self._session_valid = False
        app_logger.info("Session已失效，下次访问时将重新获取")
    
    def refresh_session(self):
        """刷新Session"""
        self.invalidate_session()
        return self.get_session()
