#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
超星学习通作业题目解析器 - @yingyong集成版
参考JavaScript用户脚本的解析逻辑，提取作业中的题目、选项、答案等信息
支持图片Base64编码和分区域存储，完整的得分和正确性信息
作者: Augment Agent
版本: 3.0 - 集成@yingyong登录管理器
"""

import os
import json
import base64
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
from PIL import Image
import io
import time
from .enterprise_logger import app_logger

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
        app_logger.success("题目解析器初始化完成")

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
                    val = int(type_input.get('value'))
                    # 映射关系参考 ocs.common.user.js getQuestionType
                    if val == 0: return '单选题'
                    if val == 1: return '多选题'
                    if val == 3: return '判断题'
                    if val == 4: return '简答题'
                    if val in [2, 5, 6, 7, 8, 9, 10]: return '填空题'
                    if val == 11: return '连线题'
                    if val == 14: return '完形填空'
                    if val == 15: return '阅读理解'
                except ValueError:
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
        """判断是否为有效题目"""
        if not text or len(text.strip()) < 2:  # 放宽长度限制
            return False
        
        text = text.strip()
        
        # 过滤掉分数统计信息
        invalid_patterns = [
            r'^一\.\s*单选题.*分.*',      # 一. 单选题（73.2分）...
            r'^二\.\s*多选题.*分.*',      # 二. 多选题（26.8分）...
            r'^三\.\s*判断题.*分.*',      # 三. 判断题（XX分）...
            r'^四\.\s*填空题.*分.*',      # 四. 填空题（XX分）...
            r'^五\.\s*问答题.*分.*',      # 五. 问答题（XX分）...
            r'^六\.\s*.*题.*分.*',        # 六. XX题（XX分）...
            r'^\d+\.\d+分$',             # 纯分数
            r'^总分.*分',                # 总分信息
            r'^得分.*分',                # 得分信息
            r'^分数.*分',                # 分数信息
        ]
        
        for pattern in invalid_patterns:
            if re.match(pattern, text):
                return False
        
        # 只要是以数字开头，或者包含特定的题型标记，就认为是题目
        valid_starters = [
            r'^\d+[\.、\s]',           # 1. 题目
            r'^\(\d+\)',               # (1) 题目
            r'^\[.*?题\]',             # [单选题] 题目
            r'^\(.*?题\)',             # (单选题) 题目
            r'^\d+\s*\(.*?题\)',       # 1 (单选题)
        ]
        
        for pattern in valid_starters:
            if re.match(pattern, text):
                return True
                
        # 如果长度足够长，也可能是题目（针对没有序号的情况）
        if len(text) > 5:
            return True
        
        return False

    def extract_question_text(self, container):
        """提取题目文本"""
        try:
            # 辅助函数：清洗题目文本
            def clean_text(raw_text):
                # 截断答案部分
                separators = ['我的答案', '正确答案', '答案解析', 'Answer:', 'Correct Answer:', '我的答案：', '正确答案：']
                for sep in separators:
                    if sep in raw_text:
                        raw_text = raw_text.split(sep)[0]
                return raw_text.strip()

            # 方法0: OCS策略 - 查找 h3 元素并处理
            # 如果容器包含 questionLi 类，则专门处理 h3
            is_question_li = 'questionLi' in container.get('class', [])
            h3_title = container.find('h3')
            
            if is_question_li and h3_title:
                import copy
                # 复制一份在这个函数里操作，不影响原始DOM
                title_clone = copy.copy(h3_title)
                full_text = title_clone.get_text(strip=True)
                
                # 移除开头的题号 (数字加点或空格)
                cleaned = re.sub(r'^\d+[\.、\s\)]+\s*', '', full_text)
                # 移除题目类型标记 (如 [单选题], (单选题))
                cleaned = re.sub(r'^[\[\(].*?题[\]\)]\s*', '', cleaned)
                cleaned = clean_text(cleaned)
                
                if self.is_valid_question(cleaned) or len(cleaned) > 5:
                    return cleaned

            # 方法1: 查找 .mark_name 元素 (标准结构)
            mark_name = container.find(class_='mark_name')
            if mark_name:
                text = mark_name.get_text(strip=True)
                text = clean_text(text)
                if self.is_valid_question(text):
                    return text
            
            # 方法2: 查找 .TiMu 元素 (常见变体)
            timu = container.find(class_='TiMu')
            if timu:
                text = timu.get_text(strip=True)
                text = clean_text(text)
                if self.is_valid_question(text):
                    return text

            # 方法3: 查找题目序号模式 (全文搜索)
            text_content = container.get_text()
            # 尝试找到以数字开头的行，且不包含"分"字（或者是分值）
            lines = text_content.split('\n')
            for line in lines:
                line = line.strip()
                if not line: continue
                
                # 如果这一行包含"我的答案"，截断它
                cleaned_line = clean_text(line)
                
                if self.is_valid_question(cleaned_line):
                    return cleaned_line
            
            # 方法4: 正则匹配题目及序号
            # 匹配 "1. (单选题) 题目内容" 或 "1. 题目内容"
            match = re.search(r'(\d+[\.、\s].*?)(?=我的答案|正确答案|A[\.、]|B[\.、]|$)', text_content, re.DOTALL)
            if match:
                text = match.group(1).strip()
                if self.is_valid_question(text):
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
        """提取题目选项，包含选项中的图片"""
        options = []
        try:
            # OCS Selectors: .answerBg .answer_p, .textDIV, .eidtDiv, .radio-view li.clearfix, .checklist-view label
            ocs_options = container.select(".answerBg .answer_p, .textDIV, .eidtDiv, .radio-view li.clearfix, .checklist-view label")
            if ocs_options:
                for idx, opt_elem in enumerate(ocs_options):
                    # 尝试寻找选项标签 A, B, C...
                    label = chr(65 + idx) # 默认 A, B, C...
                    
                    # 尝试从文本中提取真实标签 (e.g. "A. Option Text")
                    text = opt_elem.get_text(strip=True)
                    match = re.match(r'^([A-Z])[\.、]', text)
                    if match:
                        label = match.group(1)
                        content = text[len(match.group(0)):].strip()
                    else:
                        content = text
                    
                    # 提取图片
                    imgs = self.extract_images_from_element(opt_elem)
                    
                    options.append({
                        'label': label,
                        'content': content,
                        'images': imgs
                    })
                return options

            text_content = container.get_text()

            # 先移除答案部分，避免干扰选项提取
            clean_text = re.sub(r'我的答案[：:].*?(?=\n|$)', '', text_content, flags=re.MULTILINE)
            clean_text = re.sub(r'正确答案[：:].*?(?=\n|$)', '', clean_text, flags=re.MULTILINE)
            clean_text = re.sub(r'答案[：:].*?(?=\n|$)', '', clean_text, flags=re.MULTILINE)

            # 查找ABCD选项
            option_pattern = re.compile(r'([ABCD])[\.、]\s*([^ABCD\n]+?)(?=\s*[ABCD][\.、]|\n\n|$)', re.DOTALL)
            matches = option_pattern.findall(clean_text)

            for label, content in matches:
                # 清理选项内容
                content = content.strip()
                content = re.sub(r'\n+.*?答案.*', '', content, flags=re.DOTALL)
                content = re.sub(r'\d+分$', '', content).strip()

                if content and len(content) > 1:
                    # 查找该选项对应的HTML元素，提取其中的图片
                    option_images = []
                    option_elements = container.find_all(string=re.compile(re.escape(label + '.')))
                    for elem in option_elements:
                        parent = elem.parent
                        if parent:
                            option_images = self.extract_images_from_element(parent)
                            break

                    options.append({
                        'label': label,
                        'content': content,
                        'images': option_images
                    })

            # 如果没有找到ABCD选项，尝试查找判断题选项
            if not options:
                judge_pattern = re.compile(r'([√×✓✗对错是否])[\.、]?\s*([^√×✓✗对错是否\n]*)', re.DOTALL)
                matches = judge_pattern.findall(clean_text)
                for label, content in matches:
                    content = content.strip()
                    if not content:
                        content = label

                    options.append({
                        'label': label,
                        'content': content,
                        'images': []
                    })

        except Exception as e:
            app_logger.error(f"提取选项失败: {e}")

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
        提取单个题目的完整信息
        完全按照 超星学习通作业题目提取工具（支持图片）.js 的逻辑重写
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
                'is_correct': None,
                'isCorrect': None,
                'explanation': '',
                'analysis': '',
                'explanation_images': [],
                'analysisImages': []
            }
            
            # ========== 1. 解析题目编号和类型 ==========
            # JS: const titleElement = container.querySelector('.mark_name');
            title_element = container.find(class_='mark_name')
            if title_element:
                title_text = title_element.get_text(strip=True)
                
                # 提取题目类型: const typeMatch = titleText.match(/\((.*?题)\)/);
                type_match = re.search(r'[\(\（](.*?题)[\)\）]', title_text)
                if type_match:
                    question_info['question_type'] = type_match.group(1)
                    question_info['type'] = type_match.group(1)
                else:
                    # 备用：从 .colorShallow 提取
                    color_shallow = container.find('span', class_='colorShallow')
                    if color_shallow:
                        type_text = color_shallow.get_text(strip=True)
                        type_text = re.sub(r'[\(\)\（\）\[\]]', '', type_text).strip()
                        if type_text:
                            question_info['question_type'] = type_text
                            question_info['type'] = type_text
                
                # 提取题目编号: const numberMatch = titleText.match(/^(\d+)\./);
                number_match = re.match(r'^(\d+)[\.\、]', title_text)
                if number_match:
                    question_info['question_number'] = number_match.group(1)
            
            # ========== 2. 解析题目内容和图片 ==========
            # JS: const contentElement = container.querySelector('.qtContent');
            content_element = container.find(class_='qtContent')
            if content_element:
                # getTextContent: 克隆元素，将图片替换为占位符
                question_info['content'] = self._get_text_content(content_element)
                question_info['title'] = question_info['content']
                
                # extractImages: 提取图片
                question_info['contentImages'] = self.extract_images_from_element(content_element)
                question_info['title_images'] = question_info['contentImages']
            else:
                # 备用：从 .mark_name 提取（移除题号和题型）
                if title_element:
                    raw_text = title_element.get_text(strip=True)
                    # 移除开头的题号
                    raw_text = re.sub(r'^\d+[\.\、]\s*', '', raw_text)
                    # 移除题型标记
                    raw_text = re.sub(r'[\(\（].*?题[\)\）]\s*', '', raw_text)
                    question_info['content'] = self._clean_text(raw_text)
                    question_info['title'] = question_info['content']
            
            # ========== 3. 解析选项和选项图片 ==========
            # JS: const optionElements = container.querySelectorAll('.mark_letter li, .qtDetail li');
            option_elements = container.select('.mark_letter li, .qtDetail li')
            
            for opt_idx, option_elem in enumerate(option_elements):
                opt_text = self._get_text_content(option_elem)
                if opt_text:
                    # 尝试提取选项标签 (A, B, C...)
                    label_match = re.match(r'^([A-Z])[\.\、\s]', opt_text)
                    if label_match:
                        label = label_match.group(1)
                        content = opt_text[len(label_match.group(0)):].strip()
                    else:
                        label = chr(65 + opt_idx)  # 默认 A, B, C...
                        content = opt_text
                    
                    question_info['options'].append({
                        'label': label,
                        'content': content,
                        'images': self.extract_images_from_element(option_elem)
                    })
            
            # ========== 4. 解析我的答案（包括文字和图片） ==========
            # JS: const myAnswerElements = container.querySelectorAll('.stuAnswerContent');
            my_answer_elements = container.select('.stuAnswerContent')
            my_answers = []
            my_answer_images = []
            for elem in my_answer_elements:
                # 提取文字
                answer_text = self._clean_text(elem.get_text())
                if answer_text:
                    my_answers.append(answer_text)
                # 提取图片
                imgs = self.extract_images_from_element(elem)
                my_answer_images.extend(imgs)
            
            question_info['my_answer'] = '; '.join(my_answers) if my_answers else ''
            question_info['myAnswer'] = question_info['my_answer']
            question_info['my_answer_images'] = my_answer_images
            question_info['myAnswerImages'] = my_answer_images
            
            # 如果没有文字答案但有图片，标注
            if not question_info['my_answer'] and my_answer_images:
                question_info['my_answer'] = f'[包含 {len(my_answer_images)} 张图片]'
                question_info['myAnswer'] = question_info['my_answer']
            
            # ========== 5. 解析正确答案（包括文字和图片） ==========
            # JS: const correctAnswerElements = container.querySelectorAll('.rightAnswerContent');
            correct_answer_elements = container.select('.rightAnswerContent')
            correct_answers = []
            correct_answer_images = []
            for elem in correct_answer_elements:
                # 提取文字
                answer_text = self._clean_text(elem.get_text())
                if answer_text:
                    correct_answers.append(answer_text)
                # 提取图片
                imgs = self.extract_images_from_element(elem)
                correct_answer_images.extend(imgs)
            
            question_info['correct_answer'] = '; '.join(correct_answers) if correct_answers else ''
            question_info['answer'] = question_info['correct_answer']
            question_info['correct_answer_images'] = correct_answer_images
            question_info['answerImages'] = correct_answer_images
            
            # ========== 6. 解析答案解析 ==========
            # JS: const analysisElement = container.querySelector('.qtAnalysis');
            analysis_element = container.find(class_='qtAnalysis')
            if analysis_element:
                question_info['analysis'] = self._get_text_content(analysis_element)
                question_info['explanation'] = question_info['analysis']
                question_info['analysisImages'] = self.extract_images_from_element(analysis_element)
                question_info['explanation_images'] = question_info['analysisImages']
            
            # ========== 7. 解析得分 ==========
            # JS: const scoreElement = container.querySelector('.totalScore i');
            score_element = container.select_one('.totalScore i')
            if score_element:
                question_info['score'] = score_element.get_text(strip=True)
            else:
                # 备用：从 .mark_score 提取
                mark_score = container.find(class_='mark_score')
                if mark_score:
                    score_i = mark_score.find('i')
                    if score_i:
                        question_info['score'] = score_i.get_text(strip=True)
            
            # ========== 8. 判断是否正确 ==========
            # JS: const correctIcon = container.querySelector('.marking_dui');
            # JS: question.isCorrect = !!correctIcon;
            correct_icon = container.find(class_='marking_dui')
            if correct_icon:
                question_info['is_correct'] = True
                question_info['isCorrect'] = True
            else:
                wrong_icon = container.find(class_='marking_cuo')
                if wrong_icon:
                    question_info['is_correct'] = False
                    question_info['isCorrect'] = False
                else:
                    # 如果没有图标，尝试通过比较答案判断
                    if question_info['correct_answer'] and question_info['my_answer']:
                        # 对于选择题，规范化答案比较
                        correct = question_info['correct_answer'].upper().replace(' ', '').replace(';', '')
                        my = question_info['my_answer'].upper().replace(' ', '').replace(';', '')
                        question_info['is_correct'] = correct == my
                        question_info['isCorrect'] = question_info['is_correct']
            
            # 验证是否提取到有效内容
            if not question_info['content'] and not question_info['title']:
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

            # 方法1: OCS策略 - 查找 .questionLi
            ocs_containers = soup.find_all(class_='questionLi')
            if ocs_containers:
                question_containers.extend(ocs_containers)

            # 方法2: 查找包含 .mark_name 的直接父容器
            if not question_containers:
                mark_names = soup.find_all(class_='mark_name')
                for mark_name in mark_names:
                    # 找到包含完整题目信息的父容器
                    parent = mark_name.parent
                    while parent and not parent.find(class_='mark_answer'):
                         parent = parent.parent
                    if parent and parent not in question_containers:
                        question_containers.append(parent)

            # 如果没有找到，使用备用方法
            if not question_containers:
                question_containers = soup.find_all('div', class_=lambda x: x and ('question' in x.lower() or 'topic' in x.lower()))

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
