#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具方法模块
包含：相似度计算、选择器查找、文本清理等通用功能
"""

import re
from ..enterprise_logger import app_logger
from ..selectors import CHAOXING_SELECTORS


def calculate_similarity(str1, str2):
    """计算两个字符串的相似度"""
    if not str1 or not str2:
        return 0.0
    
    str1 = str1.lower().strip()
    str2 = str2.lower().strip()
    
    # 完全包含关系
    if str1 in str2:
        return 0.9
    if str2 in str1:
        return 0.8
    
    # 字符匹配
    shorter, longer = (str1, str2) if len(str1) < len(str2) else (str2, str1)
    match_count = sum(1 for char in shorter if char in longer)
    
    return match_count / len(shorter) if shorter else 0.0


def match_answer_with_options(answer, options):
    """
    将答案文本与选项进行智能匹配
    answer: 答案文本
    options: 选项列表 [{'label': 'A', 'content': '内容'}, ...]
    返回: 匹配到的选项标签，如 'A' 或 'AB'
    """
    if not answer or not options:
        return ''
    
    answer = answer.strip()
    
    # 如果答案已经是选项标签格式 (A, B, AB, ABC等)
    if re.match(r'^[A-Z]+$', answer.upper()):
        return answer.upper()
    
    # 检测多选题答案（包含分隔符）
    is_multiple = any(sep in answer for sep in ['#', '\n', '、', ',', '，'])
    
    if is_multiple:
        # 多选题：分割答案并匹配
        keywords = re.split(r'[#\n、,，]+', answer)
        matched_labels = []
        
        for keyword in keywords:
            keyword = keyword.strip()
            if not keyword:
                continue
            
            best_match = None
            best_score = 0.3  # 最小阈值
            
            for opt in options:
                similarity = calculate_similarity(keyword, opt.get('content', ''))
                if similarity > best_score:
                    best_score = similarity
                    best_match = opt.get('label', '')
            
            if best_match and best_match not in matched_labels:
                matched_labels.append(best_match)
        
        return ''.join(sorted(matched_labels))
    else:
        # 单选题：找最佳匹配
        best_match = None
        best_score = 0.3
        
        for opt in options:
            # 精确匹配
            if opt.get('content', '').strip() == answer:
                return opt.get('label', '')
            
            # 相似度匹配
            similarity = calculate_similarity(answer, opt.get('content', ''))
            if similarity > best_score:
                best_score = similarity
                best_match = opt.get('label', '')
        
        return best_match or ''


def find_by_selectors(container, selector_key, find_all=False):
    """
    使用配置的选择器列表查找元素
    selector_key: CHAOXING_SELECTORS 中的键名
    find_all: 是否返回所有匹配元素
    """
    selectors = CHAOXING_SELECTORS.get(selector_key, [])
    
    for selector in selectors:
        try:
            if find_all:
                elements = container.select(selector)
                if elements:
                    return elements
            else:
                element = container.select_one(selector)
                if element:
                    return element
        except Exception:
            continue
    
    return [] if find_all else None


def clean_text(text):
    """
    清理文本内容
    对应JS的 cleanText 方法
    """
    if not text:
        return ''
    return re.sub(r'\s+', ' ', text).strip()


def get_text_content(element):
    """
    获取纯文本内容（去除图片标签）
    对应JS的 getTextContent 方法
    """
    if not element:
        return ''
    
    # 将图片替换为占位符
    text = element.get_text(separator=' ', strip=True)
    
    return clean_text(text)
