#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
超星学习通作业题目解析器 - 史诗级增强版
整合 v1.31chaoxing.js、OCS、chaoxing_scrapper 等脚本的优秀技术
支持：混排内容解析、智能选项识别、答案相似度匹配、图片嵌入等高级功能
"""

import os
import json
import base64
import requests
from bs4 import BeautifulSoup, NavigableString, Tag
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
from PIL import Image
import io
import time
from copy import copy
from .enterprise_logger import app_logger


# =====================================================================
# OCS 题型值映射系统 (来自 ocs.common.user.js)
# =====================================================================
OCS_QUESTION_TYPE_MAP = {
    0: '单选题',
    1: '多选题', 
    2: '填空题',
    3: '判断题',
    4: '简答题',
    5: '填空题',  # 名词解释
    6: '填空题',  # 论述题
    7: '填空题',  # 计算题
    8: '填空题',  # 分录题
    9: '填空题',  # 资料题
    10: '填空题', # 其他
    11: '连线题',
    14: '完形填空',
    15: '阅读理解'
}

# =====================================================================
# 超全学习通DOM选择器配置 (整合所有脚本)
# =====================================================================
CHAOXING_SELECTORS = {
    # 题目容器选择器（按优先级排序）
    # 注意：.questionLi 是单个题目容器，.mark_item 是题型分组容器
    'question_containers': [
        '.questionLi',          # 单个题目容器（最精确，优先）
        '.TiMu',                # 常见变体
        '.Py-mian1',            # 考试页面
        '.queBox',              # 问答框
        '.stem_question',       # 题干容器
        'div[data]',            # 带题目ID
        '.mark_item',           # 题型分组容器（放最后）
    ],
    # 题目标题/内容选择器
    'question_title': [
        '.mark_name',           # 标准
        'h3.mark_name',         # 精确h3
        '.qtContent',           # 内容区
        '.Zy_TItle',            # 作业标题
        '.newZy_TItle',         # 新版标题
        '.Cy_TItle',            # 测验标题
        '.stem',                # 题干
        '.question-stem',       # 题干变体
    ],
    # 选项选择器
    'options': [
        '.mark_letter li',      # 标准选项
        '.mark_letter div',     # div选项
        '.answerBg .answer_p',  # OCS选项
        '.textDIV',             # 文本选项
        '.eidtDiv',             # 编辑区选项
        '.Zy_ulTop li',         # 作业选项
        '.ulAnswer li',         # 答案列表
        '.optionUl li',         # 选项列表
        '.qtDetail li',         # 详情选项
        '.radio-view li.clearfix',  # 单选视图
        '.checklist-view label',    # 多选视图
    ],
    # 我的答案选择器
    'my_answer': [
        '.stuAnswerContent',    # 标准
        '.colorDeep dd',        # 深色答案
        '.answerCon',           # 答案内容
        '.myAnswer',            # 我的答案
    ],
    # 正确答案选择器
    'correct_answer': [
        '.rightAnswerContent',  # 标准
        '.colorGreen dd',       # 绿色答案
        '.answer',              # 答案
        '.key',                 # 答案键
        '.rightAnswer',         # 正确答案
    ],
    # 解析选择器
    'explanation': [
        '.qtAnalysis',          # 题目解析
        '.mark_explain',        # 解释
        '.analysis',            # 分析
        '.explanation',         # 解释
    ],
    # 得分选择器
    'score': [
        '.totalScore i',        # 总分
        '.mark_score i',        # 分数
        '.score',               # 分数
    ],
    # 正确/错误标记选择器
    'correct_mark': [
        '.marking_dui',         # 对勾
        '.correct',             # 正确
        '.right',               # 对
    ],
    'wrong_mark': [
        '.marking_cuo',         # 叉号
        '.wrong',               # 错误
        '.error',               # 错
    ],
    # 题型标记选择器
    'question_type': [
        '.colorShallow',        # 浅色标记
        'input[id^="answertype"]',  # OCS类型
        'input[name^="type"]',  # 类型输入
    ],
}


class HomeworkQuestionParser:
    """超星学习通作业题目解析器"""
    
    def __init__(self, login_manager=None):
        """初始化解析器"""
        self.login_manager = login_manager
        self.homework_list = []
        self.all_questions = []
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'
        }
        app_logger.success("题目解析器初始化完成 (史诗级增强版)")

    # =====================================================================
    # 核心增强功能：混排内容解析 (来自 v1.31chaoxing.js parseMixedContent)
    # =====================================================================
    def parse_mixed_content(self, element):
        """
        解析混排内容，保持文字和图片的原始顺序
        返回: {'text': 纯文本, 'html': 带图片占位符的HTML, 'items': 混排项列表}
        """
        if not element:
            return {'text': '', 'html': '', 'items': []}
        
        items = []
        text_parts = []
        html_parts = []
        
        try:
            # 遍历所有子节点，保持顺序
            for child in element.children:
                if isinstance(child, NavigableString):
                    # 文本节点
                    text = str(child).strip()
                    if text:
                        items.append({'type': 'text', 'content': text})
                        text_parts.append(text)
                        html_parts.append(text)
                elif isinstance(child, Tag):
                    if child.name == 'img':
                        # 图片节点
                        src = child.get('src', '')
                        alt = child.get('alt', '图片')
                        if src:
                            base64_data = self.get_image_as_base64(src)
                            items.append({
                                'type': 'image',
                                'src': src,
                                'alt': alt,
                                'data': base64_data
                            })
                            text_parts.append(f'[图片:{alt}]')
                            html_parts.append(f'<img src="{base64_data or src}" alt="{alt}"/>')
                    elif child.name == 'br':
                        items.append({'type': 'br'})
                        text_parts.append('\n')
                        html_parts.append('<br/>')
                    elif child.name == 'p':
                        # 段落标签，处理后添加换行
                        sub_result = self.parse_mixed_content(child)
                        items.extend(sub_result['items'])
                        items.append({'type': 'br'})
                        text_parts.append(sub_result['text'])
                        text_parts.append('\n')
                        html_parts.append(sub_result['html'])
                        html_parts.append('<br/>')
                    else:
                        # 递归处理子元素
                        sub_result = self.parse_mixed_content(child)
                        items.extend(sub_result['items'])
                        text_parts.append(sub_result['text'])
                        html_parts.append(sub_result['html'])
        except Exception as e:
            app_logger.warning(f"解析混排内容失败: {e}")
            # 降级处理
            return {
                'text': element.get_text(strip=True),
                'html': str(element),
                'items': [{'type': 'text', 'content': element.get_text(strip=True)}]
            }
        
        # 合并文本，保留换行符
        combined_text = ''.join(text_parts)
        # 清理多余换行但保留单个换行
        combined_text = re.sub(r'\n{3,}', '\n\n', combined_text)
        combined_text = combined_text.strip()
        
        return {
            'text': combined_text,
            'html': ''.join(html_parts),
            'items': items
        }

    # =====================================================================
    # 核心增强功能：智能选项解析 (来自 v1.31chaoxing.js parseOptionContent)
    # =====================================================================
    def parse_option_content(self, option_element):
        """
        智能解析选项内容，自动识别纯图片选项、纯文本选项、混排选项
        返回: {'label': 'A', 'content': 内容, 'is_image_only': bool, 'images': []}
        """
        if not option_element:
            return None
        
        try:
            # 获取所有图片
            images = option_element.find_all('img')
            text = option_element.get_text(strip=True)
            
            # 尝试提取选项标签 (A, B, C, D...)
            label = ''
            label_match = re.match(r'^([A-Z])[\.、\s：:]', text)
            if label_match:
                label = label_match.group(1)
                text = text[len(label_match.group(0)):].strip()
            
            # 判断选项类型
            has_images = len(images) > 0
            has_text = len(text) > 0 and text not in ['', ' ']
            
            # 处理图片
            image_data_list = []
            for img in images:
                src = img.get('src', '')
                if src:
                    base64_data = self.get_image_as_base64(src)
                    image_data_list.append({
                        'src': src,
                        'alt': img.get('alt', '选项图片'),
                        'data': base64_data
                    })
            
            # 确定选项类型和内容
            if has_images and not has_text:
                # 纯图片选项
                return {
                    'label': label,
                    'content': f'[图片选项: {len(images)}张]',
                    'is_image_only': True,
                    'images': image_data_list,
                    'mixed_content': self.parse_mixed_content(option_element)
                }
            elif has_images and has_text:
                # 混排选项
                return {
                    'label': label,
                    'content': text,
                    'is_image_only': False,
                    'images': image_data_list,
                    'mixed_content': self.parse_mixed_content(option_element)
                }
            else:
                # 纯文本选项
                return {
                    'label': label,
                    'content': text,
                    'is_image_only': False,
                    'images': [],
                    'mixed_content': {'text': text, 'html': text, 'items': [{'type': 'text', 'content': text}]}
                }
        except Exception as e:
            app_logger.warning(f"解析选项内容失败: {e}")
            return {
                'label': '',
                'content': option_element.get_text(strip=True),
                'is_image_only': False,
                'images': [],
                'mixed_content': None
            }

    # =====================================================================
    # 核心增强功能：答案相似度匹配 (来自 chaoxing_scrapper matchAnswerWithOptions)
    # =====================================================================
    def calculate_similarity(self, str1, str2):
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

    def match_answer_with_options(self, answer, options):
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
                    similarity = self.calculate_similarity(keyword, opt.get('content', ''))
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
                similarity = self.calculate_similarity(answer, opt.get('content', ''))
                if similarity > best_score:
                    best_score = similarity
                    best_match = opt.get('label', '')
            
            return best_match or ''

    # =====================================================================
    # 核心增强功能：使用配置的选择器查找元素
    # =====================================================================
    def find_by_selectors(self, container, selector_key, find_all=False):
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

    # =====================================================================
    # 核心增强功能：OCS题型识别
    # =====================================================================
    def determine_question_type_ocs(self, container):
        """
        使用OCS策略识别题目类型
        优先级: 隐藏input值 > colorShallow标记 > 文本关键词 > 选项推断
        """
        try:
            # 策略1: 查找隐藏的题型input
            type_input = container.select_one('input[id^="answertype"]') or \
                        container.select_one('input[name^="type"]')
            
            if type_input and type_input.get('value'):
                try:
                    val = int(float(type_input.get('value')))
                    if val in OCS_QUESTION_TYPE_MAP:
                        return OCS_QUESTION_TYPE_MAP[val]
                except (ValueError, TypeError):
                    pass
            
            # 策略2: 从colorShallow提取
            color_shallow = container.select_one('.colorShallow')
            if color_shallow:
                type_text = color_shallow.get_text(strip=True)
                type_text = re.sub(r'[\(\)\（\）\[\]\【\】]', '', type_text).strip()
                if type_text and '题' in type_text:
                    return type_text
            
            # 策略3: 从题目文本中提取
            text_content = container.get_text().lower()
            type_keywords = [
                ('单选题', ['单选题', 'single', '单选']),
                ('多选题', ['多选题', 'multiple', '多选']),
                ('判断题', ['判断题', 'true', 'false', '判断']),
                ('填空题', ['填空题', 'blank', '填空']),
                ('简答题', ['简答题', '问答题', 'essay', '简答', '论述']),
            ]
            
            for type_name, keywords in type_keywords:
                if any(kw in text_content for kw in keywords):
                    return type_name
            
            # 策略4: 根据选项类型推断
            radios = container.select('input[type="radio"]')
            checkboxes = container.select('input[type="checkbox"]')
            
            if checkboxes:
                return '多选题'
            elif radios:
                return '判断题' if len(radios) == 2 else '单选题'
            elif re.search(r'[ABCD][\.、]', text_content):
                options_count = len(re.findall(r'[ABCD][\.、]', text_content))
                return '单选题' if options_count <= 4 else '多选题'
            
            return '简答题'
            
        except Exception as e:
            app_logger.warning(f"OCS题型识别失败: {e}")
            return '未知'

    def check_login(self):
        """检查登录状态"""
        try:
            if not self.login_manager:
                app_logger.info(" 未提供登录管理器")
                return False
            
            user_info = self.login_manager.get_user_info()
            if user_info and user_info.get('name'):
                app_logger.info(f"登录状态正常，用户: {user_info.get('name')}")
                return True
            else:
                app_logger.info("登录状态已失效")
                return False
        except Exception as e:
            app_logger.error(f"检查登录状态失败: {e}")
            return False

    def load_homework_list(self):
        """加载作业列表"""
        try:
            if not os.path.exists('homework_list.json'):
                app_logger.info("未找到 homework_list.json 文件")
                app_logger.info("   请先在主界面选择课程并查看作业列表")
                return False

            with open('homework_list.json', 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, list):
                self.homework_list = data
                app_logger.success(f"从 homework_list.json 成功加载 {len(self.homework_list)} 个作业")
                return True
            else:
                app_logger.info("homework_list.json 格式不正确，应该是数组格式")
                return False
        except Exception as e:
            app_logger.error(f"加载作业列表失败: {e}")
            return False

    def get_image_as_base64(self, url):
        """将图片转换为Base64编码"""
        try:
            if not url or not url.strip():
                return None
            
            # 对于已经是base64的数据，直接返回
            if url.startswith('data:image'):
                return url
            
            # 处理相对路径，强制使用HTTPS
            if url.startswith('//'):
                safe_url = 'https:' + url
            elif url.startswith('/'):
                safe_url = 'https://mooc1.chaoxing.com' + url
            elif url.startswith('http://'):
                safe_url = url.replace('http://', 'https://')
            else:
                safe_url = url
            
            # 使用登录管理器的session获取图片
            if self.login_manager and hasattr(self.login_manager, 'session'):
                session = self.login_manager.session
                headers = {**self.headers, 'Referer': 'https://i.chaoxing.com/'}
                response = session.get(safe_url, headers=headers, timeout=10, verify=False)
                response.raise_for_status()
                
                # 获取图片内容类型
                content_type = response.headers.get('content-type', 'image/png')
                if not content_type.startswith('image/'):
                    content_type = 'image/png'
                
                # 转换为Base64
                image_base64 = base64.b64encode(response.content).decode('utf-8')
                data_url = f"data:{content_type};base64,{image_base64}"
                
                return data_url
            else:
                app_logger.info("无法获取登录session")
                return url
            
        except Exception as e:
            app_logger.error(f"转换图片到Base64失败 {url}: {e}")
            return url  # 如果转换失败，返回原始URL

    def extract_images_from_element(self, element):
        """从指定元素中提取图片并转换为Base64"""
        images = []
        if not element:
            return images
        
        try:
            # 查找该元素内的所有图片
            img_elements = element.find_all('img')
            unique_urls = set()
            
            for img in img_elements:
                src = img.get('src')
                if src and src not in unique_urls:
                    unique_urls.add(src)
                    
                    # 获取图片的Base64编码
                    base64_data = self.get_image_as_base64(src)
                    
                    # 尝试获取图片尺寸
                    width = height = 0
                    try:
                        if base64_data and base64_data.startswith('data:image'):
                            image_data = base64_data.split(',')[1]
                            image_bytes = base64.b64decode(image_data)
                            with Image.open(io.BytesIO(image_bytes)) as pil_img:
                                width, height = pil_img.size
                    except Exception:
                        pass  # 忽略尺寸获取错误
                    
                    images.append({
                        'src': src,
                        'alt': img.get('alt', '图片'),
                        'data': base64_data,
                        'width': width,
                        'height': height
                    })
            
        except Exception as e:
            app_logger.error(f"从元素提取图片失败: {e}")
        
        return images

    def determine_question_type(self, container):
        """判断题目类型"""
        try:
            # 方法0: 优先从 colorShallow span 提取 (如 "(简答题)")
            color_shallow = container.find('span', class_='colorShallow')
            if color_shallow:
                type_text = color_shallow.get_text(strip=True)
                # 移除括号
                type_text = re.sub(r'[\(\)\（\）\[\]]', '', type_text).strip()
                if type_text:
                    return type_text
            
            # OCS策略：检查隐藏的 input 标签值
            # type: type === "exam" ? 'input[name^="type"]' : 'input[id^="answertype"]'
            type_input = container.find('input', id=re.compile(r'^answertype')) or \
                         container.find('input', attrs={'name': re.compile(r'^type')})
            
            if type_input and type_input.get('value'):
                try:
                    val = int(float(type_input.get('value')))
                    # 映射关系参考 ocs.common.user.js getQuestionType
                    if val == 0: return '单选题'
                    if val == 1: return '多选题'
                    if val == 3: return '判断题'
                    if val == 4: return '简答题'
                    if val in [2, 5, 6, 7, 8, 9, 10]: return '填空题'
                    if val == 11: return '连线题'
                    if val == 14: return '完形填空'
                    if val == 15: return '阅读理解'
                except (ValueError, TypeError):
                    pass

            text_content = container.get_text().lower()
            
            # 判断题目类型的关键词
            if any(keyword in text_content for keyword in ['单选题', 'single', '单选']):
                return '单选题'
            elif any(keyword in text_content for keyword in ['多选题', 'multiple', '多选']):
                return '多选题'
            elif any(keyword in text_content for keyword in ['判断题', 'true', 'false', '判断']):
                return '判断题'
            elif any(keyword in text_content for keyword in ['填空题', 'blank', '填空']):
                return '填空题'
            elif any(keyword in text_content for keyword in ['简答题', '问答题', 'essay', '简答', '论述']):
                return '简答题'
            else:
                # 根据选项判断
                if re.search(r'[ABCD][\.、]', text_content):
                    return '单选题' if len(re.findall(r'[ABCD][\.、]', text_content)) <= 4 else '多选题'
                elif re.search(r'[√×✓✗对错是否][\.、]?', text_content):
                    return '判断题'
                else:
                    return '简答题'
        except Exception as e:
            app_logger.error(f"判断题目类型失败: {e}")
            return '未知'

    def is_valid_question(self, text):
        """判断是否为有效题目 - 宽松策略，优先保留题目"""
        if not text:
            return False
        
        text = text.strip()
        
        # 长度太短直接拒绝
        if len(text) < 2:
            return False
        
        # ========== 明确排除的无效内容 ==========
        invalid_patterns = [
            r'^[一二三四五六七八九十]+[\.、]\s*[单多判填问简论].*题.*共?\d+.*分',  # 题型分组标题
            r'^[一二三四五六七八九十]+[\.、]\s*[单多判填问简论].*题.*\d+题',      # 题型统计
            r'^\d+\.\d+分$',             # 纯分数如 "2.5分"
            r'^总分[：:]\s*\d+',          # 总分信息
            r'^得分[：:]\s*\d+',          # 得分信息
            r'^满分[：:]\s*\d+',          # 满分信息
            r'^共\d+题',                  # "共10题"
            r'^本大题共\d+',              # "本大题共..."
        ]
        
        for pattern in invalid_patterns:
            if re.match(pattern, text, re.IGNORECASE):
                return False
        
        # ========== 宽松的有效题目判断 ==========
        # 策略1: 以数字序号开头
        if re.match(r'^\d+[\.、\s\)]', text):
            return True
        
        # 策略2: 包含题型标记
        if re.search(r'[\(\（\[\【][单多判填问简论].*?题[\)\）\]\】]', text):
            return True
        
        # 策略3: 以括号序号开头
        if re.match(r'^[\(\（]\d+[\)\）]', text):
            return True
        
        # 策略4: 包含问号（很可能是题目）
        if '?' in text or '？' in text:
            return True
        
        # 策略5: 包含选项标记
        if re.search(r'[ABCD][\.、\s]', text):
            return True
        
        # 策略6: 长度足够（>10字符），且不是纯数字/符号
        if len(text) > 10 and re.search(r'[\u4e00-\u9fff]', text):
            return True
        
        # 策略7: 包含常见题目关键词
        question_keywords = ['下列', '以下', '关于', '属于', '不属于', '正确', '错误', 
                            '选择', '判断', '说法', '描述', '表述', '理解', '分析',
                            '计算', '解答', '简述', '论述', '请', '试']
        if any(kw in text for kw in question_keywords):
            return True
        
        # 策略8: 最后的宽松判断 - 只要有中文内容且长度>5
        if len(text) > 5 and re.search(r'[\u4e00-\u9fff]', text):
            return True
        
        return False

    def extract_question_text(self, container):
        """提取题目文本 - 多策略增强版"""
        try:
            # 辅助函数：清洗题目文本
            def clean_text(raw_text):
                if not raw_text:
                    return ''
                # 截断答案部分
                separators = ['我的答案', '正确答案', '答案解析', 'Answer:', 'Correct Answer:', '我的答案：', '正确答案：']
                for sep in separators:
                    if sep in raw_text:
                        raw_text = raw_text.split(sep)[0]
                return raw_text.strip()

            # ========== 策略1: .mark_name 元素（最常用） ==========
            mark_name = container.find(class_='mark_name')
            if mark_name:
                text = mark_name.get_text(strip=True)
                text = clean_text(text)
                if text and len(text) > 3:
                    return text
            
            # ========== 策略2: h3 标题元素（OCS策略） ==========
            h3_title = container.find('h3')
            if h3_title:
                full_text = h3_title.get_text(strip=True)
                # 移除开头的题号和题型标记
                cleaned = re.sub(r'^\d+[\.、\s\)]+\s*', '', full_text)
                cleaned = re.sub(r'^[\[\(\（\【].*?题[\]\)\）\】]\s*', '', cleaned)
                cleaned = clean_text(cleaned)
                if cleaned and len(cleaned) > 3:
                    return cleaned
            
            # ========== 策略3: .qtContent 元素（保留换行） ==========
            qt_content = container.find(class_='qtContent')
            if qt_content:
                # 使用 separator='\n' 保留换行
                text = qt_content.get_text(separator='\n').strip()
                # 清理多余换行
                text = re.sub(r'\n{3,}', '\n\n', text)
                text = clean_text(text)
                if text and len(text) > 3:
                    return text
            
            # ========== 策略4: .Zy_TItle / .newZy_TItle 元素 ==========
            for cls in ['Zy_TItle', 'newZy_TItle', 'Cy_TItle']:
                zy_title = container.find(class_=cls)
                if zy_title:
                    text = zy_title.get_text(strip=True)
                    text = clean_text(text)
                    if text and len(text) > 3:
                        return text
            
            # ========== 策略5: .TiMu 元素 ==========
            timu = container.find(class_='TiMu')
            if timu:
                text = timu.get_text(strip=True)
                text = clean_text(text)
                if text and len(text) > 3:
                    return text
            
            # ========== 策略6: .stem / .stem_question 元素 ==========
            for cls in ['stem', 'stem_question', 'question-stem']:
                stem = container.find(class_=cls)
                if stem:
                    text = stem.get_text(strip=True)
                    text = clean_text(text)
                    if text and len(text) > 3:
                        return text
            
            # ========== 策略7: 从文本行中查找题目 ==========
            text_content = container.get_text()
            lines = text_content.split('\n')
            for line in lines:
                line = line.strip()
                if not line or len(line) < 5:
                    continue
                
                cleaned_line = clean_text(line)
                
                # 跳过明显的非题目内容
                if any(kw in cleaned_line for kw in ['我的答案', '正确答案', '得分', '分数']):
                    continue
                
                # 检查是否以题号开头
                if re.match(r'^\d+[\.、\s\)]', cleaned_line):
                    return cleaned_line
                
                # 检查是否包含题型标记
                if re.search(r'[\(\（\[\【][单多判填问简].*?题[\)\）\]\】]', cleaned_line):
                    return cleaned_line
            
            # ========== 策略8: 正则匹配整段题目 ==========
            match = re.search(r'(\d+[\.、\s].*?)(?=我的答案|正确答案|A[\.、\s]|B[\.、\s]|$)', text_content, re.DOTALL)
            if match:
                text = match.group(1).strip()
                text = clean_text(text)
                if text and len(text) > 5:
                    return text
            
            # ========== 策略9: 最后尝试 - 取容器前200字符 ==========
            full_text = container.get_text(strip=True)
            if full_text:
                # 截取前200字符作为题目
                text = clean_text(full_text[:200])
                if text and len(text) > 5:
                    return text
            
        except Exception as e:
            app_logger.error(f"提取题目文本失败: {e}")
        
        return ""

    def extract_answers_and_score(self, container):
        """提取用户答案、正确答案、得分和正确性"""
        correct_answer = ""
        my_answer = ""
        score = ""
        is_correct = None

        try:
            # 方法1: 从标准元素提取 (如 stuAnswerContent, rightAnswerContent)
            
            # 提取我的答案 (.stuAnswerContent)
            stu_answer_elem = container.find(class_='stuAnswerContent')
            if stu_answer_elem:
                my_answer = stu_answer_elem.get_text(strip=True)
            
            # 提取正确答案 (.rightAnswerContent)
            right_answer_elem = container.find(class_='rightAnswerContent')
            if right_answer_elem:
                correct_answer = right_answer_elem.get_text(strip=True)
            
            # 提取得分 (.totalScore i)
            total_score_elem = container.find(class_='totalScore')
            if total_score_elem:
                score_i = total_score_elem.find('i')
                if score_i:
                    score = score_i.get_text(strip=True)
            
            # 判断正确性 - 查找标记图标
            marking_dui = container.find(class_='marking_dui')
            if marking_dui:
                is_correct = True
            else:
                marking_cuo = container.find(class_='marking_cuo')
                if marking_cuo:
                    is_correct = False
            
            # 方法1-B: mark_answer 方式
            if not my_answer or not correct_answer:
                mark_answer = container.find(class_='mark_answer')
                if mark_answer:
                    # mark_fill colorGreen 里面的 dd.rightAnswerContent
                    if not correct_answer:
                        green_fill = mark_answer.find('dl', class_=lambda x: x and 'colorGreen' in x)
                        if green_fill:
                            right_dd = green_fill.find('dd', class_='rightAnswerContent')
                            if right_dd:
                                correct_answer = right_dd.get_text(strip=True)
                    
                    # mark_fill colorDeep 里面的 dd.stuAnswerContent
                    if not my_answer:
                        deep_fill = mark_answer.find('dl', class_=lambda x: x and 'colorDeep' in x)
                        if deep_fill:
                            stu_dd = deep_fill.find('dd', class_='stuAnswerContent')
                            if stu_dd:
                                my_answer = stu_dd.get_text(strip=True)

            # 方法2: 如果信息不完整，用正则表达式匹配
            text_content = container.get_text()

            if not correct_answer:
                # 正确答案模式
                correct_patterns = [
                    r'正确答案[：:]\s*([ABCD√×✓✗对错是否]+(?:[、,，]\s*[ABCD√×✓✗对错是否]+)*)',
                    r'答案[：:]\s*([ABCD√×✓✗对错是否]+(?:[、,，]\s*[ABCD√×✓✗对错是否]+)*)',
                ]

                for pattern in correct_patterns:
                    match = re.search(pattern, text_content)
                    if match:
                        correct_answer = match.group(1).strip()
                        break

            if not my_answer:
                # 我的答案模式
                my_patterns = [
                    r'我的答案[：:]\s*([ABCD√×✓✗对错是否]+(?:[、,，]\s*[ABCD√×✓✗对错是否]+)*)',
                ]

                for pattern in my_patterns:
                    match = re.search(pattern, text_content)
                    if match:
                        my_answer = match.group(1).strip()
                        break

            # 如果没有提取到分数，用正则匹配
            if not score:
                score_patterns = [
                    r'(\d+(?:\.\d+)?)\s*分',
                    r'得分[：:]\s*(\d+(?:\.\d+)?)',
                ]
                for pattern in score_patterns:
                    match = re.search(pattern, text_content)
                    if match:
                        score = match.group(1)
                        break

            # 判断正确性 - 如果没有从元素判断
            if is_correct is None and correct_answer and my_answer:
                is_correct = correct_answer.strip() == my_answer.strip()

        except Exception as e:
            app_logger.error(f"提取答案和得分失败: {e}")

        return correct_answer, my_answer, score, is_correct

    def extract_options_with_images(self, container):
        """
        提取题目选项 - 史诗级增强版
        整合所有脚本的选项提取策略，支持纯图片选项、混排选项
        """
        options = []
        try:
            # ========== 策略1: 使用配置的选择器链式查找 ==========
            for selector in CHAOXING_SELECTORS['options']:
                try:
                    opt_elements = container.select(selector)
                    if opt_elements and len(opt_elements) > 0:
                        app_logger.debug(f"选项策略命中: {selector}, 找到 {len(opt_elements)} 个选项")
                        
                        for idx, opt_elem in enumerate(opt_elements):
                            # 使用智能选项解析
                            parsed = self.parse_option_content(opt_elem)
                            if parsed:
                                # 如果没有标签，使用默认顺序
                                if not parsed['label']:
                                    parsed['label'] = chr(65 + idx)  # A, B, C...
                                
                                options.append({
                                    'label': parsed['label'],
                                    'content': parsed['content'],
                                    'images': parsed['images'],
                                    'is_image_only': parsed.get('is_image_only', False),
                                    'mixed_content': parsed.get('mixed_content')
                                })
                        
                        if options:
                            return options
                except Exception:
                    continue
            
            # ========== 策略2: 查找带有选项标签的li/div元素 ==========
            if not options:
                # 查找所有可能包含选项的元素
                possible_options = container.find_all(['li', 'div', 'p', 'label'], 
                    string=re.compile(r'^[A-Z][\.、\s：:]'))
                
                for opt_elem in possible_options:
                    parsed = self.parse_option_content(opt_elem)
                    if parsed and parsed['content']:
                        options.append({
                            'label': parsed['label'] or chr(65 + len(options)),
                            'content': parsed['content'],
                            'images': parsed['images'],
                            'is_image_only': parsed.get('is_image_only', False),
                            'mixed_content': parsed.get('mixed_content')
                        })
            
            # ========== 策略3: 正则表达式从文本提取 ==========
            if not options:
                text_content = container.get_text()
                
                # 清理干扰文本
                clean_text = re.sub(r'我的答案[：:].*?(?=\n|$)', '', text_content, flags=re.MULTILINE)
                clean_text = re.sub(r'正确答案[：:].*?(?=\n|$)', '', clean_text, flags=re.MULTILINE)
                clean_text = re.sub(r'答案解析[：:].*', '', clean_text, flags=re.DOTALL)
                
                # 匹配 A. B. C. D. 选项
                option_pattern = re.compile(
                    r'([A-Z])[\.、：:]\s*(.+?)(?=(?:\s*[A-Z][\.、：:])|(?:\n\s*[A-Z][\.、：:])|$)', 
                    re.DOTALL
                )
                matches = option_pattern.findall(clean_text)
                
                for label, content in matches:
                    content = content.strip()
                    # 清理内容
                    content = re.sub(r'\n+.*?答案.*', '', content, flags=re.DOTALL)
                    content = re.sub(r'\d+分$', '', content).strip()
                    content = re.sub(r'\s+', ' ', content)  # 合并空白
                    
                    if content and len(content) >= 1:
                        # 尝试查找对应的HTML元素获取图片
                        option_images = []
                        label_patterns = [f'{label}.', f'{label}、', f'{label}：', f'{label}:']
                        for pattern in label_patterns:
                            opt_elems = container.find_all(string=re.compile(re.escape(pattern)))
                            for elem in opt_elems:
                                parent = elem.parent
                                if parent:
                                    option_images = self.extract_images_from_element(parent)
                                    if option_images:
                                        break
                            if option_images:
                                break
                        
                        options.append({
                            'label': label,
                            'content': content,
                            'images': option_images,
                            'is_image_only': False,
                            'mixed_content': None
                        })
            
            # ========== 策略4: 判断题选项（仅当确定是判断题时） ==========
            if not options:
                # 必须先确认是判断题类型，才添加判断选项
                q_type = self.determine_question_type_ocs(container)
                is_judge_question = '判断' in q_type
                
                # 额外检测：查找明确的判断题UI元素
                has_judge_inputs = container.select('input[type="radio"]')
                if has_judge_inputs and len(has_judge_inputs) == 2:
                    is_judge_question = True
                
                if is_judge_question:
                    # 标准判断题选项
                    options = [
                        {'label': 'A', 'content': '正确', 'images': [], 'is_image_only': False, 'mixed_content': None},
                        {'label': 'B', 'content': '错误', 'images': [], 'is_image_only': False, 'mixed_content': None}
                    ]
            
            # ========== 策略5: 查找包含input[type=radio/checkbox]的父元素 ==========
            if not options:
                inputs = container.select('input[type="radio"], input[type="checkbox"]')
                seen_labels = set()
                
                for inp in inputs:
                    # 向上查找包含选项文本的父元素
                    parent = inp.parent
                    for _ in range(3):
                        if parent is None:
                            break
                        text = parent.get_text(strip=True)
                        if text and len(text) > 1:
                            # 尝试提取标签
                            label_match = re.match(r'^([A-Z])[\.、\s：:]', text)
                            if label_match:
                                label = label_match.group(1)
                                if label not in seen_labels:
                                    seen_labels.add(label)
                                    content = text[len(label_match.group(0)):].strip()
                                    options.append({
                                        'label': label,
                                        'content': content,
                                        'images': self.extract_images_from_element(parent),
                                        'is_image_only': False,
                                        'mixed_content': None
                                    })
                            break
                        parent = parent.parent

        except Exception as e:
            app_logger.error(f"提取选项失败: {e}")

        # 按标签排序
        options.sort(key=lambda x: x.get('label', 'Z'))
        return options

    def extract_explanation_with_images(self, container):
        """提取题目解析和解析中的图片"""
        explanation_text = ""
        explanation_images = []

        try:
            # 查找解析相关的元素
            explanation_keywords = ['解析', '解答', '答案解析', '详解', '分析']

            for keyword in explanation_keywords:
                explanation_elem = container.find(string=re.compile(keyword))
                if explanation_elem:
                    parent = explanation_elem.parent
                    if parent:
                        explanation_text = parent.get_text(strip=True)
                        explanation_images = self.extract_images_from_element(parent)
                        break

        except Exception as e:
            app_logger.error(f"提取解析失败: {e}")

        return explanation_text, explanation_images

    def extract_question_info(self, container, question_num, homework_title):
        """
        提取单个题目的完整信息 - 史诗级增强版
        整合所有脚本的优秀技术：混排解析、智能选项、相似度匹配
        """
        try:
            question_info = {
                'homework_title': homework_title,
                'question_number': question_num,
                'question_type': '未知',
                'type': '未知',
                'title': '',
                'content': '',
                'title_images': [],
                'contentImages': [],
                'options': [],
                'optionImages': [],
                'correct_answer': '',
                'answer': '',
                'my_answer': '',
                'myAnswer': '',
                'score': '',
                'totalScore': '',
                'is_correct': None,
                'isCorrect': None,
                'explanation': '',
                'analysis': '',
                'explanation_images': [],
                'analysisImages': [],
                # 新增：混排内容
                'mixed_content': None,
                'raw_html': str(container)[:500]  # 保存原始HTML片段用于调试
            }
            
            # ========== 1. 使用OCS增强版题型识别 ==========
            question_info['question_type'] = self.determine_question_type_ocs(container)
            question_info['type'] = question_info['question_type']
            
            # ========== 2. 多策略提取题目内容 ==========
            # 尝试多个选择器
            content_element = None
            for selector in CHAOXING_SELECTORS['question_title']:
                content_element = container.select_one(selector)
                if content_element:
                    break
            
            if content_element:
                # 使用混排内容解析
                mixed = self.parse_mixed_content(content_element)
                question_info['content'] = mixed['text']
                question_info['title'] = mixed['text']
                question_info['mixed_content'] = mixed
                question_info['contentImages'] = self.extract_images_from_element(content_element)
                question_info['title_images'] = question_info['contentImages']
            else:
                # 降级：使用 extract_question_text
                question_info['content'] = self.extract_question_text(container)
                question_info['title'] = question_info['content']
                question_info['title_images'] = self.extract_images_from_element(container)
                question_info['contentImages'] = question_info['title_images']
            
            # 清理题目内容（移除题号和题型标记）
            if question_info['content']:
                content = question_info['content']
                content = re.sub(r'^\d+[\.\、\s\)]+', '', content)
                content = re.sub(r'^[\[\(\（\【].*?题[\]\)\）\】]\s*', '', content)
                question_info['content'] = content.strip()
                question_info['title'] = question_info['content']
            
            # ========== 3. 使用增强版选项提取 ==========
            question_info['options'] = self.extract_options_with_images(container)
            
            # 收集所有选项图片
            all_option_images = []
            for opt in question_info['options']:
                all_option_images.extend(opt.get('images', []))
            question_info['optionImages'] = all_option_images
            
            # ========== 4. 多策略提取我的答案 ==========
            my_answers = []
            my_answer_images = []
            
            for selector in CHAOXING_SELECTORS['my_answer']:
                elems = container.select(selector)
                for elem in elems:
                    # 使用混排解析
                    mixed = self.parse_mixed_content(elem)
                    if mixed['text']:
                        my_answers.append(mixed['text'])
                    # 提取图片
                    imgs = self.extract_images_from_element(elem)
                    my_answer_images.extend(imgs)
                if my_answers:
                    break
            
            question_info['my_answer'] = '; '.join(my_answers) if my_answers else ''
            question_info['myAnswer'] = question_info['my_answer']
            question_info['my_answer_images'] = my_answer_images
            question_info['myAnswerImages'] = my_answer_images
            
            if not question_info['my_answer'] and my_answer_images:
                question_info['my_answer'] = f'[包含 {len(my_answer_images)} 张图片]'
                question_info['myAnswer'] = question_info['my_answer']
            
            # ========== 5. 多策略提取正确答案 ==========
            correct_answers = []
            correct_answer_images = []
            
            for selector in CHAOXING_SELECTORS['correct_answer']:
                elems = container.select(selector)
                for elem in elems:
                    mixed = self.parse_mixed_content(elem)
                    if mixed['text']:
                        correct_answers.append(mixed['text'])
                    imgs = self.extract_images_from_element(elem)
                    correct_answer_images.extend(imgs)
                if correct_answers:
                    break
            
            question_info['correct_answer'] = '; '.join(correct_answers) if correct_answers else ''
            question_info['answer'] = question_info['correct_answer']
            question_info['correct_answer_images'] = correct_answer_images
            question_info['answerImages'] = correct_answer_images
            
            # ========== 6. 多策略提取解析 ==========
            for selector in CHAOXING_SELECTORS['explanation']:
                analysis_elem = container.select_one(selector)
                if analysis_elem:
                    mixed = self.parse_mixed_content(analysis_elem)
                    question_info['analysis'] = mixed['text']
                    question_info['explanation'] = mixed['text']
                    question_info['analysisImages'] = self.extract_images_from_element(analysis_elem)
                    question_info['explanation_images'] = question_info['analysisImages']
                    break
            
            # ========== 7. 多策略提取得分和满分（参考chaoxing_scrapper等脚本） ==========
            text_content = container.get_text()
            
            # 提取得分（从DOM元素）
            for selector in CHAOXING_SELECTORS['score']:
                score_elem = container.select_one(selector)
                if score_elem:
                    score_text = score_elem.get_text(strip=True)
                    # 提取数字
                    score_match = re.search(r'(\d+(?:\.\d+)?)', score_text)
                    if score_match:
                        question_info['score'] = score_match.group(1)
                    break
            
            # 从题目标题中同时提取题型和分数（参考chaoxing_scrapper）
            # 格式: (单选题, 2分) / (单选题)[2分] / （单选题：2分） / [单选题,2分]
            title_score_patterns = [
                r'[\(（\[]([^)）\]]+?)[,，:：]\s*(\d+(?:\.\d+)?)\s*分[\)）\]]',  # (单选题, 2分)
                r'[\(（]([^)）]+?)[\)）]\s*[\[\【](\d+(?:\.\d+)?)\s*分[\]\】]',  # (单选题)[2分]
                r'[\[\【]([^\]】]+?)[,，:：]\s*(\d+(?:\.\d+)?)\s*分[\]\】]',     # [单选题,2分]
            ]
            for pattern in title_score_patterns:
                match = re.search(pattern, text_content)
                if match:
                    if not question_info['totalScore']:
                        question_info['totalScore'] = match.group(2)
                    break
            
            # 提取满分（从文本中匹配更多格式）
            if not question_info['totalScore']:
                total_score_patterns = [
                    r'[\(（](\d+(?:\.\d+)?)\s*分[\)）]',      # (10分) 或 （10分）
                    r'[\[\【](\d+(?:\.\d+)?)\s*分[\]\】]',    # [10分] 或 【10分】
                    r'满分[：:]\s*(\d+(?:\.\d+)?)',           # 满分:10
                    r'本题\s*(\d+(?:\.\d+)?)\s*分',           # 本题10分
                    r'共\s*(\d+(?:\.\d+)?)\s*分',             # 共10分
                    r'(\d+(?:\.\d+)?)\s*分\s*[\)）\]\】]',    # 2分) 或 2分]
                ]
                for pattern in total_score_patterns:
                    match = re.search(pattern, text_content)
                    if match:
                        question_info['totalScore'] = match.group(1)
                        break
            
            # ========== 8. 多策略判断正确性 ==========
            is_correct = None
            
            # 方法1: 查找正确标记
            for selector in CHAOXING_SELECTORS['correct_mark']:
                if container.select_one(selector):
                    is_correct = True
                    break
            
            # 方法2: 查找错误标记
            if is_correct is None:
                for selector in CHAOXING_SELECTORS['wrong_mark']:
                    if container.select_one(selector):
                        is_correct = False
                        break
            
            # 方法3: 通过答案比较
            if is_correct is None and question_info['correct_answer'] and question_info['my_answer']:
                # 使用相似度匹配进行智能比较
                correct = question_info['correct_answer'].upper().replace(' ', '').replace(';', '').replace('、', '')
                my = question_info['my_answer'].upper().replace(' ', '').replace(';', '').replace('、', '')
                
                # 对于选择题答案 (A, B, AB, ABC等)
                if re.match(r'^[A-Z]+$', correct) and re.match(r'^[A-Z]+$', my):
                    is_correct = set(correct) == set(my)
                else:
                    # 使用相似度匹配
                    similarity = self.calculate_similarity(correct, my)
                    is_correct = similarity > 0.8
            
            question_info['is_correct'] = is_correct
            question_info['isCorrect'] = is_correct
            
            # ========== 9. 智能答案匹配（如果答案是文本而非选项标签） ==========
            if question_info['correct_answer'] and question_info['options']:
                answer = question_info['correct_answer']
                # 如果答案不是标准选项格式，尝试匹配
                if not re.match(r'^[A-Z]+$', answer.upper().replace(' ', '')):
                    matched = self.match_answer_with_options(answer, question_info['options'])
                    if matched:
                        question_info['matched_answer'] = matched
            
            # ========== 10. 验证和返回 ==========
            if not question_info['content'] and not question_info['title']:
                # 最后尝试：从容器获取任何文本
                fallback_text = container.get_text(strip=True)[:200]
                if fallback_text and len(fallback_text) > 10:
                    question_info['content'] = fallback_text
                    question_info['title'] = fallback_text
                else:
                    return None
            
            return question_info
            
        except Exception as e:
            app_logger.error(f"提取题目信息失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _get_text_content(self, element):
        """
        获取纯文本内容（去除图片标签）
        对应JS的 getTextContent 方法
        """
        if not element:
            return ''
        
        # 克隆元素以避免修改原DOM
        from copy import copy
        cloned = copy(element)
        
        # 将图片替换为占位符
        text = element.get_text(separator=' ', strip=True)
        
        return self._clean_text(text)
    
    def _clean_text(self, text):
        """
        清理文本内容
        对应JS的 cleanText 方法
        """
        if not text:
            return ''
        return re.sub(r'\s+', ' ', text).strip()

    def parse_homework_questions(self, homework_url, homework_title):
        """解析单个作业的题目"""
        app_logger.info(f"正在解析作业: {homework_title}")
        questions = []

        try:
            # 验证登录状态
            if not self.check_login():
                app_logger.error("解析作业失败: 用户未登录，请先登录")
                return []

            # 获取作业页面内容
            if self.login_manager and hasattr(self.login_manager, 'session'):
                session = self.login_manager.session
                response = session.get(homework_url, headers=self.headers, timeout=30)
                response.raise_for_status()
            else:
                app_logger.info("无法获取登录session")
                return []

            # 解析HTML
            soup = BeautifulSoup(response.content, 'html.parser')

            # 查找题目容器 - 改进识别逻辑
            question_containers = []

            # ========== 史诗级题目容器识别（使用配置选择器） ==========
            app_logger.info("开始识别题目容器...")
            
            # 使用配置的选择器链式查找
            for idx, selector in enumerate(CHAOXING_SELECTORS['question_containers'], 1):
                try:
                    elements = soup.select(selector)
                    if elements:
                        # 过滤：确保容器包含有效内容
                        valid_elements = []
                        for elem in elements:
                            # 检查是否包含题目相关元素
                            has_content = any([
                                elem.select_one(s) for s in CHAOXING_SELECTORS['question_title']
                            ]) or elem.get_text(strip=True)
                            
                            if has_content:
                                valid_elements.append(elem)
                        
                        if valid_elements:
                            question_containers.extend(valid_elements)
                            app_logger.info(f"策略{idx}: 选择器 '{selector}' 命中 {len(valid_elements)} 个有效容器")
                            break
                except Exception as e:
                    app_logger.debug(f"选择器 '{selector}' 执行失败: {e}")
                    continue
            
            # 补充策略: div[data] 带题目ID的元素
            if not question_containers:
                data_divs = soup.find_all('div', attrs={'data': True})
                for div in data_divs:
                    # 检查是否包含题目内容选择器
                    has_title = any(div.select_one(s) for s in CHAOXING_SELECTORS['question_title'])
                    if has_title:
                        question_containers.append(div)
                if question_containers:
                    app_logger.info(f"补充策略: 发现 {len(question_containers)} 个带data属性的题目元素")
            
            # 补充策略: 查找包含 .mark_name 的父容器
            if not question_containers:
                for title_selector in CHAOXING_SELECTORS['question_title']:
                    title_elements = soup.select(title_selector)
                    for title_elem in title_elements:
                        parent = title_elem.parent
                        for _ in range(6):  # 最多向上6层
                            if parent is None or parent.name == 'body':
                                break
                            # 检查是否包含答案元素
                            has_answer = any(
                                parent.select_one(s) for s in 
                                CHAOXING_SELECTORS['my_answer'] + CHAOXING_SELECTORS['correct_answer']
                            )
                            if has_answer and parent not in question_containers:
                                question_containers.append(parent)
                                break
                            parent = parent.parent
                    if question_containers:
                        app_logger.info(f"补充策略: 通过 '{title_selector}' 父容器发现 {len(question_containers)} 个题目")
                        break
            
            # 最终备用: 通用关键词匹配
            if not question_containers:
                generic_containers = soup.find_all('div', class_=lambda x: x and any(
                    kw in x.lower() for kw in ['question', 'topic', 'item', 'ques', 'timu', 'stem']
                ))
                if generic_containers:
                    question_containers.extend(generic_containers)
                    app_logger.info(f"备用策略: 通用关键词匹配发现 {len(generic_containers)} 个可能的容器")

            app_logger.info(f"找到 {len(question_containers)} 个题目容器")
            
            # ========== 提取题型分组标题 ==========
            # 例如: <h2 class="type_tit">一. 简答题（共1题，100分）</h2>
            type_sections = []
            type_tit_elements = soup.find_all(['h2', 'div'], class_='type_tit')
            for tit_elem in type_tit_elements:
                section_text = tit_elem.get_text(strip=True)
                if section_text:
                    type_sections.append({
                        'title': section_text,
                        'element': tit_elem
                    })
            
            if type_sections:
                app_logger.info(f"找到 {len(type_sections)} 个题型分组: {[s['title'] for s in type_sections]}")

            valid_question_count = 0
            seen_questions = set()  # 用于去重
            current_section = type_sections[0]['title'] if type_sections else None

            for i, container in enumerate(question_containers, 1):
                try:
                    question_info = self.extract_question_info(container, valid_question_count + 1, homework_title)
                    if question_info:
                        # 使用题目文本的前50个字符作为去重标识
                        question_key = question_info['title'][:50]

                        if question_key in seen_questions:
                            app_logger.warning(f"跳过重复题目 {i}: {question_key}...")
                            continue

                        seen_questions.add(question_key)
                        valid_question_count += 1
                        question_info['question_number'] = valid_question_count  # 更新题目序号
                        
                        # 添加分组信息
                        question_info['section'] = current_section
                        
                        questions.append(question_info)

                        # 构建状态信息
                        status_info = []
                        if question_info.get('is_correct') is not None:
                            if question_info['is_correct']:
                                status_info.append("正确")
                            else:
                                status_info.append("错误")

                        if question_info.get('score'):
                            status_info.append(f"{question_info['score']}分")

                        # 显示我的答案（即使正确答案为空也显示）
                        if question_info.get('my_answer'):
                            my_ans_preview = question_info['my_answer'][:50] + '...' if len(question_info['my_answer']) > 50 else question_info['my_answer']
                            status_info.append(f"我的答案: {my_ans_preview}")
                        
                        # 显示正确答案（即使为空也标注）
                        if question_info.get('correct_answer'):
                            correct_ans_preview = question_info['correct_answer'][:50] + '...' if len(question_info['correct_answer']) > 50 else question_info['correct_answer']
                            status_info.append(f"正确答案: {correct_ans_preview}")
                        else:
                            status_info.append("正确答案: (未设置)")

                        status_text = " | ".join(status_info) if status_info else ""

                        app_logger.info(f"题目 {valid_question_count}: {question_info['title'][:50]}...")
                        if status_text:
                            app_logger.info(f"   {status_text}")

                        # 显示图片信息
                        total_images = len(question_info['title_images'])
                        for option in question_info['options']:
                            total_images += len(option.get('images', []))
                        total_images += len(question_info['explanation_images'])

                        if total_images > 0:
                            app_logger.info(f"包含 {total_images} 张图片")
                    else:
                        # 获取容器文本来显示跳过的内容
                        container_text = container.get_text(strip=True)[:50]
                        app_logger.warning(f"跳过无效内容 {i}: {container_text}...")

                except Exception as e:
                    app_logger.info(f"容器 {i} 解析出错: {e}")
                    continue

            return questions

        except Exception as e:
            app_logger.error(f"解析作业失败: {e}")
            return []

    def save_questions_to_file(self, questions, homework_title):
        """保存题目数据到JSON文件"""
        if not questions:
            app_logger.info("没有题目数据可保存")
            return False
            
        try:
            # 生成安全的文件名
            safe_title = homework_title.replace('/', '_').replace('\\', '_').replace(':', '_')
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f'homework_questions_{safe_title}_{timestamp}.json'

            # 统计信息
            stats = {
                'total_questions': len(questions),
                'question_types': {},
                'total_images': 0,
                'correct_count': 0,
                'total_score': 0
            }

            for question in questions:
                # 统计题目类型
                q_type = question.get('question_type', '未知')
                stats['question_types'][q_type] = stats['question_types'].get(q_type, 0) + 1

                # 统计图片数量
                stats['total_images'] += len(question.get('title_images', []))
                stats['total_images'] += len(question.get('explanation_images', []))
                for option in question.get('options', []):
                    stats['total_images'] += len(option.get('images', []))

                # 统计正确率和总分
                if question.get('is_correct'):
                    stats['correct_count'] += 1

                if question.get('score'):
                    try:
                        stats['total_score'] += float(question['score'])
                    except ValueError:
                        pass

            # 构建输出数据
            output_data = {
                'metadata': {
                    'homework_title': homework_title,
                    'timestamp': datetime.now().isoformat(),
                    'total_questions': len(questions),
                    'statistics': stats,
                    'parser_version': '3.0'
                },
                'questions': questions
            }

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)

            app_logger.info(f"题目数据已保存到: {filename}")
            app_logger.info(f"文件大小: {os.path.getsize(filename) / 1024 / 1024:.2f} MB")
            
            # 打印统计信息
            app_logger.info("解析统计:")
            app_logger.info(f"    总题目数: {stats['total_questions']}")
            app_logger.info(f"    总图片数: {stats['total_images']}")
            app_logger.info(f"    正确题目: {stats['correct_count']}")
            app_logger.info(f"    总得分: {stats['total_score']:.1f}分")
            
            if len(questions) > 0:
                accuracy = (stats['correct_count'] / len(questions)) * 100
                app_logger.info(f"    正确率: {accuracy:.1f}%")

            return True

        except Exception as e:
            app_logger.error(f"保存文件失败: {e}")
            return False
