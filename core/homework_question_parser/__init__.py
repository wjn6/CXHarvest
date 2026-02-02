#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
超星学习通作业题目解析器 - 模块化版本

整合 v1.31chaoxing.js、OCS、chaoxing_scrapper 等脚本的优秀技术
支持：混排内容解析、智能选项识别、答案相似度匹配、图片嵌入等高级功能

模块结构:
- parser.py: 主解析器类 HomeworkQuestionParser
- content_extractor.py: 内容提取（混排解析、选项提取、答案提取）
- image_handler.py: 图片处理（Base64转换、图片提取）
- type_detector.py: 题型识别（OCS策略、关键词识别）
- utils.py: 工具方法（相似度计算、选择器查找）

使用方式（向后兼容）:
    from core.homework_question_parser import HomeworkQuestionParser
    
    parser = HomeworkQuestionParser(login_manager)
    questions = parser.parse_homework_questions(url, title)
"""

from .parser import HomeworkQuestionParser
from .image_handler import ImageHandler
from .type_detector import TypeDetector
from .content_extractor import ContentExtractor
from .utils import (
    calculate_similarity,
    match_answer_with_options,
    find_by_selectors,
    clean_text,
    get_text_content
)

__all__ = [
    'HomeworkQuestionParser',
    'ImageHandler',
    'TypeDetector', 
    'ContentExtractor',
    'calculate_similarity',
    'match_answer_with_options',
    'find_by_selectors',
    'clean_text',
    'get_text_content'
]

__version__ = '3.0.0'
