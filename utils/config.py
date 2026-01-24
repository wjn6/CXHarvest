#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理工具
为兼容历史导入，此模块代理到 core.config_manager
"""

from core.config_manager import ConfigManager, get_config_manager

# 全局配置实例
config = get_config_manager()

__all__ = ['ConfigManager', 'config', 'get_config_manager']