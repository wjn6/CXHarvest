#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
选择器配置模块
存储所有DOM选择器和常量定义
"""

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
