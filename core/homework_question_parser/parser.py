#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主解析器模块
HomeworkQuestionParser 类的核心实现
"""

import os
import json
import re
from datetime import datetime
from bs4 import BeautifulSoup

from ..enterprise_logger import app_logger
from ..selectors import CHAOXING_SELECTORS

from .image_handler import ImageHandler
from .type_detector import TypeDetector
from .content_extractor import ContentExtractor
from .utils import calculate_similarity, match_answer_with_options


class HomeworkQuestionParser:
    """超星学习通作业题目解析器"""
    
    def __init__(self, login_manager=None):
        """初始化解析器"""
        self.login_manager = login_manager
        self.homework_list = []
        self.all_questions = []
        from core.common import AppConstants
        self.headers = {
            'User-Agent': AppConstants.DEFAULT_HEADERS['User-Agent']
        }
        
        # 初始化子模块
        self.image_handler = ImageHandler(login_manager)
        self.type_detector = TypeDetector()
        self.content_extractor = ContentExtractor(self.image_handler)
        
        app_logger.success("题目解析器初始化完成 (史诗级增强版)")
    
    # =========================================================================
    # 代理方法 - 保持向后兼容
    # =========================================================================
    def parse_mixed_content(self, element):
        """解析混排内容（代理到 ContentExtractor）"""
        return self.content_extractor.parse_mixed_content(element)
    
    def parse_option_content(self, option_element):
        """智能解析选项内容（代理到 ContentExtractor）"""
        return self.content_extractor.parse_option_content(option_element)
    
    def calculate_similarity(self, str1, str2):
        """计算两个字符串的相似度（代理到 utils）"""
        return calculate_similarity(str1, str2)
    
    def match_answer_with_options(self, answer, options):
        """将答案文本与选项进行智能匹配（代理到 utils）"""
        return match_answer_with_options(answer, options)
    
    def find_by_selectors(self, container, selector_key, find_all=False):
        """使用配置的选择器列表查找元素"""
        from .utils import find_by_selectors
        return find_by_selectors(container, selector_key, find_all)
    
    def determine_question_type_ocs(self, container):
        """使用OCS策略识别题目类型（代理到 TypeDetector）"""
        return self.type_detector.determine_question_type_ocs(container)
    
    def determine_question_type(self, container):
        """判断题目类型（代理到 TypeDetector）"""
        return self.type_detector.determine_question_type(container)
    
    def is_valid_question(self, text):
        """判断是否为有效题目（代理到 TypeDetector）"""
        return self.type_detector.is_valid_question(text)
    
    def get_image_as_base64(self, url):
        """将图片转换为Base64编码（代理到 ImageHandler）"""
        return self.image_handler.get_image_as_base64(url)
    
    def extract_images_from_element(self, element):
        """从指定元素中提取图片（代理到 ImageHandler）"""
        return self.image_handler.extract_images_from_element(element)
    
    def extract_question_text(self, container):
        """提取题目文本（代理到 ContentExtractor）"""
        return self.content_extractor.extract_question_text(container)
    
    def extract_answers_and_score(self, container):
        """提取答案和得分（代理到 ContentExtractor）"""
        return self.content_extractor.extract_answers_and_score(container)
    
    def extract_options_with_images(self, container):
        """提取题目选项（代理到 ContentExtractor）"""
        return self.content_extractor.extract_options_with_images(container, self.type_detector)
    
    def extract_explanation_with_images(self, container):
        """提取题目解析（代理到 ContentExtractor）"""
        return self.content_extractor.extract_explanation_with_images(container)
    
    # =========================================================================
    # 核心方法
    # =========================================================================
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
            from ..common import PathManager
            hw_list_path = PathManager.get_file_path("homework_list.json", "data")
            if not hw_list_path.exists():
                app_logger.info("未找到 homework_list.json 文件")
                app_logger.info("   请先在主界面选择课程并查看作业列表")
                return False

            with open(hw_list_path, 'r', encoding='utf-8') as f:
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
    
    def _get_text_content(self, element):
        """获取纯文本内容（去除图片标签）"""
        from .utils import get_text_content
        return get_text_content(element)
    
    def _clean_text(self, text):
        """清理文本内容"""
        from .utils import clean_text
        return clean_text(text)
    
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
            question_info['question_type'] = self.type_detector.determine_question_type_ocs(container)
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
                mixed = self.content_extractor.parse_mixed_content(content_element)
                question_info['content'] = mixed['text']
                question_info['title'] = mixed['text']
                question_info['mixed_content'] = mixed
                question_info['contentImages'] = self.image_handler.extract_images_from_element(content_element)
                question_info['title_images'] = question_info['contentImages']
            else:
                # 降级：使用 extract_question_text
                question_info['content'] = self.content_extractor.extract_question_text(container)
                question_info['title'] = question_info['content']
                question_info['title_images'] = self.image_handler.extract_images_from_element(container)
                question_info['contentImages'] = question_info['title_images']
            
            # 清理题目内容（移除题号和题型标记）
            if question_info['content']:
                content = question_info['content']
                content = re.sub(r'^\d+[\.\、\s\)]+', '', content)
                content = re.sub(r'^[\[\(\（\【].*?题[\]\)\）\】]\s*', '', content)
                question_info['content'] = content.strip()
                question_info['title'] = question_info['content']
            
            # ========== 3. 使用增强版选项提取 ==========
            question_info['options'] = self.content_extractor.extract_options_with_images(container, self.type_detector)
            
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
                    mixed = self.content_extractor.parse_mixed_content(elem)
                    if mixed['text']:
                        my_answers.append(mixed['text'])
                    # 提取图片
                    imgs = self.image_handler.extract_images_from_element(elem)
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
                    mixed = self.content_extractor.parse_mixed_content(elem)
                    if mixed['text']:
                        correct_answers.append(mixed['text'])
                    imgs = self.image_handler.extract_images_from_element(elem)
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
                    mixed = self.content_extractor.parse_mixed_content(analysis_elem)
                    question_info['analysis'] = mixed['text']
                    question_info['explanation'] = mixed['text']
                    question_info['analysisImages'] = self.image_handler.extract_images_from_element(analysis_elem)
                    question_info['explanation_images'] = question_info['analysisImages']
                    break
            
            # ========== 7. 多策略提取得分和满分 ==========
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
            
            # 从题目标题中同时提取题型和分数
            title_score_patterns = [
                r'[\(（\[]([^)）\]]+?)[,，:：]\s*(\d+(?:\.\d+)?)\s*分[\)）\]]',
                r'[\(（]([^)）]+?)[\)）]\s*[\[\【](\d+(?:\.\d+)?)\s*分[\]\】]',
                r'[\[\【]([^\]】]+?)[,，:：]\s*(\d+(?:\.\d+)?)\s*分[\]\】]',
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
                    r'[\(（](\d+(?:\.\d+)?)\s*分[\)）]',
                    r'[\[\【](\d+(?:\.\d+)?)\s*分[\]\】]',
                    r'满分[：:]\s*(\d+(?:\.\d+)?)',
                    r'本题\s*(\d+(?:\.\d+)?)\s*分',
                    r'共\s*(\d+(?:\.\d+)?)\s*分',
                    r'(\d+(?:\.\d+)?)\s*分\s*[\)）\]\】]',
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
                    similarity = calculate_similarity(correct, my)
                    is_correct = similarity > 0.8
            
            question_info['is_correct'] = is_correct
            question_info['isCorrect'] = is_correct
            
            # ========== 9. 智能答案匹配 ==========
            if question_info['correct_answer'] and question_info['options']:
                answer = question_info['correct_answer']
                # 如果答案不是标准选项格式，尝试匹配
                if not re.match(r'^[A-Z]+$', answer.upper().replace(' ', '')):
                    matched = match_answer_with_options(answer, question_info['options'])
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

            question_info['content_images'] = (
                question_info.get('content_images')
                or question_info.get('title_images', [])
                or question_info.get('contentImages', [])
            )
            question_info['option_images'] = (
                question_info.get('option_images')
                or question_info.get('optionImages', [])
            )
            question_info['explanation_images'] = (
                question_info.get('explanation_images')
                or question_info.get('analysisImages', [])
            )
            question_info['total_score'] = (
                question_info.get('total_score')
                or question_info.get('totalScore', '')
            )
            
            return question_info
            
        except Exception as e:
            app_logger.exception(f"提取题目信息失败: {e}", exc=e)
            return None

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
                
                # 检测登录页面重定向（超星可能返回200但内容是登录页）
                if '<title>用户登录</title>' in response.text or 'passport2.chaoxing.com/login' in response.text:
                    app_logger.warning("作业详情页返回了登录页面，session已失效")
                    return []
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
            type_sections = []
            type_tit_elements = soup.find_all(['h2', 'div'], class_='type_tit')
            expected_total = 0
            for tit_elem in type_tit_elements:
                section_text = tit_elem.get_text(strip=True)
                if section_text:
                    # 提取题目数量，如 "一. 单选题（共120题，60分）" -> 120
                    count_match = re.search(r'共(\d+)题', section_text)
                    section_count = int(count_match.group(1)) if count_match else 0
                    expected_total += section_count
                    type_sections.append({
                        'title': section_text,
                        'element': tit_elem,
                        'expected_count': section_count
                    })
            
            if type_sections:
                app_logger.info(f"========== 页面题目分组 ==========")
                for sec in type_sections:
                    app_logger.info(f"  {sec['title']}")
                app_logger.info(f"  页面声明总题数: {expected_total}")

            valid_question_count = 0

            for i, container in enumerate(question_containers, 1):
                try:
                    question_info = self.extract_question_info(container, valid_question_count + 1, homework_title)
                    if question_info:
                        valid_question_count += 1
                        question_info['question_number'] = valid_question_count  # 更新题目序号
                        
                        # 确定题目所属分组
                        current_section = self._find_question_section(container, type_sections)
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

                        # 显示我的答案
                        if question_info.get('my_answer'):
                            my_ans_preview = question_info['my_answer'][:50] + '...' if len(question_info['my_answer']) > 50 else question_info['my_answer']
                            status_info.append(f"我的答案: {my_ans_preview}")
                        
                        # 显示正确答案
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

            # ========== 核对解析结果 ==========
            app_logger.info(f"========== 解析结果核对 ==========")
            app_logger.info(f"  页面声明总题数: {expected_total}")
            app_logger.info(f"  实际解析题数: {valid_question_count}")
            if expected_total > 0 and valid_question_count != expected_total:
                app_logger.warning(f"  ⚠️ 题数不一致! 差异: {expected_total - valid_question_count}")
            elif expected_total > 0:
                app_logger.success(f"  ✓ 题数一致")

            return questions

        except Exception as e:
            app_logger.error(f"解析作业失败: {e}")
            return []

    def _find_question_section(self, container, type_sections):
        """
        确定题目所属的分组
        通过向上遍历DOM树查找最近的 type_tit 元素
        """
        if not type_sections:
            return None
        
        try:
            # 方法1: 向上查找 type_tit 父元素
            parent = container
            for _ in range(15):  # 限制查找层数
                if parent is None:
                    break
                # 检查同级前面的兄弟元素中是否有 type_tit
                prev_sibling = parent.find_previous_sibling(['h2', 'div'], class_='type_tit')
                if prev_sibling:
                    section_text = prev_sibling.get_text(strip=True)
                    if section_text:
                        return section_text
                parent = parent.parent
            
            # 方法2: 使用 find_previous 查找任意位置的 type_tit
            prev_type_tit = container.find_previous(['h2', 'div'], class_='type_tit')
            if prev_type_tit:
                section_text = prev_type_tit.get_text(strip=True)
                if section_text:
                    return section_text
            
            # 方法3: 回退到第一个分组
            return type_sections[0]['title'] if type_sections else None
            
        except Exception as e:
            app_logger.warning(f"查找题目分组失败: {e}")
            return type_sections[0]['title'] if type_sections else None

    def save_questions_to_file(self, questions, homework_title):
        """保存题目数据到JSON文件"""
        if not questions:
            app_logger.info("没有题目数据可保存")
            return False
            
        try:
            from core.common import PathManager, sanitize_filename
            # 生成安全的文件名
            safe_title = sanitize_filename(homework_title)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f'homework_questions_{safe_title}_{timestamp}.json'
            filepath = PathManager.get_exports_dir() / filename

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

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)

            app_logger.info(f"题目数据已保存到: {filepath}")
            app_logger.info(f"文件大小: {os.path.getsize(filepath) / 1024 / 1024:.2f} MB")
            
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
