#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用工具和常量模块
包含公共的导入、常量定义和工具函数
"""

import os
import sys
import json
import re
import tempfile
from typing import Dict, Optional, Any
from pathlib import Path

# 导入统一版本号和应用名称
from .version import __version__, APP_NAME as _APP_NAME


class PathManager:
    """统一路径管理器
    
    集中管理所有输出目录，方便打包和维护。
    所有运行时数据统一存放在 data/ 主文件夹下。
    """
    
    _app_root: Optional[Path] = None
    
    @classmethod
    def get_app_root(cls) -> Path:
        """获取应用根目录（@yingyong 目录）"""
        if cls._app_root is None:
            if getattr(sys, 'frozen', False):
                # 如果是打包环境，使用可执行文件所在目录
                cls._app_root = Path(sys.executable).parent
            else:
                # 如果是脚本环境，使用当前文件所在目录的父目录
                cls._app_root = Path(__file__).parent.parent
        return cls._app_root
    
    @classmethod
    def get_data_dir(cls) -> Path:
        """获取数据主目录（所有运行时数据的根目录）
        
        打包环境: %LOCALAPPDATA%/CXHarvest（避免 Program Files 写入权限问题）
        开发环境: 项目根目录/data
        """
        if getattr(sys, 'frozen', False):
            # 打包环境：使用 LOCALAPPDATA，避免 Program Files 写入权限问题
            local_app = os.environ.get('LOCALAPPDATA', '')
            if local_app:
                data_dir = Path(local_app) / "CXHarvest"
            else:
                data_dir = Path.home() / "AppData" / "Local" / "CXHarvest"
        else:
            # 开发环境：使用项目根目录下的 data/
            data_dir = cls.get_app_root() / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
    
    @classmethod
    def get_logs_dir(cls) -> Path:
        """获取日志目录 - 位于 data/logs/"""
        logs_dir = cls.get_data_dir() / "logs"
        logs_dir.mkdir(exist_ok=True)
        return logs_dir
    
    @classmethod
    def get_cache_dir(cls) -> Path:
        """获取缓存目录 - 位于 data/cache/"""
        cache_dir = cls.get_data_dir() / "cache"
        cache_dir.mkdir(exist_ok=True)
        return cache_dir
    
    @classmethod
    def get_config_dir(cls) -> Path:
        """获取配置目录 - 位于 data/config/"""
        config_dir = cls.get_data_dir() / "config"
        config_dir.mkdir(exist_ok=True)
        return config_dir
    
    @classmethod
    def get_temp_dir(cls) -> Path:
        """获取临时文件目录 - 位于 data/temp/"""
        temp_dir = cls.get_data_dir() / "temp"
        temp_dir.mkdir(exist_ok=True)
        return temp_dir
    
    @classmethod
    def get_exports_dir(cls) -> Path:
        """获取默认导出目录
        
        打包环境: ~/Desktop/CXHarvest_exports（用户可见、有写入权限）
        开发环境: 项目根目录/exports
        """
        if getattr(sys, 'frozen', False):
            # 打包环境：使用桌面目录，方便用户找到导出文件
            docs = Path.home() / "Desktop" / "CXHarvest_exports"
        else:
            docs = cls.get_app_root() / "exports"
        docs.mkdir(parents=True, exist_ok=True)
        return docs
    
    @classmethod
    def get_file_path(cls, filename: str, subdir: str = "data") -> Path:
        """获取指定子目录下的文件路径
        
        Args:
            filename: 文件名
            subdir: 子目录名（data, logs, cache, config, temp, exports）
            
        Raises:
            ValueError: 如果 filename 包含路径遍历字符
        """
        dir_map = {
            "data": cls.get_data_dir,
            "logs": cls.get_logs_dir,
            "cache": cls.get_cache_dir,
            "config": cls.get_config_dir,
            "temp": cls.get_temp_dir,
            "exports": cls.get_exports_dir,
        }
        if subdir not in dir_map:
            raise ValueError(f"未知的应用数据目录: {subdir}")

        get_dir = dir_map[subdir]
        base_dir = get_dir()
        resolved = (base_dir / filename).resolve()
        try:
            # Path.relative_to 按路径组件判断边界，不会把 data-backup
            # 误认为 data 的子目录（字符串 startswith 会有这个问题）。
            resolved.relative_to(base_dir.resolve())
        except ValueError:
            raise ValueError(f"路径遍历检测: {filename}")
        return resolved


# 网络相关（仅 setup_session 使用）
import requests

# 常量定义
class AppConstants:
    """应用常量"""
    
    # 应用信息 - 统一使用 version.py 中的值
    APP_NAME = _APP_NAME
    APP_VERSION = __version__
    ORGANIZATION = "重庆彭于晏"
    
    # 文件名常量
    LOGIN_INFO_FILE = "login_info.json"
    COURSES_CACHE_FILE = "courses.json"
    HOMEWORK_COUNT_CACHE_FILE = "homework_counts.json"
    SESSION_FILE = "session.txt"
    
    # 网络常量
    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    # UI 常量
    CARD_WIDTH = 220
    CARD_HEIGHT = 200
    DEFAULT_FONT_SIZE = 9
    DEFAULT_FONT_FAMILY = "Microsoft YaHei"
    
    # 超星学习通URL常量
    BASE_URL = "https://passport2.chaoxing.com"
    LOGIN_URL = f"{BASE_URL}/fanyalogin"
    CAPTCHA_URL = f"{BASE_URL}/num/code"
    COURSE_LIST_URL = "https://mooc2-ans.chaoxing.com/mooc2-ans/visit/courselistdata"
    HOMEWORK_LIST_BASE_URL = "https://mooc1.chaoxing.com/mooc2/work/list"


# =============================================================================
# 题目数据字段标准化
# =============================================================================
# 为了兼容不同模块使用的字段名，定义统一的字段映射
QUESTION_FIELD_ALIASES = {
    # 标准字段名: [可能的别名列表]
    'question_type': ['question_type', 'type'],
    'correct_answer': ['correct_answer', 'answer'],
    'correct_answer_images': ['correct_answer_images', 'answerImages'],
    'my_answer': ['my_answer', 'myAnswer'],
    'my_answer_images': ['my_answer_images', 'myAnswerImages'],
    'content': ['content', 'title'],
    'content_images': ['content_images', 'title_images', 'contentImages'],
    'option_images': ['option_images', 'optionImages'],
    'score': ['score', '得分'],
    'total_score': ['total_score', 'totalScore', '满分'],
    'is_correct': ['is_correct', 'isCorrect'],
    'explanation': ['explanation', 'analysis'],
    'explanation_images': ['explanation_images', 'analysisImages'],
}


def get_question_field(q: Dict, field: str, default=None):
    """统一获取题目字段值，自动处理字段别名
    
    Args:
        q: 题目字典
        field: 标准字段名
        default: 默认值
    
    Returns:
        字段值，如果都不存在则返回default
    """
    aliases = QUESTION_FIELD_ALIASES.get(field, [field])
    for alias in aliases:
        if alias in q:
            value = q.get(alias)

            if value is None:
                continue

            if isinstance(value, str) and not value.strip():
                continue

            if isinstance(value, (list, dict, set, tuple)) and not value:
                continue

            return value
    return default


from .exceptions import AppError, LoginError, NetworkError, ParseError

def sanitize_filename(filename: str, max_length: int = 180) -> str:
    """返回可安全用于 Windows/macOS/Linux 的单个文件名。

    路径分隔符、控制字符和 Windows 非法字符会被替换；空名称及
    Windows 保留设备名会得到安全的回退值。返回值永远不包含目录。
    """
    value = str(filename or "")
    value = re.sub(r'[\x00-\x1f\\/:*?"<>|]', '_', value)
    value = value.strip().rstrip(". ")

    if not value or value in {".", ".."}:
        value = "untitled"

    reserved_names = {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if value.split(".", 1)[0].upper() in reserved_names:
        value = f"_{value}"

    if max_length < 1:
        raise ValueError("max_length 必须大于 0")
    value = value[:max_length].rstrip(". ")
    return value or "untitled"

def safe_json_load(file_path, default=None) -> Any:
    """安全加载JSON文件（接受 str 或 Path）"""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        from .enterprise_logger import app_logger
        app_logger.error(f"加载JSON文件失败 {file_path}: {e}")
    return default if default is not None else {}

def safe_json_save(data: Any, file_path) -> bool:
    """原子保存 JSON 文件（接受 str 或 Path）。

    先写入目标目录内的临时文件，再通过 ``os.replace`` 一次性替换，
    避免程序退出或写入失败时留下半截 JSON。
    """
    temp_path = None
    try:
        target = Path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', dir=str(target.parent),
            prefix=f".{target.name}.", suffix=".tmp", delete=False
        ) as f:
            temp_path = Path(f.name)
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(temp_path), str(target))
        return True
    except Exception as e:
        from .enterprise_logger import app_logger
        app_logger.error(f"保存JSON文件失败 {file_path}: {e}")
        return False
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass

def setup_session() -> requests.Session:
    """创建配置好的requests会话"""
    session = requests.Session()
    session.headers.update(AppConstants.DEFAULT_HEADERS)
    session.verify = True
    return session

