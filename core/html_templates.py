#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTML 导出模板系统
每套模板完全控制 HTML 结构和样式，实现风格迥异的导出效果
"""

import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from .enterprise_logger import app_logger
from .version import __version__, APP_NAME


class HtmlTemplate:
    """HTML 模板基类"""
    id: str = ""
    name: str = ""
    description: str = ""

    def render_html(self, exporter) -> str:
        """渲染完整 HTML，子类必须覆盖"""
        raise NotImplementedError

    def get_preview_svg(self) -> str:
        raise NotImplementedError

    # 公共辅助方法
    @staticmethod
    def _esc(text):
        if not text:
            return ""
        return (str(text).replace('&', '&amp;').replace('<', '&lt;')
                .replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#39;'))

    @staticmethod
    def _render_imgs(images, include_images=True):
        if not images or not include_images:
            return ""
        parts = []
        for img in images:
            if isinstance(img, dict):
                src = img.get('data') or img.get('src', '')
                alt = img.get('alt', '图片')
            else:
                src, alt = str(img), '图片'
            if src:
                safe_alt = HtmlTemplate._esc(alt)
                parts.append(f'<img class="question-image" src="{src}" alt="{safe_alt}" style="max-width:100%;" />')
        return '\n'.join(parts)

    @staticmethod
    def _clean_opt_content(content, opt_images):
        if opt_images:
            content = re.sub(r'\[图片选项[：:]\s*\d+张\]', '', content).strip()
        return content

    def _filter_js(self):
        return '''<script>
var _statusFilter='all',_typeFilter='all';
function filterByStatus(type){
  _statusFilter=type;
  document.querySelectorAll('.filter-btn').forEach(function(b){b.classList.remove('active')});
  event.target.classList.add('active');
  applyFilters();
}
function filterByType(type){
  _typeFilter=type;
  document.querySelectorAll('.type-filter-btn').forEach(function(b){b.classList.remove('active')});
  event.target.classList.add('active');
  applyFilters();
}
function applyFilters(){
  document.querySelectorAll('.question-card').forEach(function(c){
    var ok=c.dataset.correct==='true';
    var tp=c.dataset.type||'';
    var statusMatch=(_statusFilter==='all'||(_statusFilter==='correct'&&ok)||(_statusFilter==='wrong'&&!ok));
    var typeMatch=(_typeFilter==='all'||tp===_typeFilter);
    c.classList.toggle('hidden',!(statusMatch&&typeMatch));
  });
}
</script>'''

    def _build_type_filter_bar(self, questions, exp):
        """生成题型筛选按钮 HTML"""
        types = {}
        for q in questions:
            t = exp._get_question_type(q)
            types[t] = types.get(t, 0) + 1
        if len(types) <= 1:
            return ""
        btns = '<button class="type-filter-btn active" onclick="filterByType(\'all\')">全部题型</button>'
        for t, cnt in types.items():
            safe_t = self._esc(t)
            btns += f'<button class="type-filter-btn" onclick="filterByType(\'{safe_t}\')">{safe_t}({cnt})</button>'
        return f'<div class="type-filter-bar">{btns}</div>'


def _make_preview_svg(bg, header_bg, card_bg, card_border, badge_bg,
                      correct_bg, wrong_bg, text_color, sub_text) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="200" height="140" viewBox="0 0 200 140">
  <rect width="200" height="140" rx="6" fill="{bg}"/>
  <rect x="10" y="0" width="180" height="140" rx="6" fill="{card_bg}" stroke="{card_border}" stroke-width="0.5"/>
  <rect x="10" y="0" width="180" height="32" rx="6" fill="{header_bg}"/>
  <rect x="10" y="26" width="180" height="6" fill="{header_bg}"/>
  <rect x="60" y="10" width="80" height="6" rx="2" fill="white" opacity="0.9"/>
  <rect x="75" y="20" width="50" height="3" rx="1" fill="white" opacity="0.5"/>
  <rect x="20" y="40" width="30" height="12" rx="2" fill="{correct_bg}"/>
  <rect x="55" y="40" width="30" height="12" rx="2" fill="{wrong_bg}"/>
  <rect x="90" y="40" width="30" height="12" rx="2" fill="{card_border}"/>
  <rect x="20" y="60" width="160" height="30" rx="4" fill="{card_bg}" stroke="{card_border}" stroke-width="0.5"/>
  <rect x="26" y="65" width="24" height="6" rx="2" fill="{badge_bg}"/>
  <rect x="54" y="65" width="18" height="6" rx="2" fill="{card_border}"/>
  <rect x="26" y="75" width="100" height="3" rx="1" fill="{text_color}" opacity="0.5"/>
  <rect x="26" y="81" width="60" height="3" rx="1" fill="{text_color}" opacity="0.3"/>
  <rect x="20" y="96" width="160" height="30" rx="4" fill="{card_bg}" stroke="{card_border}" stroke-width="0.5"/>
  <rect x="26" y="101" width="24" height="6" rx="2" fill="{badge_bg}"/>
  <rect x="54" y="101" width="18" height="6" rx="2" fill="{card_border}"/>
  <rect x="26" y="111" width="120" height="3" rx="1" fill="{text_color}" opacity="0.5"/>
  <rect x="26" y="117" width="80" height="3" rx="1" fill="{text_color}" opacity="0.3"/>
  <rect x="40" y="134" width="120" height="3" rx="1" fill="{sub_text}" opacity="0.3"/>
</svg>'''


# =====================================================================
# 模板 1: 默认青色 — 卡片式，现代 SaaS 风格
# =====================================================================
class DefaultTemplate(HtmlTemplate):
    id = "default"
    name = "默认青色"
    description = "现代卡片布局、青色渐变"

    def render_html(self, exp) -> str:
        from .common import get_question_field
        s = exp.get_statistics()
        o = exp.options
        h = self._esc
        r = lambda imgs: self._render_imgs(imgs, o.include_images)

        out = f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{h(exp.homework_title)}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;background:#f0f4f8;padding:24px;min-height:100vh}}
.container{{max-width:900px;margin:0 auto;background:#fff;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.07);overflow:hidden}}
.header{{background:linear-gradient(135deg,#0891b2,#06b6d4);color:#fff;padding:32px;text-align:center}}
.header h1{{font-size:26px;margin-bottom:6px}}.header .meta{{opacity:.85;font-size:13px}}
.stats-bar{{display:flex;justify-content:space-around;padding:20px;border-bottom:1px solid #e5e7eb}}
.stat-item{{text-align:center}}.stat-value{{font-size:26px;font-weight:700;color:#1e293b}}.stat-label{{font-size:12px;color:#64748b;margin-top:2px}}
.stat-item.correct .stat-value{{color:#16a34a}}.stat-item.wrong .stat-value{{color:#dc2626}}
.filter-bar{{display:flex;gap:8px;padding:14px 24px;background:#f8fafc;border-bottom:1px solid #e5e7eb}}
.filter-btn{{padding:7px 16px;border:none;border-radius:6px;font-size:13px;cursor:pointer;background:#e2e8f0;color:#64748b;transition:.2s}}
.filter-btn.active{{background:#0891b2;color:#fff}}.filter-btn:hover{{opacity:.85}}
.type-filter-bar{{display:flex;gap:6px;padding:10px 24px;background:#f1f5f9;border-bottom:1px solid #e5e7eb;flex-wrap:wrap}}
.type-filter-btn{{padding:5px 14px;border:none;border-radius:14px;font-size:12px;cursor:pointer;background:#e2e8f0;color:#64748b;transition:.2s}}
.type-filter-btn.active{{background:#0e7490;color:#fff}}.type-filter-btn:hover{{opacity:.85}}
.content{{padding:24px}}
.question-card{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px;margin-bottom:14px}}.question-card.hidden{{display:none}}
.question-header{{display:flex;align-items:center;margin-bottom:10px;flex-wrap:wrap;gap:8px}}
.question-number{{background:#0891b2;color:#fff;padding:3px 12px;border-radius:6px;font-size:13px;font-weight:500}}
.question-type{{background:#f1f5f9;color:#64748b;padding:3px 10px;border-radius:6px;font-size:12px}}
.question-status{{margin-left:auto;padding:3px 10px;border-radius:6px;font-size:12px;font-weight:500}}
.question-status.correct{{background:#dcfce7;color:#16a34a}}.question-status.wrong{{background:#fee2e2;color:#dc2626}}
.question-content{{font-size:15px;line-height:1.75;color:#1e293b;margin-bottom:14px}}
.options-list{{list-style:none;margin-bottom:14px}}.options-list li{{padding:10px 14px;margin-bottom:6px;background:#f8fafc;border-radius:8px;font-size:14px;color:#475569}}
.answer-section{{padding:10px 14px;border-radius:8px;margin-top:10px;font-size:14px}}
.answer-section.my-answer{{background:#ecfeff;border-left:4px solid #0891b2}}
.answer-section.correct-answer{{background:#f0fdf4;border-left:4px solid #22c55e}}
.answer-section.analysis{{background:#fefce8;border-left:4px solid #eab308}}
.answer-label{{font-weight:600;margin-right:6px}}.score-info{{margin-top:10px;font-size:13px;color:#64748b}}
.question-image{{max-width:100%;height:auto;border-radius:8px;margin:8px 0}}
.footer{{text-align:center;padding:18px;background:#f8fafc;color:#94a3b8;font-size:11px}}
@media print{{body{{background:#fff;padding:0}}.container{{box-shadow:none}}.question-card{{break-inside:avoid}}.filter-bar{{display:none}}}}
</style></head><body><div class="container">
<div class="header"><h1>{h(exp.homework_title)}</h1>'''
        if o.include_export_time:
            out += f'<div class="meta">导出时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>'
        out += '</div>'
        if o.include_statistics:
            out += f'<div class="stats-bar"><div class="stat-item"><div class="stat-value">{s["total_questions"]}</div><div class="stat-label">总题数</div></div><div class="stat-item correct"><div class="stat-value">{s["correct_count"]}</div><div class="stat-label">正确</div></div><div class="stat-item wrong"><div class="stat-value">{s["wrong_count"]}</div><div class="stat-label">错误</div></div><div class="stat-item"><div class="stat-value">{s["accuracy"]}</div><div class="stat-label">正确率</div></div></div>'
        out += '<div class="filter-bar"><button class="filter-btn active" onclick="filterByStatus(\'all\')">全部</button><button class="filter-btn" onclick="filterByStatus(\'correct\')">答对</button><button class="filter-btn" onclick="filterByStatus(\'wrong\')">答错</button></div>'
        out += self._build_type_filter_bar(exp.questions, exp)
        out += '<div class="content">'

        for i, q in enumerate(exp.questions, 1):
            ic = exp._is_correct(q)
            dc = "true" if ic else "false"
            qt = exp._get_question_type(q)
            out += f'<div class="question-card" data-correct="{dc}" data-type="{h(qt)}"><div class="question-header">'
            if o.include_question_number: out += f'<span class="question-number">第 {i} 题</span>'
            if o.include_question_type: out += f'<span class="question-type">{qt}</span>'
            if o.show_correct_status and ic is not None:
                out += f'<span class="question-status {"correct" if ic else "wrong"}">{"✓ 正确" if ic else "✗ 错误"}</span>'
            out += f'</div><div class="question-content">{h(exp._get_question_content(q))}</div>'
            out += r(get_question_field(q, 'content_images', []))
            for opt in q.get('options', []):
                if isinstance(opt, dict):
                    c = self._clean_opt_content(opt.get('content',''), opt.get('images',[]))
                    out += f'<div class="options-list"><li>{h(opt.get("label",""))}. {h(c)}{r(opt.get("images",[]))}</li></div>'
                else:
                    out += f'<div class="options-list"><li>{h(str(opt))}</li></div>'
            if o.include_my_answer:
                ma = exp._get_my_answer(q)
                if ma and '[图片' not in ma: out += f'<div class="answer-section my-answer"><span class="answer-label">我的答案:</span>{h(ma)}</div>'
                out += r(get_question_field(q, 'my_answer_images', []))
            if o.include_correct_answer:
                ca = exp._get_question_answer(q)
                if ca and '[图片' not in ca: out += f'<div class="answer-section correct-answer"><span class="answer-label">正确答案:</span>{h(ca)}</div>'
                out += r(get_question_field(q, 'correct_answer_images', []))
            if o.include_analysis:
                an = exp._get_analysis(q)
                if an: out += f'<div class="answer-section analysis"><span class="answer-label">解析:</span>{h(an)}</div>'
            if o.include_score:
                sc = get_question_field(q, 'score', '')
                if sc: out += f'<div class="score-info">得分: {sc}</div>'
            out += '</div>'
        out += f'</div><div class="footer">Generated by {APP_NAME} v{__version__}</div></div>{self._filter_js()}</body></html>'
        return out

    def get_preview_svg(self):
        return _make_preview_svg("#f0f4f8","#0891b2","#ffffff","#e5e7eb","#0891b2","#dcfce7","#fee2e2","#1e293b","#94a3b8")


# =====================================================================
# 模板 2: 试卷风格 — 模拟纸质考试卷面
# =====================================================================
class ExamPaperTemplate(HtmlTemplate):
    id = "exam_paper"
    name = "试卷风格"
    description = "模拟纸质考试卷、密封线、题号大写"

    def render_html(self, exp) -> str:
        from .common import get_question_field
        s = exp.get_statistics()
        o = exp.options
        h = self._esc
        r = lambda imgs: self._render_imgs(imgs, o.include_images)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        questions_html = ""
        for i, q in enumerate(exp.questions, 1):
            ic = exp._is_correct(q)
            dc = "true" if ic else "false"
            qt = exp._get_question_type(q)
            status = ""
            if o.show_correct_status and ic is not None:
                status = '<span class="stamp stamp-correct">CORRECT</span>' if ic else '<span class="stamp stamp-wrong">WRONG</span>'

            opts = ""
            for opt in q.get('options', []):
                if isinstance(opt, dict):
                    c = self._clean_opt_content(opt.get('content',''), opt.get('images',[]))
                    opts += f'<div class="opt"><span class="opt-label">{h(opt.get("label",""))}</span>{h(c)}{r(opt.get("images",[]))}</div>'
                else:
                    opts += f'<div class="opt">{h(str(opt))}</div>'

            answers = ""
            if o.include_my_answer:
                ma = exp._get_my_answer(q)
                if ma and '[图片' not in ma: answers += f'<div class="ans-row"><b>我的答案：</b>{h(ma)}</div>'
                answers += r(get_question_field(q, 'my_answer_images', []))
            if o.include_correct_answer:
                ca = exp._get_question_answer(q)
                if ca and '[图片' not in ca: answers += f'<div class="ans-row correct-text"><b>正确答案：</b>{h(ca)}</div>'
                answers += r(get_question_field(q, 'correct_answer_images', []))
            if o.include_analysis:
                an = exp._get_analysis(q)
                if an: answers += f'<div class="ans-row analysis-text"><b>【解析】</b>{h(an)}</div>'
            score = ""
            if o.include_score:
                sc = get_question_field(q, 'score', '')
                if sc: score = f'<span class="score-badge">{sc}分</span>'

            questions_html += f'''<div class="question-card" data-correct="{dc}" data-type="{h(qt)}">
<div class="q-header"><span class="q-num">{i}</span><span class="q-type">({qt})</span>{score}{status}</div>
<div class="q-body">{h(exp._get_question_content(q))}</div>
{r(get_question_field(q, 'content_images', []))}
{opts}
<div class="ans-area">{answers}</div>
</div>'''

        stats_row = ""
        if o.include_statistics:
            stats_row = f'<tr><td>总题数: {s["total_questions"]}</td><td>正确: {s["correct_count"]}</td><td>错误: {s["wrong_count"]}</td><td>正确率: {s["accuracy"]}</td></tr>'

        return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{h(exp.homework_title)}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"SimSun","Songti SC",serif;background:#fff;padding:0;color:#000}}
.paper{{max-width:800px;margin:20px auto;border:2px solid #000;position:relative;padding:40px 50px 40px 70px}}
.seal-line{{position:absolute;left:0;top:0;bottom:0;width:50px;border-right:2px dashed #999;display:flex;align-items:center;justify-content:center}}
.seal-text{{writing-mode:vertical-rl;font-size:12px;color:#999;letter-spacing:4px}}
.paper-header{{text-align:center;border-bottom:2px solid #000;padding-bottom:16px;margin-bottom:20px}}
.paper-header h1{{font-size:22px;letter-spacing:4px;margin-bottom:8px}}
.paper-header .info{{font-size:12px;color:#555}}
.stats-table{{width:100%;border-collapse:collapse;margin-bottom:20px;font-size:13px}}
.stats-table td{{border:1px solid #999;padding:6px 12px;text-align:center}}
.filter-bar{{display:flex;gap:6px;margin-bottom:16px}}
.filter-btn{{padding:4px 12px;border:1px solid #333;background:#fff;font-size:12px;cursor:pointer;font-family:inherit}}
.filter-btn.active{{background:#333;color:#fff}}
.type-filter-bar{{display:flex;gap:4px;margin-bottom:12px;flex-wrap:wrap}}
.type-filter-btn{{padding:3px 10px;border:1px solid #aaa;font-size:11px;cursor:pointer;background:#fff;color:#555;font-family:inherit}}
.type-filter-btn.active{{background:#555;color:#fff;border-color:#555}}
.question-card{{margin-bottom:20px;padding-bottom:16px;border-bottom:1px dashed #ccc}}.question-card.hidden{{display:none}}
.q-header{{display:flex;align-items:center;gap:8px;margin-bottom:8px}}
.q-num{{display:inline-flex;width:28px;height:28px;align-items:center;justify-content:center;border:2px solid #000;border-radius:50%;font-weight:700;font-size:14px}}
.q-type{{font-size:13px;color:#555}}
.score-badge{{margin-left:auto;font-size:12px;border:1px solid #333;padding:1px 8px}}
.stamp{{margin-left:8px;font-size:10px;padding:2px 8px;border:2px solid;border-radius:4px;font-weight:700;transform:rotate(-5deg);display:inline-block}}
.stamp-correct{{color:#006400;border-color:#006400}}.stamp-wrong{{color:#8b0000;border-color:#8b0000}}
.q-body{{font-size:15px;line-height:1.8;margin-bottom:10px;text-indent:0}}
.opt{{padding:3px 0 3px 20px;font-size:14px;line-height:1.6}}
.opt-label{{font-weight:700;margin-right:6px}}
.ans-area{{margin-top:10px;padding:8px 0 0;border-top:1px solid #eee}}
.ans-row{{font-size:13px;line-height:1.7;margin-bottom:4px}}
.correct-text{{color:#006400}}.analysis-text{{color:#555;font-style:italic}}
.question-image{{max-width:100%;height:auto;margin:6px 0}}
.paper-footer{{text-align:center;margin-top:24px;font-size:10px;color:#aaa;border-top:1px solid #ccc;padding-top:10px}}
@media print{{.filter-bar{{display:none}}.paper{{border:none;margin:0;padding:20px 40px 20px 60px}}.question-card{{break-inside:avoid}}}}
</style></head><body>
<div class="paper">
<div class="seal-line"><span class="seal-text">密 封 线 内 不 要 答 题</span></div>
<div class="paper-header">
<h1>{h(exp.homework_title)}</h1>
<div class="info">{now}</div>
</div>
<table class="stats-table">{stats_row}</table>
<div class="filter-bar"><button class="filter-btn active" onclick="filterByStatus('all')">全部</button><button class="filter-btn" onclick="filterByStatus('correct')">答对</button><button class="filter-btn" onclick="filterByStatus('wrong')">答错</button></div>
{self._build_type_filter_bar(exp.questions, exp)}
{questions_html}
<div class="paper-footer">Generated by {APP_NAME} v{__version__}</div>
</div>{self._filter_js()}</body></html>'''

    def get_preview_svg(self):
        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="200" height="140" viewBox="0 0 200 140">
  <rect width="200" height="140" rx="2" fill="#fff" stroke="#000" stroke-width="2"/>
  <line x1="25" y1="0" x2="25" y2="140" stroke="#999" stroke-dasharray="4,3"/>
  <rect x="60" y="8" width="80" height="6" rx="1" fill="#000"/>
  <rect x="70" y="18" width="60" height="3" rx="1" fill="#555"/>
  <rect x="35" y="30" width="155" height="0.5" fill="#000"/>
  <circle cx="42" cy="45" r="8" fill="none" stroke="#000" stroke-width="1.5"/>
  <rect x="55" y="42" width="80" height="3" rx="1" fill="#000" opacity="0.6"/>
  <rect x="55" y="49" width="50" height="2" rx="1" fill="#000" opacity="0.3"/>
  <rect x="35" y="60" width="155" height="0.5" fill="#ccc" stroke-dasharray="3,2"/>
  <circle cx="42" cy="75" r="8" fill="none" stroke="#000" stroke-width="1.5"/>
  <rect x="55" y="72" width="100" height="3" rx="1" fill="#000" opacity="0.6"/>
  <rect x="55" y="79" width="70" height="2" rx="1" fill="#000" opacity="0.3"/>
  <rect x="35" y="90" width="155" height="0.5" fill="#ccc" stroke-dasharray="3,2"/>
  <circle cx="42" cy="105" r="8" fill="none" stroke="#000" stroke-width="1.5"/>
  <rect x="55" y="102" width="90" height="3" rx="1" fill="#000" opacity="0.6"/>
  <rect x="55" y="109" width="60" height="2" rx="1" fill="#000" opacity="0.3"/>
</svg>'''


# =====================================================================
# 模板 3: 暗色终端 — 代码终端风格，深色背景
# =====================================================================
class DarkTerminalTemplate(HtmlTemplate):
    id = "dark"
    name = "暗色终端"
    description = "终端代码风、深色背景、绿色光标"

    def render_html(self, exp) -> str:
        from .common import get_question_field
        s = exp.get_statistics()
        o = exp.options
        h = self._esc
        r = lambda imgs: self._render_imgs(imgs, o.include_images)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        questions_html = ""
        for i, q in enumerate(exp.questions, 1):
            ic = exp._is_correct(q)
            dc = "true" if ic else "false"
            st = ""
            if o.show_correct_status and ic is not None:
                st = '<span class="tag-pass">PASS</span>' if ic else '<span class="tag-fail">FAIL</span>'

            opts = ""
            for opt in q.get('options', []):
                if isinstance(opt, dict):
                    c = self._clean_opt_content(opt.get('content',''), opt.get('images',[]))
                    opts += f'<div class="opt"><span class="prompt">&gt;</span> <span class="opt-key">{h(opt.get("label",""))}</span> {h(c)}{r(opt.get("images",[]))}</div>'
                else:
                    opts += f'<div class="opt"><span class="prompt">&gt;</span> {h(str(opt))}</div>'

            answers = ""
            if o.include_my_answer:
                ma = exp._get_my_answer(q)
                if ma and '[图片' not in ma: answers += f'<div class="output"><span class="key">my_answer</span> = <span class="val">"{h(ma)}"</span></div>'
                answers += r(get_question_field(q, 'my_answer_images', []))
            if o.include_correct_answer:
                ca = exp._get_question_answer(q)
                if ca and '[图片' not in ca: answers += f'<div class="output"><span class="key">correct</span> = <span class="val correct-val">"{h(ca)}"</span></div>'
                answers += r(get_question_field(q, 'correct_answer_images', []))
            if o.include_analysis:
                an = exp._get_analysis(q)
                if an: answers += f'<div class="output comment">// {h(an)}</div>'
            score = ""
            if o.include_score:
                sc = get_question_field(q, 'score', '')
                if sc: score = f'<span class="score-tag">{sc}pts</span>'

            qt_dark = exp._get_question_type(q)
            questions_html += f'''<div class="question-card" data-correct="{dc}" data-type="{h(qt_dark)}">
<div class="q-line"><span class="line-num">{i:03d}</span> <span class="fn">question</span>(<span class="type-tag">{h(qt_dark)}</span>) {st} {score}</div>
<div class="q-body">{h(exp._get_question_content(q))}</div>
{r(get_question_field(q, 'content_images', []))}
{opts}{answers}
</div>'''

        stats_line = ""
        if o.include_statistics:
            stats_line = f'<div class="stats-line"><span class="prompt">$</span> stats --total={s["total_questions"]} --correct={s["correct_count"]} --wrong={s["wrong_count"]} --accuracy={s["accuracy"]}</div>'

        return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{h(exp.homework_title)}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Cascadia Code","Fira Code","JetBrains Mono","Consolas","Microsoft YaHei",monospace;background:#0c0c0c;color:#cccccc;padding:0;min-height:100vh}}
.terminal{{max-width:920px;margin:0 auto;padding:0}}
.title-bar{{background:#1e1e1e;padding:8px 16px;display:flex;align-items:center;gap:8px;border-bottom:1px solid #333}}
.dot{{width:12px;height:12px;border-radius:50%}}.dot-r{{background:#ff5f56}}.dot-y{{background:#ffbd2e}}.dot-g{{background:#27c93f}}
.title-text{{flex:1;text-align:center;font-size:12px;color:#888}}
.body{{padding:20px 24px}}
.header-line{{color:#569cd6;margin-bottom:4px;font-size:14px}}
.time-line{{color:#666;font-size:12px;margin-bottom:16px}}
.stats-line{{background:#1a1a1a;padding:8px 12px;border-radius:4px;font-size:13px;margin-bottom:16px;color:#6a9955}}
.filter-bar{{display:flex;gap:6px;margin-bottom:16px}}
.filter-btn{{padding:4px 12px;border:1px solid #444;background:#1a1a1a;color:#888;font-size:12px;cursor:pointer;font-family:inherit;border-radius:3px}}
.filter-btn.active{{background:#264f78;color:#fff;border-color:#264f78}}
.type-filter-bar{{display:flex;gap:4px;margin-bottom:12px;flex-wrap:wrap}}
.type-filter-btn{{padding:3px 10px;border:1px solid #444;border-radius:3px;font-size:11px;cursor:pointer;background:#1a1a1a;color:#888;font-family:inherit}}
.type-filter-btn.active{{background:#264f78;color:#fff;border-color:#264f78}}
.question-card{{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:6px;padding:14px 16px;margin-bottom:12px;border-left:3px solid #333}}.question-card.hidden{{display:none}}
.q-line{{font-size:13px;margin-bottom:8px;display:flex;align-items:center;gap:6px;flex-wrap:wrap}}
.line-num{{color:#858585;min-width:30px}}.fn{{color:#dcdcaa}}.type-tag{{color:#4ec9b0}}
.tag-pass{{color:#27c93f;border:1px solid #27c93f;padding:1px 6px;border-radius:3px;font-size:10px}}.tag-fail{{color:#ff5f56;border:1px solid #ff5f56;padding:1px 6px;border-radius:3px;font-size:10px}}
.score-tag{{color:#d7ba7d;font-size:11px;margin-left:auto}}
.q-body{{font-size:14px;line-height:1.7;color:#d4d4d4;margin-bottom:10px;white-space:pre-wrap}}
.opt{{padding:2px 0;font-size:13px;color:#9cdcfe}}.prompt{{color:#27c93f}}.opt-key{{color:#ce9178}}
.output{{font-size:13px;padding:2px 0;color:#d4d4d4}}.key{{color:#9cdcfe}}.val{{color:#ce9178}}.correct-val{{color:#6a9955}}
.comment{{color:#6a9955;font-style:italic}}
.question-image{{max-width:100%;height:auto;margin:6px 0;border-radius:4px}}
.footer{{text-align:center;padding:16px;color:#444;font-size:10px;border-top:1px solid #222}}
@media print{{body{{background:#fff;color:#000}}.terminal{{background:#fff}}.question-card{{background:#fff;border-color:#ccc}}.q-body,.output,.opt{{color:#000}}.filter-bar{{display:none}}.question-card{{break-inside:avoid}}}}
</style></head><body>
<div class="terminal">
<div class="title-bar"><span class="dot dot-r"></span><span class="dot dot-y"></span><span class="dot dot-g"></span><span class="title-text">{h(exp.homework_title)} — Terminal</span></div>
<div class="body">
<div class="header-line">/// {h(exp.homework_title)}</div>
<div class="time-line">// Generated at {now}</div>
{stats_line}
<div class="filter-bar"><button class="filter-btn active" onclick="filterByStatus('all')">ALL</button><button class="filter-btn" onclick="filterByStatus('correct')">PASS</button><button class="filter-btn" onclick="filterByStatus('wrong')">FAIL</button></div>
{self._build_type_filter_bar(exp.questions, exp)}
{questions_html}
<div class="footer">Generated by {APP_NAME} v{__version__}</div>
</div></div>{self._filter_js()}</body></html>'''

    def get_preview_svg(self):
        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="200" height="140" viewBox="0 0 200 140">
  <rect width="200" height="140" rx="6" fill="#0c0c0c"/>
  <rect x="0" y="0" width="200" height="22" rx="6" fill="#1e1e1e"/>
  <rect x="0" y="16" width="200" height="6" fill="#1e1e1e"/>
  <circle cx="12" cy="11" r="4" fill="#ff5f56"/><circle cx="24" cy="11" r="4" fill="#ffbd2e"/><circle cx="36" cy="11" r="4" fill="#27c93f"/>
  <rect x="12" y="30" width="60" height="4" rx="1" fill="#569cd6"/>
  <rect x="12" y="40" width="176" height="20" rx="3" fill="#1a1a1a" stroke="#2a2a2a" stroke-width="0.5"/>
  <rect x="16" y="44" width="20" height="3" rx="1" fill="#858585"/><rect x="40" y="44" width="30" height="3" rx="1" fill="#dcdcaa"/>
  <rect x="16" y="51" width="100" height="3" rx="1" fill="#d4d4d4" opacity="0.5"/>
  <rect x="12" y="66" width="176" height="20" rx="3" fill="#1a1a1a" stroke="#2a2a2a" stroke-width="0.5"/>
  <rect x="16" y="70" width="20" height="3" rx="1" fill="#858585"/><rect x="40" y="70" width="30" height="3" rx="1" fill="#dcdcaa"/>
  <rect x="16" y="77" width="80" height="3" rx="1" fill="#d4d4d4" opacity="0.5"/>
  <rect x="12" y="92" width="176" height="20" rx="3" fill="#1a1a1a" stroke="#2a2a2a" stroke-width="0.5"/>
  <rect x="16" y="96" width="20" height="3" rx="1" fill="#858585"/><rect x="40" y="96" width="30" height="3" rx="1" fill="#dcdcaa"/>
  <rect x="16" y="103" width="120" height="3" rx="1" fill="#d4d4d4" opacity="0.5"/>
  <rect x="60" y="130" width="80" height="3" rx="1" fill="#444" opacity="0.5"/>
</svg>'''


# =====================================================================
# 模板 4: 彩虹杂志 — 杂志排版、大色块、侧栏
# =====================================================================
class MagazineTemplate(HtmlTemplate):
    id = "magazine"
    name = "彩虹杂志"
    description = "杂志排版、大色块标题、侧栏统计"

    def render_html(self, exp) -> str:
        from .common import get_question_field
        s = exp.get_statistics()
        o = exp.options
        h = self._esc
        r = lambda imgs: self._render_imgs(imgs, o.include_images)

        colors = ['#6366f1','#10b981','#f59e0b','#ef4444','#ec4899','#8b5cf6','#14b8a6','#f97316']
        questions_html = ""
        for i, q in enumerate(exp.questions, 1):
            ic = exp._is_correct(q)
            dc = "true" if ic else "false"
            color = colors[(i-1) % len(colors)]
            st = ""
            if o.show_correct_status and ic is not None:
                st = f'<div class="status-dot" style="background:{"#10b981" if ic else "#ef4444"}"></div>'

            opts = ""
            for j, opt in enumerate(q.get('options', [])):
                if isinstance(opt, dict):
                    c = self._clean_opt_content(opt.get('content',''), opt.get('images',[]))
                    opts += f'<div class="opt-pill"><span class="pill-label" style="background:{color}">{h(opt.get("label",""))}</span><span class="pill-text">{h(c)}</span>{r(opt.get("images",[]))}</div>'
                else:
                    opts += f'<div class="opt-pill"><span class="pill-text">{h(str(opt))}</span></div>'

            answers = ""
            if o.include_my_answer:
                ma = exp._get_my_answer(q)
                if ma and '[图片' not in ma: answers += f'<div class="ans-block mine"><b>我的答案</b><p>{h(ma)}</p></div>'
                answers += r(get_question_field(q, 'my_answer_images', []))
            if o.include_correct_answer:
                ca = exp._get_question_answer(q)
                if ca and '[图片' not in ca: answers += f'<div class="ans-block right"><b>正确答案</b><p>{h(ca)}</p></div>'
                answers += r(get_question_field(q, 'correct_answer_images', []))
            if o.include_analysis:
                an = exp._get_analysis(q)
                if an: answers += f'<div class="ans-block note"><b>解析</b><p>{h(an)}</p></div>'
            score = ""
            if o.include_score:
                sc = get_question_field(q, 'score', '')
                if sc: score = f'<span class="score-circle" style="border-color:{color};color:{color}">{sc}</span>'

            qt_mag = exp._get_question_type(q)
            questions_html += f'''<div class="question-card" data-correct="{dc}" data-type="{h(qt_mag)}">
<div class="q-top" style="background:{color}"><span class="q-num">Q{i}</span>{score}{st}</div>
<div class="q-info"><span class="type-label">{h(exp._get_question_type(q))}</span></div>
<div class="q-body">{h(exp._get_question_content(q))}</div>
{r(get_question_field(q, 'content_images', []))}
<div class="opts-grid">{opts}</div>
<div class="ans-grid">{answers}</div>
</div>'''

        stats_top = ""
        if o.include_statistics:
            stats_top = f'''<div class="stats-top">
<div class="side-stat"><div class="side-num">{s["total_questions"]}</div><div class="side-label">总题数</div></div>
<div class="side-stat"><div class="side-num" style="color:#10b981">{s["correct_count"]}</div><div class="side-label">正确</div></div>
<div class="side-stat"><div class="side-num" style="color:#ef4444">{s["wrong_count"]}</div><div class="side-label">错误</div></div>
<div class="side-stat"><div class="side-num">{s["accuracy"]}</div><div class="side-label">正确率</div></div>
</div>'''

        return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{h(exp.homework_title)}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","PingFang SC",-apple-system,sans-serif;background:linear-gradient(150deg,#e0c3fc,#8ec5fc,#f5d0fe);min-height:100vh;padding:24px}}
.main{{max-width:920px;margin:0 auto}}
.stats-top{{display:flex;justify-content:space-around;background:rgba(255,255,255,.85);border-radius:14px;padding:16px;margin-bottom:16px;box-shadow:0 2px 12px rgba(0,0,0,.04)}}
.side-stat{{text-align:center;flex:1}}
.side-num{{font-size:22px;font-weight:700;color:#333}}.side-label{{font-size:11px;color:#999}}
.cover{{background:linear-gradient(135deg,#6366f1,#a855f7,#ec4899);border-radius:20px;padding:36px;color:#fff;margin-bottom:20px;text-align:center}}
.cover h1{{font-size:28px;margin-bottom:8px;text-shadow:0 2px 8px rgba(0,0,0,.2)}}.cover .meta{{opacity:.85;font-size:13px}}
.filter-bar{{display:flex;gap:6px;margin-bottom:16px}}
.filter-btn{{padding:7px 18px;border:none;border-radius:20px;font-size:13px;cursor:pointer;background:rgba(255,255,255,.7);color:#666;transition:.3s}}
.filter-btn.active{{background:linear-gradient(135deg,#6366f1,#a855f7);color:#fff;box-shadow:0 2px 10px rgba(99,102,241,.3)}}
.type-filter-bar{{display:flex;gap:6px;margin-bottom:14px;flex-wrap:wrap}}
.type-filter-btn{{padding:5px 14px;border:none;border-radius:16px;font-size:12px;cursor:pointer;background:rgba(255,255,255,.6);color:#888;transition:.3s}}
.type-filter-btn.active{{background:linear-gradient(135deg,#10b981,#059669);color:#fff}}
.question-card{{background:rgba(255,255,255,.92);border-radius:16px;overflow:hidden;margin-bottom:16px;box-shadow:0 2px 12px rgba(0,0,0,.04)}}.question-card.hidden{{display:none}}
.q-top{{color:#fff;padding:12px 18px;display:flex;align-items:center;gap:10px}}
.q-num{{font-size:18px;font-weight:700}}.status-dot{{width:10px;height:10px;border-radius:50%;margin-left:auto}}
.score-circle{{width:32px;height:32px;border-radius:50%;border:2px solid;display:inline-flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;margin-left:auto;background:#fff}}
.q-info{{padding:8px 18px 0}}.type-label{{font-size:11px;color:#888;background:#f3f4f6;padding:2px 10px;border-radius:10px}}
.q-body{{padding:10px 18px;font-size:15px;line-height:1.75;color:#333}}
.opts-grid{{padding:0 18px 10px;display:flex;flex-wrap:wrap;gap:8px}}
.opt-pill{{display:flex;align-items:center;gap:6px;background:#f8f9ff;border-radius:8px;padding:6px 12px;font-size:13px;flex:1 1 45%;min-width:200px}}
.pill-label{{display:inline-flex;width:24px;height:24px;border-radius:50%;color:#fff;align-items:center;justify-content:center;font-size:12px;font-weight:600;flex-shrink:0}}.pill-text{{color:#444}}
.ans-grid{{padding:0 18px 14px;display:flex;flex-wrap:wrap;gap:8px}}
.ans-block{{flex:1;min-width:180px;padding:10px 12px;border-radius:8px;font-size:13px}}
.ans-block b{{display:block;font-size:11px;color:#888;margin-bottom:4px}}.ans-block p{{margin:0;color:#333}}
.mine{{background:#eef2ff}}.right{{background:#ecfdf5}}.note{{background:#fffbeb;font-style:italic}}
.question-image{{max-width:100%;height:auto;border-radius:8px;margin:6px 18px}}
.footer{{text-align:center;padding:16px;color:rgba(255,255,255,.5);font-size:10px;margin-top:10px}}
@media print{{body{{background:#fff;padding:0}}.question-card{{break-inside:avoid;box-shadow:none}}.filter-bar,.type-filter-bar{{display:none}}}}
</style></head><body>
<div class="main">
<div class="cover"><h1>{h(exp.homework_title)}</h1><div class="meta">{datetime.now().strftime("%Y-%m-%d %H:%M")}</div></div>
{stats_top}
<div class="filter-bar"><button class="filter-btn active" onclick="filterByStatus('all')">全部</button><button class="filter-btn" onclick="filterByStatus('correct')">答对</button><button class="filter-btn" onclick="filterByStatus('wrong')">答错</button></div>
{self._build_type_filter_bar(exp.questions, exp)}
{questions_html}
<div class="footer">Generated by {APP_NAME} v{__version__}</div>
</div>{self._filter_js()}</body></html>'''

    def get_preview_svg(self):
        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="200" height="140" viewBox="0 0 200 140">
  <defs><linearGradient id="mgbg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#e0c3fc"/><stop offset="0.5" stop-color="#8ec5fc"/><stop offset="1" stop-color="#f5d0fe"/></linearGradient></defs>
  <rect width="200" height="140" rx="6" fill="url(#mgbg)"/>
  <rect x="8" y="8" width="140" height="28" rx="10" fill="#6366f1"/>
  <rect x="40" y="16" width="76" height="5" rx="2" fill="white" opacity="0.9"/>
  <rect x="155" y="8" width="38" height="124" rx="8" fill="rgba(255,255,255,0.9)"/>
  <rect x="162" y="18" width="24" height="10" rx="2" fill="#6366f1" opacity="0.3"/>
  <rect x="162" y="34" width="24" height="10" rx="2" fill="#10b981" opacity="0.3"/>
  <rect x="162" y="50" width="24" height="10" rx="2" fill="#ef4444" opacity="0.3"/>
  <rect x="8" y="44" width="140" height="36" rx="8" fill="rgba(255,255,255,0.9)"/>
  <rect x="8" y="44" width="140" height="10" rx="8" fill="#10b981"/>
  <rect x="8" y="50" width="140" height="4" fill="#10b981"/>
  <rect x="14" y="60" width="80" height="3" rx="1" fill="#333" opacity="0.5"/>
  <rect x="14" y="67" width="50" height="3" rx="1" fill="#333" opacity="0.3"/>
  <rect x="8" y="86" width="140" height="36" rx="8" fill="rgba(255,255,255,0.9)"/>
  <rect x="8" y="86" width="140" height="10" rx="8" fill="#f59e0b"/>
  <rect x="8" y="92" width="140" height="4" fill="#f59e0b"/>
  <rect x="14" y="102" width="100" height="3" rx="1" fill="#333" opacity="0.5"/>
  <rect x="14" y="109" width="60" height="3" rx="1" fill="#333" opacity="0.3"/>
</svg>'''


# =====================================================================
# 模板 5: 极简笔记 — Notion 风格，纯内容
# =====================================================================
class NotionTemplate(HtmlTemplate):
    id = "notion"
    name = "极简笔记"
    description = "Notion 风格、纯内容排版、无边框"

    def render_html(self, exp) -> str:
        from .common import get_question_field
        s = exp.get_statistics()
        o = exp.options
        h = self._esc
        r = lambda imgs: self._render_imgs(imgs, o.include_images)

        questions_html = ""
        for i, q in enumerate(exp.questions, 1):
            ic = exp._is_correct(q)
            dc = "true" if ic else "false"
            prefix = ""
            if o.show_correct_status and ic is not None:
                prefix = '🟢 ' if ic else '🔴 '

            opts = ""
            for opt in q.get('options', []):
                if isinstance(opt, dict):
                    c = self._clean_opt_content(opt.get('content',''), opt.get('images',[]))
                    opts += f'<div class="opt">{h(opt.get("label",""))}. {h(c)}{r(opt.get("images",[]))}</div>'
                else:
                    opts += f'<div class="opt">{h(str(opt))}</div>'

            details = ""
            parts = []
            if o.include_my_answer:
                ma = exp._get_my_answer(q)
                if ma and '[图片' not in ma: parts.append(f'<span class="detail-key">我的答案</span> {h(ma)}')
                details += r(get_question_field(q, 'my_answer_images', []))
            if o.include_correct_answer:
                ca = exp._get_question_answer(q)
                if ca and '[图片' not in ca: parts.append(f'<span class="detail-key">正确答案</span> {h(ca)}')
                details += r(get_question_field(q, 'correct_answer_images', []))
            if o.include_score:
                sc = get_question_field(q, 'score', '')
                if sc: parts.append(f'<span class="detail-key">得分</span> {sc}')
            if parts:
                details = '<div class="details">' + '<span class="sep">·</span>'.join(parts) + '</div>' + details
            if o.include_analysis:
                an = exp._get_analysis(q)
                if an: details += f'<blockquote class="analysis">{h(an)}</blockquote>'

            num = f'{i}. ' if o.include_question_number else ''
            tp = f'<span class="type-tag">{h(exp._get_question_type(q))}</span> ' if o.include_question_type else ''

            qt_notion = exp._get_question_type(q)
            questions_html += f'''<div class="question-card" data-correct="{dc}" data-type="{h(qt_notion)}">
<h3>{prefix}{num}{tp}{h(exp._get_question_content(q))}</h3>
{r(get_question_field(q, 'content_images', []))}
{opts}{details}
</div>'''

        stats = ""
        if o.include_statistics:
            stats = f'<div class="stats">{s["total_questions"]} 题 · {s["correct_count"]} 正确 · {s["wrong_count"]} 错误 · 正确率 {s["accuracy"]}</div>'

        return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{h(exp.homework_title)}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;background:#fff;color:#37352f;padding:32px 20px;min-height:100vh;max-width:750px;margin:0 auto}}
h1{{font-size:32px;font-weight:700;margin-bottom:4px}}
.meta{{font-size:13px;color:#999;margin-bottom:8px}}
.stats{{font-size:13px;color:#787774;background:#f7f6f3;padding:8px 12px;border-radius:4px;margin-bottom:20px}}
.filter-bar{{display:flex;gap:4px;margin-bottom:20px}}
.filter-btn{{padding:4px 12px;border:none;background:#f7f6f3;border-radius:4px;font-size:12px;cursor:pointer;color:#787774}}
.filter-btn.active{{background:#37352f;color:#fff}}
.type-filter-bar{{display:flex;gap:4px;margin-bottom:16px;flex-wrap:wrap}}
.type-filter-btn{{padding:3px 10px;border:none;background:#f7f6f3;border-radius:4px;font-size:11px;cursor:pointer;color:#787774}}
.type-filter-btn.active{{background:#37352f;color:#fff}}
.question-card{{margin-bottom:24px;padding-bottom:20px;border-bottom:1px solid #f0efec}}.question-card.hidden{{display:none}}
h3{{font-size:16px;font-weight:600;line-height:1.6;margin-bottom:8px;color:#37352f}}
.type-tag{{display:inline-block;font-size:11px;color:#787774;background:#f7f6f3;padding:2px 8px;border-radius:4px;font-weight:400;vertical-align:middle}}
.opt{{font-size:14px;line-height:1.7;padding:2px 0;color:#37352f;padding-left:16px}}
.details{{font-size:13px;color:#787774;margin-top:8px;line-height:1.7}}
.detail-key{{color:#37352f;font-weight:600}}.sep{{margin:0 8px;color:#d3d1cb}}
blockquote.analysis{{margin-top:8px;padding:8px 16px;border-left:3px solid #f0efec;color:#787774;font-size:13px;font-style:italic}}
.question-image{{max-width:100%;height:auto;border-radius:4px;margin:6px 0}}
.footer{{margin-top:32px;text-align:center;font-size:10px;color:#d3d1cb}}
@media print{{.filter-bar{{display:none}}.question-card{{break-inside:avoid}}}}
</style></head><body>
<h1>{h(exp.homework_title)}</h1>
<div class="meta">{datetime.now().strftime("%Y-%m-%d %H:%M")}</div>
{stats}
<div class="filter-bar"><button class="filter-btn active" onclick="filterByStatus('all')">全部</button><button class="filter-btn" onclick="filterByStatus('correct')">正确</button><button class="filter-btn" onclick="filterByStatus('wrong')">错误</button></div>
{self._build_type_filter_bar(exp.questions, exp)}
{questions_html}
<div class="footer">Generated by {APP_NAME} v{__version__}</div>
{self._filter_js()}</body></html>'''

    def get_preview_svg(self):
        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="200" height="140" viewBox="0 0 200 140">
  <rect width="200" height="140" fill="#ffffff"/>
  <rect x="20" y="12" width="120" height="8" rx="2" fill="#37352f"/>
  <rect x="20" y="24" width="60" height="3" rx="1" fill="#999"/>
  <rect x="20" y="34" width="160" height="12" rx="2" fill="#f7f6f3"/>
  <rect x="24" y="38" width="80" height="4" rx="1" fill="#787774" opacity="0.5"/>
  <rect x="20" y="54" width="140" height="4" rx="1" fill="#37352f" opacity="0.7"/>
  <rect x="20" y="62" width="100" height="3" rx="1" fill="#37352f" opacity="0.4"/>
  <rect x="30" y="69" width="80" height="3" rx="1" fill="#37352f" opacity="0.3"/>
  <rect x="20" y="78" width="160" height="0.5" fill="#f0efec"/>
  <rect x="20" y="86" width="120" height="4" rx="1" fill="#37352f" opacity="0.7"/>
  <rect x="20" y="94" width="90" height="3" rx="1" fill="#37352f" opacity="0.4"/>
  <rect x="30" y="101" width="70" height="3" rx="1" fill="#37352f" opacity="0.3"/>
  <rect x="20" y="110" width="160" height="0.5" fill="#f0efec"/>
  <rect x="20" y="118" width="100" height="4" rx="1" fill="#37352f" opacity="0.7"/>
  <rect x="20" y="126" width="80" height="3" rx="1" fill="#37352f" opacity="0.4"/>
</svg>'''


# =====================================================================
# 自定义 CSS 模板
# =====================================================================
class CustomCssTemplate(HtmlTemplate):
    def __init__(self, css_file: Path):
        self.id = f"custom_{css_file.stem}"
        self.name = css_file.stem.replace('_', ' ').replace('-', ' ').title()
        self.description = f"自定义: {css_file.name}"
        self._css = css_file.read_text('utf-8')

    def render_html(self, exp) -> str:
        default = DefaultTemplate()
        html = default.render_html(exp)
        css = self._css
        html = re.sub(r'<style>.*?</style>', f'<style>\n{css}\n</style>', html, count=1, flags=re.DOTALL)
        return html

    def get_preview_svg(self):
        return _make_preview_svg("#f0f0f0","#888","#fff","#ddd","#888","#e8e8e8","#e8e8e8","#333","#bbb")


# =====================================================================
# 注册中心
# =====================================================================
class TemplateRegistry:
    def __init__(self):
        self._templates: Dict[str, HtmlTemplate] = {}
        for tmpl in [DefaultTemplate(), ExamPaperTemplate(), DarkTerminalTemplate(), MagazineTemplate(), NotionTemplate()]:
            self.register(tmpl)

    def register(self, template: HtmlTemplate):
        self._templates[template.id] = template

    def get(self, template_id: str) -> HtmlTemplate:
        return self._templates.get(template_id, self._templates.get('default'))

    def list_all(self) -> List[Dict]:
        return [{"id": t.id, "name": t.name, "description": t.description} for t in self._templates.values()]

    def load_custom_templates(self, directory: Path):
        if not directory.exists():
            return
        for css_file in sorted(directory.glob("*.css")):
            try:
                self.register(CustomCssTemplate(css_file))
                app_logger.info(f"加载自定义模板: {css_file.stem}")
            except Exception as e:
                app_logger.warning(f"加载自定义模板失败 {css_file.name}: {e}")


_registry: Optional[TemplateRegistry] = None

def get_template_registry() -> TemplateRegistry:
    global _registry
    if _registry is None:
        _registry = TemplateRegistry()
        from .common import PathManager
        custom_dir = PathManager.get_data_dir() / "custom_templates"
        custom_dir.mkdir(exist_ok=True)
        _registry.load_custom_templates(custom_dir)
    return _registry
