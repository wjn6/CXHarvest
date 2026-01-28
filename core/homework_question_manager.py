#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
作业题目管理器模块
负责解析作业页面中的题目内容，包括题目文本、选项、答案等信息
"""

# =============================================================================
# 标准库导入
# =============================================================================
import base64
import re
from io import BytesIO
from typing import Dict, List, Optional, Any, Union

# =============================================================================
# 第三方库导入
# =============================================================================
from bs4 import BeautifulSoup
from PIL import Image

# =============================================================================
# 项目内部导入
# =============================================================================
from .common import *
from .image_processor import get_image_processor
from .exceptions import handle_exceptions
from .enterprise_logger import app_logger

class HomeworkQuestionManager:
    """作业题目管理器
    
    负责解析作业页面中的题目内容，包括题目文本、选项、答案、解析等信息。
    支持多种题型的解析，包括单选题、多选题、判断题、填空题、问答题等。
    
    Attributes:
        login_manager: 登录管理器实例
        headers: HTTP请求头配置
        image_processor: 图片处理器实例
    """
    
    def __init__(self, login_manager: Any):
        """初始化作业题目管理器
        
        Args:
            login_manager: 登录管理器实例，用于网络请求认证
        """
        self.login_manager = login_manager
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'
        }
        # 初始化图片处理器
        self.image_processor = get_image_processor()
        self.image_processor.set_session(login_manager.session)
        app_logger.info("题目解析器初始化完成")

    def check_login(self) -> bool:
        """检查登录状态
        
        通过验证session cookies和测试请求来确认登录状态是否有效。
        
        Returns:
            bool: 登录状态是否有效
        """
        try:
            # 直接检查 session cookies
            if not self.login_manager.session.cookies:
                app_logger.error("没有登录凭证")
                return False
            
            # 执行一个简单的测试请求验证登录状态
            test_url = "https://mooc1.chaoxing.com/mooc2/course/list"
            response = self.login_manager.session.get(test_url, headers=self.headers, timeout=10)
            
            if response.status_code == 200 and "登录" not in response.text:
                app_logger.success("登录状态正常")
                return True
            else:
                app_logger.warning("登录状态已失效")
                return False
                
        except Exception as e:
            app_logger.error("检查登录状态失败", {"error": str(e)})
            return False

    @handle_exceptions
    def get_image_as_base64(self, url: str) -> Optional[str]:
        """将图片转换为Base64编码
        
        使用优化的图片处理器进行图片下载、压缩和Base64编码转换。
        
        Args:
            url: 图片URL地址
            
        Returns:
            Optional[str]: Base64编码的图片数据，失败时返回None
        """
        return self.image_processor.process_image_url(url, compress=True)

    def extract_images_from_element(self, element: Optional[Any]) -> List[Dict[str, Any]]:
        """从指定元素中提取图片并转换为Base64
        
        遍历HTML元素中的所有img标签，下载图片并转换为Base64编码。
        同时提取图片的尺寸信息和替代文本。
        
        Args:
            element: BeautifulSoup解析的HTML元素
            
        Returns:
            List[Dict[str, Any]]: 图片信息列表，每个字典包含src、alt、data、width、height
        """
        images = []
        if not element:
            return images
        
        try:
            unique_urls: List[str] = []
            url_to_img_node: Dict[str, Any] = {}
            # 1. 收集所有img标签的唯一URL
            for img in element.find_all('img'):
                src = img.get('src')
                if src and src not in url_to_img_node:
                    url_to_img_node[src] = img
                    unique_urls.append(src)

            if not unique_urls:
                return images

            # 2. 并发处理图片为Base64
            # 处理器内部带会话与压缩，自动限流
            url_to_b64: Dict[str, Optional[str]] = self.image_processor.batch_process_images(unique_urls, compress=True)

            # 3. 组装结果并计算尺寸（仅对成功的Base64计算）
            for src in unique_urls:
                img = url_to_img_node.get(src)
                base64_data = url_to_b64.get(src)
                width = height = 0
                if base64_data and base64_data.startswith('data:image'):
                    try:
                        image_data = base64_data.split(',')[1]
                        image_bytes = base64.b64decode(image_data)
                        with Image.open(BytesIO(image_bytes)) as pil_img:
                            width, height = pil_img.size
                    except Exception:
                        pass
                images.append({
                    'src': src,
                    'alt': (img.get('alt', '图片') if img else '图片'),
                    'data': base64_data,
                    'width': width,
                    'height': height
                })

            app_logger.debug("在元素中提取图片", {"image_count": len(images)})

        except Exception as e:
            app_logger.warning("提取图片失败", {"error": str(e)})
        
        return images

    def determine_question_type(self, container: Any) -> str:
        """判断题目类型
        
        基于题目文本内容和选项格式自动判断题目类型。
        支持识别单选题、多选题、判断题、填空题、问答题等类型。
        
        Args:
            container: BeautifulSoup解析的题目容器元素
            
        Returns:
            str: 题目类型字符串
        """
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
        elif any(keyword in text_content for keyword in ['问答题', 'essay', '简答', '论述']):
            return '问答题'
        else:
            # 根据选项判断
            if re.search(r'[ABCD][\.、]', text_content):
                return '单选题' if len(re.findall(r'[ABCD][\.、]', text_content)) <= 4 else '多选题'
            elif re.search(r'[√×✓✗对错是否][\.、]?', text_content):
                return '判断题'
            else:
                return '问答题'

    def is_valid_question(self, text: str) -> bool:
        """判断是否为有效题目 - 宽松策略，优先保留题目
        
        过滤掉分数统计信息、题型分组标题等无效内容，
        只保留真正的题目文本。
        
        Args:
            text: 待验证的文本内容
            
        Returns:
            bool: 是否为有效的题目文本
        """
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
        
        # 检查是否只包含数字
        if re.match(r'^[\d\s]+$', text):
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
        
        # 策略6: 长度足够（>10字符），且包含中文
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

    def extract_question_text(self, container: Any) -> str:
        """提取题目文本 - 多策略增强版
        
        从题目容器中提取题目的文本内容，支持多种提取策略。
        
        Args:
            container: BeautifulSoup解析的题目容器元素
            
        Returns:
            str: 提取到的题目文本，失败时返回空字符串
        """
        try:
            # 辅助函数：清洗题目文本
            def clean_text(raw_text):
                if not raw_text:
                    return ''
                separators = ['我的答案', '正确答案', '答案解析', 'Answer:', 'Correct Answer:']
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
                cleaned = re.sub(r'^\d+[\.、\s\)]+\s*', '', full_text)
                cleaned = re.sub(r'^[\[\(\（\【].*?题[\]\)\）\】]\s*', '', cleaned)
                cleaned = clean_text(cleaned)
                if cleaned and len(cleaned) > 3:
                    return cleaned
            
            # ========== 策略3: .qtContent 元素 ==========
            qt_content = container.find(class_='qtContent')
            if qt_content:
                text = qt_content.get_text(strip=True)
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
                
                if any(kw in cleaned_line for kw in ['我的答案', '正确答案', '得分', '分数']):
                    continue
                
                if re.match(r'^\d+[\.、\s\)]', cleaned_line):
                    return cleaned_line
                
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
                text = clean_text(full_text[:200])
                if text and len(text) > 5:
                    return text
            
        except Exception as e:
            app_logger.warning("提取题目文本失败", {"error": str(e)})
        
        return ""

    def extract_answers_and_score(self, container):
        """提取用户答案、正确答案、得分和正确性 - 您的原始逻辑"""
        correct_answer = ""
        my_answer = ""
        score = ""
        is_correct = None

        try:
            # 方法1: 使用您的选择器逻辑
            mark_answer = container.find(class_='mark_answer')
            if mark_answer:
                # 正确答案 (.colorGreen)
                correct_elem = mark_answer.find(class_='colorGreen')
                if correct_elem:
                    answer_text = correct_elem.get_text(strip=True)
                    correct_answer = re.sub(r'^(正确答案[：:]\s*)', '', answer_text)

                # 我的答案 (.colorDeep)
                my_elem = mark_answer.find(class_='colorDeep')
                if my_elem:
                    answer_text = my_elem.get_text(strip=True)
                    my_answer = re.sub(r'^(我的答案[：:]\s*)', '', answer_text)

            # 方法2: 使用正则表达式匹配 - 您的原始逻辑
            text_content = container.get_text()

            if not correct_answer or not my_answer:
                # 正确答案模式
                correct_patterns = [
                    r'正确答案[：:]\s*([ABCD√×✓✗对错是否]+(?:[、,，]\s*[ABCD√×✓✗对错是否]+)*)',
                    r'答案[：:]\s*([ABCD√×✓✗对错是否]+(?:[、,，]\s*[ABCD√×✓✗对错是否]+)*)',
                    r'标准答案[：:]\s*([ABCD√×✓✗对错是否]+(?:[、,，]\s*[ABCD√×✓✗对错是否]+)*)'
                ]

                for pattern in correct_patterns:
                    match = re.search(pattern, text_content)
                    if match and not correct_answer:
                        correct_answer = match.group(1).strip()
                        break

                # 我的答案模式
                my_patterns = [
                    r'我的答案[：:]\s*([ABCD√×✓✗对错是否]+(?:[、,，]\s*[ABCD√×✓✗对错是否]+)*)',
                    r'你的答案[：:]\s*([ABCD√×✓✗对错是否]+(?:[、,，]\s*[ABCD√×✓✗对错是否]+)*)',
                    r'学生答案[：:]\s*([ABCD√×✓✗对错是否]+(?:[、,，]\s*[ABCD√×✓✗对错是否]+)*)'
                ]

                for pattern in my_patterns:
                    match = re.search(pattern, text_content)
                    if match and not my_answer:
                        my_answer = match.group(1).strip()
                        break

            # 提取得分信息 - 您的原始逻辑
            score_patterns = [
                r'(\d+(?:\.\d+)?)\s*分',
                r'得分[：:]\s*(\d+(?:\.\d+)?)',
                r'分数[：:]\s*(\d+(?:\.\d+)?)'
            ]

            for pattern in score_patterns:
                match = re.search(pattern, text_content)
                if match:
                    score = match.group(1)
                    break

            # 判断是否正确
            if correct_answer and my_answer:
                is_correct = correct_answer.strip() == my_answer.strip()

            # 也可以通过页面元素判断正确性
            if is_correct is None:
                # 查找正确/错误标记
                if container.find(class_=lambda x: x and ('correct' in x.lower() or 'right' in x.lower())):
                    is_correct = True
                elif container.find(class_=lambda x: x and ('wrong' in x.lower() or 'error' in x.lower())):
                    is_correct = False
                elif '正确' in text_content:
                    is_correct = True
                elif '错误' in text_content or '不正确' in text_content:
                    is_correct = False

        except Exception as e:
            app_logger.error("提取答案和得分失败", {"error": str(e)})

        return correct_answer, my_answer, score, is_correct

    def extract_options_with_images(self, container):
        """提取题目选项，包含选项中的图片 - 您的原始逻辑"""
        options = []
        try:
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
            app_logger.error("提取选项失败", {"error": str(e)})

        return options

    def extract_explanation_with_images(self, container):
        """提取题目解析和解析中的图片 - 您的原始逻辑"""
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
            app_logger.error("提取解析失败", {"error": str(e)})

        return explanation_text, explanation_images

    def extract_question_info(self, container, question_num, homework_title):
        """提取单个题目的完整信息 - 您的原始逻辑"""
        try:
            # 首先提取题目文本并验证是否为有效题目
            title = self.extract_question_text(container)
            if not title or not self.is_valid_question(title):
                return None

            question_info = {
                'homework_title': homework_title,
                'question_number': question_num,
                'question_type': '未知',
                'title': title,
                'title_images': [],
                'options': [],
                'correct_answer': '',
                'my_answer': '',
                'score': '',
                'is_correct': None,
                'explanation': '',
                'explanation_images': []
            }

            # 提取题目中的图片
            title_images = self.extract_images_from_element(container.find(class_='mark_name') or container)
            if title_images:
                question_info['title_images'] = title_images

            # 判断题目类型：优先使用所属分组标题(.type_tit)，否则回退规则判断
            group_title = None
            try:
                parent_probe = container
                # 限制向上查找层数以防极端DOM造成长链
                for _ in range(8):
                    if parent_probe is None:
                        break
                    title_elem = parent_probe.find(class_='type_tit')
                    if title_elem and title_elem.get_text(strip=True):
                        group_title = title_elem.get_text(strip=True)
                        break
                    parent_probe = parent_probe.parent
            except Exception:
                group_title = None

            question_info['question_type'] = group_title or self.determine_question_type(container)

            # 提取答案、得分和正确性
            correct_answer, my_answer, score, is_correct = self.extract_answers_and_score(container)
            question_info['correct_answer'] = correct_answer
            question_info['my_answer'] = my_answer
            question_info['score'] = score
            question_info['is_correct'] = is_correct

            # 提取选项（包含选项中的图片）
            options = self.extract_options_with_images(container)
            if options:
                question_info['options'] = options

            # 提取解析和解析中的图片
            explanation_text, explanation_images = self.extract_explanation_with_images(container)
            if explanation_text:
                question_info['explanation'] = explanation_text
            if explanation_images:
                question_info['explanation_images'] = explanation_images

            return question_info

        except Exception as e:
            app_logger.error("提取题目信息失败", {"error": str(e)})
            return None

    def parse_homework_questions(self, homework_url, homework_title):
        """解析单个作业的题目 - 基于您的原始逻辑，添加 .questionLi 支持"""
        app_logger.info(f"正在解析作业: {homework_title}")
        questions = []

        session = self.login_manager.session
        if not session:
            app_logger.error("没有有效的session")
            return []

        try:
            # 获取作业页面内容
            response = session.get(homework_url, headers=self.headers, timeout=30)
            response.raise_for_status()

            # 解析HTML
            soup = BeautifulSoup(response.content, 'html.parser')

            # ========== 多策略题目容器识别（参考v1.31chaoxing.js） ==========
            question_containers = []
            
            # 策略1: .questionLi - 单个题目容器（最精确，优先级最高）
            # 注意：.mark_item 是题型分组容器，可能包含多个 .questionLi
            question_li = soup.find_all(class_='questionLi')
            if question_li:
                question_containers.extend(question_li)
                app_logger.info(f"策略1: 选择器 '.questionLi' 命中 {len(question_li)} 个有效容器")
            
            # 策略2: .mark_item - 如果没有 .questionLi，再尝试 .mark_item
            # 但要检查 .mark_item 内部是否有子题目容器
            if not question_containers:
                mark_items = soup.find_all(class_='mark_item')
                if mark_items:
                    # 检查 mark_item 内部是否有 questionLi（题型分组情况）
                    inner_questions = []
                    for mark_item in mark_items:
                        inner_li = mark_item.find_all(class_='questionLi')
                        if inner_li:
                            inner_questions.extend(inner_li)
                    
                    if inner_questions:
                        # mark_item 是分组容器，使用内部的 questionLi
                        question_containers.extend(inner_questions)
                        app_logger.info(f"策略2: '.mark_item' 内发现 {len(inner_questions)} 个 '.questionLi' 题目")
                    else:
                        # mark_item 本身就是题目容器
                        question_containers.extend(mark_items)
                        app_logger.info(f"策略2: 选择器 '.mark_item' 命中 {len(mark_items)} 个有效容器")
            
            # 策略3: .TiMu - 另一种常见容器
            if not question_containers:
                timu_elements = soup.find_all(class_='TiMu')
                if timu_elements:
                    question_containers.extend(timu_elements)
                    app_logger.info(f"策略3: 发现 {len(timu_elements)} 个 TiMu 元素")
            
            # 策略4: div[data] 带题目ID的元素
            if not question_containers:
                data_divs = soup.find_all('div', attrs={'data': True})
                for div in data_divs:
                    if div.find(class_=['mark_name', 'Zy_TItle', 'qtContent']):
                        question_containers.append(div)
                if question_containers:
                    app_logger.info(f"策略4: 发现 {len(question_containers)} 个带data属性的题目元素")
            
            # 策略5: 查找包含 .mark_name 的父容器
            if not question_containers:
                mark_names = soup.find_all(class_='mark_name')
                for mark_name in mark_names:
                    parent = mark_name.parent
                    for _ in range(5):
                        if parent is None:
                            break
                        if parent.find(class_=['mark_answer', 'stuAnswerContent', 'rightAnswerContent']):
                            if parent not in question_containers:
                                question_containers.append(parent)
                            break
                        parent = parent.parent
                if question_containers:
                    app_logger.info(f"策略5: 通过mark_name父容器发现 {len(question_containers)} 个题目")
            
            # 策略6: .Py-mian1 - 考试页面容器
            if not question_containers:
                py_mian = soup.find_all(class_='Py-mian1')
                if py_mian:
                    question_containers.extend(py_mian)
                    app_logger.info(f"策略6: 发现 {len(py_mian)} 个 Py-mian1 元素")
            
            # 策略7: 通用备用方法
            if not question_containers:
                generic_containers = soup.find_all('div', class_=lambda x: x and any(
                    kw in x.lower() for kw in ['question', 'topic', 'item', 'ques']
                ))
                if generic_containers:
                    question_containers.extend(generic_containers)
                    app_logger.info(f"策略7: 通用方法发现 {len(generic_containers)} 个可能的题目容器")

            app_logger.info(f"找到 {len(question_containers)} 个题目容器")

            valid_question_count = 0
            seen_questions = set()  # 用于去重

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

                        if question_info.get('my_answer') and question_info.get('correct_answer'):
                            status_info.append(f"我的答案: {question_info['my_answer']}")
                            status_info.append(f"正确答案: {question_info['correct_answer']}")

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
                    app_logger.warning(f"容器 {i} 解析出错: {str(e)}")
                    continue

            return questions

        except Exception as e:
            app_logger.error("解析作业失败", {"error": str(e)})
            return []
