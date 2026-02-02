#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内容提取模块
包含：混排内容解析、选项提取、答案提取、题目文本提取等功能
"""

import re
from bs4 import NavigableString, Tag
from ..enterprise_logger import app_logger
from ..selectors import CHAOXING_SELECTORS


class ContentExtractor:
    """内容提取器"""
    
    def __init__(self, image_handler):
        """
        初始化内容提取器
        
        Args:
            image_handler: ImageHandler实例，用于处理图片
        """
        self.image_handler = image_handler
    
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
                            base64_data = self.image_handler.get_image_as_base64(src)
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
    
    def parse_option_content(self, option_element):
        """
        智能解析选项内容，自动识别纯图片选项、纯文本选项、混排选项
        返回: {'label': 'A', 'content': 内容, 'is_image_only': bool, 'images': []}
        """
        if not option_element:
            return None
        
        try:
            # 获取所有图片（包括嵌套元素中的）
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
            # 清理文本中的图片占位符来判断是否有实际文本
            clean_text = re.sub(r'\[图片[^\]]*\]', '', text).strip()
            has_text = len(clean_text) > 0
            
            # 处理图片
            image_data_list = []
            for img in images:
                src = img.get('src', '')
                if src:
                    base64_data = self.image_handler.get_image_as_base64(src)
                    image_data_list.append({
                        'src': src,
                        'alt': img.get('alt', '选项图片'),
                        'data': base64_data
                    })
            
            # 调试：记录选项图片提取情况
            if has_images:
                app_logger.debug(f"选项 {label}: 找到 {len(images)} 张图片, 成功提取 {len(image_data_list)} 张")
            
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
    
    def extract_options_with_images(self, container, type_detector):
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
                                    option_images = self.image_handler.extract_images_from_element(parent)
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
                q_type = type_detector.determine_question_type_ocs(container)
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
                                        'images': self.image_handler.extract_images_from_element(parent),
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
                        explanation_images = self.image_handler.extract_images_from_element(parent)
                        break

        except Exception as e:
            app_logger.error(f"提取解析失败: {e}")

        return explanation_text, explanation_images
