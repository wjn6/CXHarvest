#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
题型识别模块
包含：OCS题型识别、关键词识别、选项推断等功能
"""

import re
from ..enterprise_logger import app_logger
from ..selectors import OCS_QUESTION_TYPE_MAP


class TypeDetector:
    """题型识别器"""
    
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
