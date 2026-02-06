#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块
提供统一的应用配置管理功能
"""

import os
import json
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

from .common import safe_json_load, safe_json_save, AppConstants
from .enterprise_logger import app_logger

@dataclass
class NetworkConfig:
    """网络配置"""
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    verify_ssl: bool = True
    max_connections: int = 10

@dataclass
class ImageConfig:
    """图片处理配置"""
    max_cache_size: int = 100
    max_image_size: int = 1024
    compress_images: bool = True
    image_quality: int = 85

@dataclass
class UIConfig:
    """UI配置"""
    theme: str = "light"
    font_size: int = 14
    font_family: str = "Microsoft YaHei"
    window_width: int = 1400
    window_height: int = 900
    auto_save_layout: bool = True

@dataclass
class ExportConfig:
    """导出配置"""
    default_format: str = "markdown"
    include_images: bool = True
    include_answers: bool = True
    include_explanations: bool = True
    output_directory: str = "exports"

@dataclass
class AppConfig:
    """应用配置"""
    debug: bool = False
    log_level: str = "信息"
    auto_check_updates: bool = True
    save_login_info: bool = False
    network: NetworkConfig = None
    image: ImageConfig = None
    ui: UIConfig = None
    export: ExportConfig = None
    
    def __post_init__(self):
        if self.network is None:
            self.network = NetworkConfig()
        if self.image is None:
            self.image = ImageConfig()
        if self.ui is None:
            self.ui = UIConfig()
        if self.export is None:
            self.export = ExportConfig()

class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_file: str = "app_config.json"):
        """初始化配置管理器
        
        Args:
            config_file: 配置文件名（将存储在 data/config/ 目录下）
        """
        from .common import PathManager
        self.config_file = str(PathManager.get_config_dir() / config_file)
        self._config = AppConfig()
        self._loaded = False
        
    def load_config(self) -> AppConfig:
        """加载配置文件
        
        Returns:
            应用配置对象
        """
        try:
            if os.path.exists(self.config_file):
                config_data = safe_json_load(self.config_file, {})
                if config_data:
                    self._config = self._dict_to_config(config_data)
                    app_logger.info(f" 配置已从 {self.config_file} 加载")
                else:
                    app_logger.info(" 配置文件为空，使用默认配置")
            else:
                app_logger.info(f"配置文件不存在，创建默认配置: {self.config_file}")
                self.save_config()
                
            self._loaded = True
            return self._config
            
        except Exception as e:
            app_logger.error(f" 加载配置失败: {e}")
            app_logger.info(" 使用默认配置")
            return self._config
    
    def save_config(self) -> bool:
        """保存配置到文件
        
        Returns:
            是否保存成功
        """
        try:
            config_data = self._config_to_dict(self._config)
            success = safe_json_save(config_data, self.config_file)
            if success:
                app_logger.info(f" 配置已保存到 {self.config_file}")
            return success
            
        except Exception as e:
            app_logger.error(f" 保存配置失败: {e}")
            return False
    
    def get_config(self) -> AppConfig:
        """获取当前配置
        
        Returns:
            应用配置对象
        """
        if not self._loaded:
            return self.load_config()
        return self._config
    
    def update_config(self, **kwargs) -> bool:
        """更新配置项
        
        Args:
            **kwargs: 配置项键值对
            
        Returns:
            是否更新成功
        """
        try:
            for key, value in kwargs.items():
                if hasattr(self._config, key):
                    setattr(self._config, key, value)
                    app_logger.info(f" 配置项已更新: {key} = {value}")
                else:
                    app_logger.info(f" 未知配置项: {key}")
                    
            return self.save_config()
            
        except Exception as e:
            app_logger.error(f" 更新配置失败: {e}")
            return False
    
    def reset_config(self) -> bool:
        """重置为默认配置
        
        Returns:
            是否重置成功
        """
        try:
            self._config = AppConfig()
            success = self.save_config()
            if success:
                app_logger.info(" 配置已重置为默认值")
            return success
            
        except Exception as e:
            app_logger.error(f" 重置配置失败: {e}")
            return False
    
    def _config_to_dict(self, config: AppConfig) -> Dict[str, Any]:
        """将配置对象转换为字典"""
        return {
            'debug': config.debug,
            'log_level': config.log_level,
            'auto_check_updates': config.auto_check_updates,
            'save_login_info': config.save_login_info,
            'network': asdict(config.network),
            'image': asdict(config.image),
            'ui': asdict(config.ui),
            'export': asdict(config.export)
        }
    
    def _dict_to_config(self, data: Dict[str, Any]) -> AppConfig:
        """将字典转换为配置对象"""
        config = AppConfig()
        
        # 基本配置
        config.debug = data.get('debug', config.debug)
        config.log_level = data.get('log_level', config.log_level)
        config.auto_check_updates = data.get('auto_check_updates', config.auto_check_updates)
        config.save_login_info = data.get('save_login_info', config.save_login_info)
        
        # 网络配置
        network_data = data.get('network', {})
        config.network = NetworkConfig(
            timeout=network_data.get('timeout', 30),
            max_retries=network_data.get('max_retries', 3),
            retry_delay=network_data.get('retry_delay', 1.0),
            verify_ssl=network_data.get('verify_ssl', True),
            max_connections=network_data.get('max_connections', 10)
        )
        
        # 图片配置
        image_data = data.get('image', {})
        config.image = ImageConfig(
            max_cache_size=image_data.get('max_cache_size', 100),
            max_image_size=image_data.get('max_image_size', 1024),
            compress_images=image_data.get('compress_images', True),
            image_quality=image_data.get('image_quality', 85)
        )
        
        # UI配置
        ui_data = data.get('ui', {})
        config.ui = UIConfig(
            theme=ui_data.get('theme', 'light'),
            font_size=ui_data.get('font_size', 14),
            font_family=ui_data.get('font_family', 'Microsoft YaHei'),
            window_width=ui_data.get('window_width', 1400),
            window_height=ui_data.get('window_height', 900),
            auto_save_layout=ui_data.get('auto_save_layout', True)
        )
        
        # 导出配置
        export_data = data.get('export', {})
        config.export = ExportConfig(
            default_format=export_data.get('default_format', 'markdown'),
            include_images=export_data.get('include_images', True),
            include_answers=export_data.get('include_answers', True),
            include_explanations=export_data.get('include_explanations', True),
            output_directory=export_data.get('output_directory', 'exports')
        )
        
        return config
    
    def get_network_config(self) -> NetworkConfig:
        """获取网络配置"""
        return self.get_config().network
    
    def get_image_config(self) -> ImageConfig:
        """获取图片配置"""
        return self.get_config().image
    
    def get_ui_config(self) -> UIConfig:
        """获取UI配置"""
        return self.get_config().ui
    
    def get_export_config(self) -> ExportConfig:
        """获取导出配置"""
        return self.get_config().export
    
    def is_debug_mode(self) -> bool:
        """是否为调试模式"""
        return self.get_config().debug
    
    def get_log_level(self) -> str:
        """获取日志级别"""
        return self.get_config().log_level

# 全局配置管理器实例
_config_manager = ConfigManager()

def get_config_manager() -> ConfigManager:
    """获取全局配置管理器实例"""
    return _config_manager

def get_app_config() -> AppConfig:
    """便捷函数：获取应用配置"""
    return _config_manager.get_config()

def update_app_config(**kwargs) -> bool:
    """便捷函数：更新应用配置"""
    return _config_manager.update_config(**kwargs)


