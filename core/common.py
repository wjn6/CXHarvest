#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用工具和常量模块
包含公共的导入、常量定义和工具函数
"""

import os
import sys
import json
import time
import re
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
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
        """获取数据主目录（所有运行时数据的根目录）"""
        data_dir = cls.get_app_root() / "data"
        data_dir.mkdir(exist_ok=True)
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
        """获取默认导出目录"""
        exports_dir = cls.get_app_root() / "exports"
        exports_dir.mkdir(exist_ok=True)
        return exports_dir
    
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
        get_dir = dir_map.get(subdir, cls.get_data_dir)
        base_dir = get_dir()
        resolved = (base_dir / filename).resolve()
        if not str(resolved).startswith(str(base_dir.resolve())):
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

@dataclass
class CourseInfo:
    """课程信息数据类"""
    id: str
    name: str
    teacher: str
    description: str = ""
    link: str = ""
    image: str = ""
    progress: str = "0%"
    homework_count: int = 0
    status: str = "进行中"

@dataclass
class HomeworkInfo:
    """作业信息数据类"""
    id: str
    title: str
    url: str
    status: str = "未知状态"
    deadline: str = ""
    score: str = ""
    submit_status: str = ""
    description: str = ""
    course_name: str = ""


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

def sanitize_filename(filename: str) -> str:
    """清理文件名中的非法字符（公共工具函数）"""
    return re.sub(r'[\\/:*?"<>|]', '_', filename)

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
    """安全保存JSON文件（接受 str 或 Path）"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        from .enterprise_logger import app_logger
        app_logger.error(f"保存JSON文件失败 {file_path}: {e}")
        return False

def format_timestamp(timestamp: Optional[float] = None) -> str:
    """格式化时间戳"""
    if timestamp is None:
        timestamp = time.time()
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))

def extract_course_id_from_url(url: str) -> Optional[str]:
    """从URL中提取课程ID"""
    try:
        match = re.search(r'courseid=(\d+)', url)
        return match.group(1) if match else None
    except Exception:
        return None

def validate_phone_number(phone: str) -> bool:
    """验证手机号格式"""
    pattern = r'^1[3-9]\d{9}$'
    return bool(re.match(pattern, phone))

def validate_email(email: str) -> bool:
    """验证邮箱格式"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def setup_session() -> requests.Session:
    """创建配置好的requests会话"""
    session = requests.Session()
    session.headers.update(AppConstants.DEFAULT_HEADERS)
    session.verify = True
    return session

