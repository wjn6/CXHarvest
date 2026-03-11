#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
作业管理器
"""

# =============================================================================
# 标准库导入
# =============================================================================
import os
import json
import re
import time
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin, urlparse

# =============================================================================
# 第三方库导入
# =============================================================================
import requests
from bs4 import BeautifulSoup

# =============================================================================
# 项目内部导入
# =============================================================================
from .session_manager import SessionManagerMixin
from .enterprise_logger import app_logger, network_logger

class HomeworkManager(SessionManagerMixin):
    """作业管理器
    
    负责作业信息的获取、解析和管理。基于用户提供的homework_list_parser.py
    和link_builder.py实现，继承SessionManagerMixin提供统一的session管理。
    
    Attributes:
        headers: HTTP请求头配置
    """
    
    def __init__(self, login_manager: Optional[Any] = None):
        """初始化作业管理器
        
        Args:
            login_manager: 可选的登录管理器实例
        """
        # 调用父类初始化，设置session管理
        super().__init__(login_manager)
        
        if login_manager:
            app_logger.info("作业管理器使用提供的登录管理器实例初始化",
                          {"manager_id": id(login_manager)})
        else:
            app_logger.info("作业管理器将在需要时创建登录管理器")
            
        from .common import AppConstants
        self.headers = {
            'User-Agent': AppConstants.DEFAULT_HEADERS['User-Agent'],
            'Referer': 'https://mooc1.chaoxing.com'
        }

    def extract_course_params(self, course_data: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """从课程数据中提取参数 - 按照原始logic_builder.py逻辑
        
        Args:
            course_data (dict): 课程数据，包含id, clazz_id, link等
            
        Returns:
            dict: 包含courseid, clazzid, cpi的字典
        """
        try:
            app_logger.info("开始提取课程参数", 
                           {"available_keys": list(course_data.keys())})
            
            # 方法1：直接从课程数据中获取ID（优先）
            courseid = course_data.get('id', '')
            clazzid = course_data.get('clazz_id', '')
            cpi = ''
            
            # 方法2：如果没有直接ID，尝试从课程链接中提取所有参数
            course_link = course_data.get('link', '')
            if course_link:
                app_logger.debug("课程链接", {"link_preview": course_link[:100]})
                courseid_match = re.search(r'courseid=(\d+)', course_link)
                clazzid_match = re.search(r'clazzid=(\d+)', course_link)
                cpi_match = re.search(r'cpi=(\d+)', course_link)
                
                if courseid_match and not courseid:
                    courseid = courseid_match.group(1)
                if clazzid_match and not clazzid:
                    clazzid = clazzid_match.group(1)
                if cpi_match:
                    cpi = cpi_match.group(1)
                    app_logger.debug("从链接中提取到cpi", {"cpi": cpi})
            
            # 如果三个参数齐全，直接返回
            if courseid and clazzid and cpi:
                return {
                    'courseid': str(courseid),
                    'clazzid': str(clazzid),
                    'cpi': str(cpi)
                }
            
            # 方法3：如果链接中没有cpi，需要获取当前登录用户的ID
            if not courseid or not clazzid:
                app_logger.error("课程数据缺少必要字段", 
                               {"courseid": courseid, "clazzid": clazzid})
                return None
            
            # 尝试从cookie或session中获取用户ID
            cpi = self.get_user_id_from_session()
            if not cpi:
                app_logger.error("无法获取用户ID (cpi)")
                return None
            
            app_logger.debug("成功提取课程参数", 
                           {"courseid": courseid, "clazzid": clazzid, "cpi": cpi})
            
            return {
                'courseid': str(courseid),
                'clazzid': str(clazzid),
                'cpi': str(cpi)
            }
        except Exception as e:
            app_logger.error("提取课程参数失败", {"error": str(e)})
            return None
    
    def get_user_id_from_session(self) -> Optional[str]:
        """从session中获取用户ID"""
        try:
            # 方法1：访问用户主页获取ID
            response = self.get_session().get('https://i.chaoxing.com/base', headers=self.headers)
            if response.status_code == 200:
                # 尝试从页面JavaScript变量中提取用户ID
                content = response.text
                
                # 查找类似 var userid = "123456"; 的模式
                patterns = [
                    r'userid["\s]*[:=]["\s]*(\d+)',
                    r'uid["\s]*[:=]["\s]*(\d+)', 
                    r'puid["\s]*[:=]["\s]*(\d+)',
                    r'_uid["\s]*[:=]["\s]*(\d+)',
                    r'user_id["\s]*[:=]["\s]*(\d+)'
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, content, re.IGNORECASE)
                    if match:
                        user_id = match.group(1)
                        app_logger.debug("从页面获取到用户ID", {"user_id": user_id})
                        return user_id
                        
            # 方法2：从cookies中查找用户相关信息
            for cookie in self.get_session().cookies:
                if 'uid' in cookie.name.lower() or 'userid' in cookie.name.lower():
                    if cookie.value.isdigit():
                        app_logger.debug("从cookie获取到用户ID", 
                                       {"cookie_name": cookie.name, "user_id": cookie.value})
                        return cookie.value
                        
            app_logger.warning("未能获取到用户ID，使用默认值")
            return None
            
        except Exception as e:
            app_logger.error("获取用户ID失败", {"error": str(e)})
            return None

    def get_encryption_params(self, courseid: str, clazzid: str, cpi: str) -> Optional[Dict[str, str]]:
        """获取加密参数
        
        Args:
            courseid (str): 课程ID
            clazzid (str): 班级ID
            cpi (str): 用户ID
            
        Returns:
            dict: 包含加密参数的字典
        """
        try:
            app_logger.info("正在访问课程主页获取加密参数...")
            session = self.get_session()
            
            course_url = "https://mooc1.chaoxing.com/visit/stucoursemiddle"
            params = {
                'courseid': courseid,
                'clazzid': clazzid,
                'cpi': cpi,
                'ismooc2': '1'
            }

            response = session.get(course_url, params=params, headers=self.headers)

            if response.status_code != 200:
                app_logger.error(f"访问课程主页失败，状态码: {response.status_code}")
                return None

            # 使用BeautifulSoup解析页面
            soup = BeautifulSoup(response.text, 'html.parser')

            # 提取加密参数
            enc_elem = soup.select_one('input[name="enc"]')
            work_enc_elem = soup.select_one('input[name="workEnc"]')
            exam_enc_elem = soup.select_one('input[name="examEnc"]')
            openc_elem = soup.select_one('input[name="openc"]')
            t_elem = soup.select_one('input[name="t"]')

            if not all([enc_elem, work_enc_elem, exam_enc_elem, t_elem]):
                app_logger.info("未能找到所有必需的加密参数")
                return None

            encryption_params = {
                'enc': enc_elem.get('value'),
                'workEnc': work_enc_elem.get('value'),
                'examEnc': exam_enc_elem.get('value'),
                'openc': openc_elem.get('value') if openc_elem else '',
                't': t_elem.get('value'),
                'stuenc': enc_elem.get('value')  # stuenc就是基础的enc参数
            }

            app_logger.success("成功获取加密参数")
            return encryption_params
            
        except Exception as e:
            app_logger.error(f"获取加密参数失败: {e}")
            return None

    def build_homework_url(self, courseid: str, clazzid: str, cpi: str, encryption_params: Dict[str, str]) -> str:
        """构建作业列表URL
        
        Args:
            courseid (str): 课程ID
            clazzid (str): 班级ID
            cpi (str): 用户ID
            encryption_params (dict): 加密参数
            
        Returns:
            str: 作业列表URL
        """
        base_url = "https://mooc1.chaoxing.com/mooc2/work/list"

        params = [
            f"courseId={courseid}",
            f"classId={clazzid}",
            f"cpi={cpi}",
            "ut=s",
            f"t={encryption_params['t']}",
            f"stuenc={encryption_params['stuenc']}",
            f"enc={encryption_params['workEnc']}"
        ]

        return f"{base_url}?{'&'.join(params)}"

    def build_homework_url_with_page(self, base_url: str, page_num: int) -> str:
        """构建带页码的作业列表URL
        
        注意：超星分页URL格式与第一页不同
        - 第一页: /mooc2/work/list?courseId=...&ut=s&t=...&stuenc=...&enc=...
        - 分页: /mooc-ans/mooc2/work/list?courseId=...&enc=...&status=0&pageNum=N&topicId=0
        
        Args:
            base_url (str): 基础URL（第一页URL）
            page_num (int): 页码（从1开始）
            
        Returns:
            str: 带页码的URL
        """
        from urllib.parse import urlparse, parse_qs, urlencode
        
        try:
            parsed = urlparse(base_url)
            params = parse_qs(parsed.query, keep_blank_values=True)
            
            # 提取核心参数
            course_id = params.get('courseId', params.get('courseid', ['']))[0]
            class_id = params.get('classId', params.get('clazzid', ['']))[0]
            cpi = params.get('cpi', [''])[0]
            enc = params.get('enc', [''])[0]
            
            # 构建分页URL（使用 mooc-ans 路径，只需核心参数+pageNum）
            page_params = {
                'courseId': course_id,
                'classId': class_id,
                'cpi': cpi,
                'enc': enc,
                'pageNum': str(page_num)
            }
            
            page_url = f"https://mooc1.chaoxing.com/mooc-ans/mooc2/work/list?{urlencode(page_params)}"
            return page_url
            
        except Exception as e:
            # 降级：简单追加参数
            app_logger.warning(f"构建分页URL失败: {e}，使用降级方案")
            if '?' in base_url:
                return f"{base_url}&pageNum={page_num}"
            else:
                return f"{base_url}?pageNum={page_num}"

    def extract_total_pages(self, soup: BeautifulSoup) -> int:
        """从HTML中提取总页数
        
        Args:
            soup: BeautifulSoup对象
            
        Returns:
            int: 总页数，如果没有分页则返回1
        """
        try:
            max_page = 1
            
            # 方法1: 从JavaScript代码中提取 pageNum（分页是JS动态加载的）
            # 查找类似: $("#page").paging({ nowPage: 1, pageNum: 2, ... })
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string:
                    # 匹配 pageNum : 2 或 pageNum: 2
                    match = re.search(r'pageNum\s*:\s*(\d+)', script.string)
                    if match:
                        max_page = int(match.group(1))
                        app_logger.info(f" 从JS中检测到分页，共 {max_page} 页")
                        return max_page
            
            # 方法2: 从分页容器的li元素提取（如果JS已渲染）
            page_div = soup.select_one('.pageDiv, #page')
            if page_div:
                page_items = page_div.select('li')
                for item in page_items:
                    classes = item.get('class', [])
                    if any(cls in classes for cls in ['xl-prevPage', 'xl-nextPage', 'xl-disabled', 'xl-disabled2']):
                        continue
                    text = item.get_text(strip=True)
                    if text.isdigit():
                        page_num = int(text)
                        if page_num > max_page:
                            max_page = page_num
                
                if max_page > 1:
                    app_logger.info(f" 从DOM中检测到分页，共 {max_page} 页")
                    return max_page
            
            app_logger.info(f" 检测到分页，共 {max_page} 页")
            return max_page
            
        except Exception as e:
            app_logger.warning(f" 提取页数失败: {e}，假定只有1页")
            return 1

    def fetch_homework_list_online(self, homework_url: str, course_name: str = "未知课程") -> Optional[str]:
        """在线获取作业列表
        
        Args:
            homework_url (str): 作业列表URL
            course_name (str): 课程名称
            
        Returns:
            str: HTML内容，失败返回None
        """
        try:
            app_logger.info(f" 正在访问 {course_name} 的作业列表...")
            session = self.get_session()

            response = session.get(homework_url, headers=self.headers, timeout=30)

            if response.status_code == 200:
                resp_text = response.text
                if '<title>用户登录</title>' in resp_text or 'passport2.chaoxing.com/login' in resp_text:
                    app_logger.warning(f"作业列表API返回了登录页面，session已失效")
                    self.invalidate_session()
                    return None
                app_logger.success(f" 成功获取 {course_name} 的作业列表")
                return resp_text
            else:
                app_logger.error(f" 获取 {course_name} 作业列表失败，状态码: {response.status_code}")
                return None

        except Exception as e:
            app_logger.error(f" 访问 {course_name} 作业列表失败: {e}")
            return None

    def find_homework_containers(self, soup: BeautifulSoup) -> List[Any]:
        """查找作业容器元素
        
        Args:
            soup: BeautifulSoup对象
            
        Returns:
            list: 作业容器列表
        """
        # 优先查找超星学习通的特定结构
        # 查找 .bottomList ul li 结构
        bottom_list = soup.select('.bottomList ul li')
        if bottom_list:
            app_logger.info(f" 找到超星学习通作业列表结构: .bottomList ul li ({len(bottom_list)} 个)")
            return bottom_list

        # 查找带有 onclick="goTask(this)" 的 li 元素
        task_items = soup.select('li[onclick*="goTask"]')
        if task_items:
            app_logger.info(f" 找到作业任务项: li[onclick*='goTask'] {len(task_items)} 个")
            return task_items

        # 查找带有 data 属性的 li 元素
        data_items = soup.select('li[data]')
        if data_items:
            app_logger.info(f" 找到带data属性的列表项: li[data] ({len(data_items)} 个)")
            return data_items

        # 尝试其他可能的选择器
        selectors = [
            '.workList',  # 常见的作业列表类名
            '.homework-item',
            '.work-item',
            '.assignment-item',
            'tr[onclick*="work"]',  # 表格行形式
            'div[onclick*="work"]',  # div形式
            '.list-item',
            'li[data-id]',  # 列表项形式
            '[class*="work"]',  # 包含work的类名
            '[id*="work"]'   # 包含work的ID
        ]

        for selector in selectors:
            containers = soup.select(selector)
            if containers:
                app_logger.info(f" 使用选择器找到容器: {selector}")
                return containers

        return []

    def is_valid_homework_title(self, title: str) -> bool:
        """验证是否为有效的作业标题
        
        Args:
            title (str): 标题文本
            
        Returns:
            bool: 是否为有效作业标题
        """
        if not title or len(title.strip()) < 2:
            return False
            
        # 需要过滤的无效标题
        invalid_patterns = [
            r'作业已刷新.*按.*tab.*键',  # "作业已刷新，请按tab键"
            r'请.*tab.*键',
            r'刷新.*tab',
            r'^tab$',
            r'^\s*$',  # 空白内容
            r'^[\d\s]*$',  # 只有数字和空格
            r'^[^\u4e00-\u9fa5\w]{1,3}$',  # 只有1-3个特殊符号
            r'加载中',
            r'loading',
            r'正在加载',
            r'暂无.*',
            r'没有.*作业',
            r'无.*作业',
            r'点击.*',
            r'请.*操作',
            r'系统.*提示',
            r'^提示.*',
        ]
        
        title_lower = title.lower().strip()
        
        for pattern in invalid_patterns:
            if re.search(pattern, title, re.IGNORECASE):
                app_logger.debug(f"  过滤无效作业标题: '{title}'")
                return False
                
        return True

    def extract_homework_info(self, container: Any, index: int, course_name: str = "") -> Optional[Dict[str, Any]]:
        """从容器中提取作业信息
        
        Args:
            container: 作业容器元素
            index (int): 作业序号
            course_name (str): 课程名称
            
        Returns:
            dict: 作业信息字典
        """
        try:
            homework_info = {
                'index': index,
                'title': '未知作业',
                'url': '',
                'status': '未知状态',
                'deadline': '',
                'score': '',
                'submit_status': '',
                'description': '',
                'course_name': course_name
            }

            # 提取作业标题
            title = self.extract_title(container)
            if title:
                if self.is_valid_homework_title(title):
                    homework_info['title'] = title
                else:
                    app_logger.warning(f"  作业被过滤，原因: 标题 '{title}' 被判定为无效")
                    return None
            else:
                app_logger.warning(f"  作业被过滤，原因: 未能提取到标题 (容器索引: {index})")
                app_logger.debug(f"  容器HTML片段预览: {str(container)[:300]}...")
                return None

            # 提取作业URL
            url = self.extract_url(container)
            if url:
                homework_info['url'] = url
                app_logger.success(f" 成功提取作业URL: {url}")
            else:
                app_logger.info(f"  未能提取作业URL，容器内容预览: {str(container)[:200]}...")

            # 提取作业状态
            status = self.extract_status(container)
            if status:
                homework_info['status'] = status

            # 提取截止时间
            deadline = self.extract_deadline(container)
            if deadline:
                homework_info['deadline'] = deadline

            # 提取分数信息
            score = self.extract_score(container)
            if score:
                homework_info['score'] = score

            # 提取提交状态
            submit_status = self.extract_submit_status(container)
            if submit_status:
                homework_info['submit_status'] = submit_status

            # 提取描述信息
            description = self.extract_description(container)
            if description:
                homework_info['description'] = description

            return homework_info

        except Exception as e:
            app_logger.error(f" 提取作业信息失败: {e}")
            return None

    def extract_title(self, container: Any) -> Optional[str]:
        """提取作业标题"""
        # 超星学习通特定结构：.right-content p.overHidden2
        title_element = container.select_one('.right-content p.overHidden2')
        if title_element:
            title = title_element.get_text(strip=True)
            if title and len(title) > 1:
                return title

        # 从 aria-label 属性中提取标题（格式：标题 ; 状态）
        aria_label = container.get('aria-label', '')
        if aria_label:
            # 分割 aria-label，取第一部分作为标题
            parts = aria_label.split(' ; ')
            if parts:
                title = parts[0].strip()
                if title and len(title) > 1:
                    return title

        # 尝试其他可能的标题选择器
        title_selectors = [
            '.workName', '.homework-title', '.work-title', '.title',
            'h3', 'h4', 'h5', '.name', '.subject', 'a[title]',
            '[class*="title"]', '[class*="name"]'
        ]

        for selector in title_selectors:
            element = container.select_one(selector)
            if element:
                title = element.get_text(strip=True)
                if title and len(title) > 2:  # 过滤太短的标题
                    return title

        # 如果没有找到，尝试从链接的title属性获取
        link = container.find('a')
        if link and link.get('title'):
            return link.get('title').strip()

        # 最后尝试从容器的文本内容中提取
        text = container.get_text(strip=True)
        if text:
            # 取前50个字符作为标题
            return text[:50].strip()

        return None

    def extract_url(self, container: Any) -> Optional[str]:
        """提取作业URL - 参考homework_list_parser.py逻辑"""
        # 超星学习通特定结构：从 data 属性获取URL
        data_url = container.get('data', '')
        if data_url:
            app_logger.info(f" 找到data属性URL: {data_url[:100]}...")
            # 处理HTML实体编码
            data_url = data_url.replace('&amp;', '&')
            if data_url.startswith('http'):
                return data_url
            elif data_url.startswith('/'):
                return 'https://mooc1.chaoxing.com' + data_url

        # 查找链接元素
        link = container.find('a', href=True)
        if link:
            href = link.get('href')
            if href:
                app_logger.info(f" 找到链接href: {href[:100]}...")
                # 处理相对URL
                if href.startswith('/'):
                    href = 'https://mooc1.chaoxing.com' + href
                elif href.startswith('http'):
                    return href
                else:
                    href = 'https://mooc1.chaoxing.com/' + href
                return href

        # 查找onclick事件中的URL - 参考homework_list_parser.py
        onclick = container.get('onclick', '')
        if onclick:
            app_logger.info(f" 找到onclick: {onclick[:100]}...")
            # 提取URL模式
            url_match = re.search(r'["\']([^"\']*(?:work|homework|assignment)[^"\']*)["\']', onclick)
            if url_match:
                url = url_match.group(1)
                app_logger.info(f" onclick中提取URL: {url}")
                if not url.startswith('http'):
                    url = 'https://mooc1.chaoxing.com' + url
                return url

        app_logger.info(" 未能提取到作业URL")
        return None

    def extract_status(self, container: Any) -> str:
        """提取作业状态"""
        # 1. 优先查找特定的状态类名
        status_selectors = [
            '.right-content p.status',  # 旧版
            '.status',                  # 通用
            '.zt',                      # 状态缩写
            '.mark',                    # 分数/状态标记
            'strong',                   # 强调文本常用于状态
            '[class*="status"]',
            '.fr p',                    # 右浮动文本
            '.color-green',             # 完成颜色
            '.color-red',               # 未完成颜色
            '.color-gray'               # 已截止颜色
        ]
        
        for selector in status_selectors:
            elements = container.select(selector)
            for element in elements:
                text = element.get_text(strip=True)
                # 过滤掉非状态的干扰文本（如时间）
                if not text or len(text) > 10 or ':' in text or '-' in text:
                    continue
                    
                # 检查是否为已知状态词
                if any(k in text for k in ['完成', '提交', '截止', '批阅', '分']):
                    return text

        # 2. 从 aria-label 属性中提取
        aria_label = container.get('aria-label', '')
        if aria_label:
            parts = aria_label.split(' ; ')
            if len(parts) > 1:
                return parts[1].strip()

        # 3. 基于按钮文本推断 (非常有效)
        # 如果有 "去完成" -> 待完成
        # 如果有 "查看" 或 "查看作业" -> 通常是 已完成 或 待批阅
        action_text = container.get_text()
        if '去完成' in action_text or '做作业' in action_text:
            return '待完成'
        
        # 4. 基于分数推断
        # 如果能提取到分数，状态肯定是已完成/待批阅
        if self.extract_score(container):
            return '已完成'

        # 5. 通用关键词匹配 (最后的手段)
        status_keywords = {
            '已完成': ['已完成', '已提交', '已批阅'],
            '待批阅': ['待批阅', '待评分'],
            '待完成': ['待完成', '未交', '未提交'],
            '已截止': ['已截止', '过期'],
            '进行中': ['进行中']
        }

        for status, keywords in status_keywords.items():
            for keyword in keywords:
                if keyword in action_text:
                    return status

        return '未知状态'

    def extract_deadline(self, container: Any) -> Optional[str]:
        """提取截止时间"""
        text = container.get_text()

        # 匹配日期时间格式
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}',
            r'\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}',
            r'\d{2}-\d{2}\s+\d{2}:\d{2}',
            r'\d{2}/\d{2}\s+\d{2}:\d{2}'
        ]

        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group()

        return None

    def extract_score(self, container: Any) -> Optional[str]:
        """提取分数信息"""
        text = container.get_text()

        # 匹配分数格式
        score_patterns = [
            r'(\d+(?:\.\d+)?)\s*[/／]\s*(\d+(?:\.\d+)?)',  # 85/100
            r'(\d+(?:\.\d+)?)\s*分',  # 85分
            r'得分[：:]\s*(\d+(?:\.\d+)?)',  # 得分：85
            r'分数[：:]\s*(\d+(?:\.\d+)?)'   # 分数：85
        ]

        for pattern in score_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group()

        return None

    def extract_submit_status(self, container: Any) -> Optional[str]:
        """提取提交状态"""
        text = container.get_text()

        submit_keywords = {
            '已提交': ['已提交', '提交成功', 'submitted'],
            '未提交': ['未提交', '待提交', 'not submitted'],
            '已批改': ['已批改', '已评分', 'graded'],
            '待批改': ['待批改', '待评分', 'pending review']
        }

        for status, keywords in submit_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    return status

        return None

    def extract_description(self, container: Any) -> Optional[str]:
        """提取作业描述"""
        # 查找描述相关的元素
        desc_selectors = [
            '.description', '.desc', '.content', '.summary',
            '[class*="desc"]', '[class*="content"]'
        ]

        for selector in desc_selectors:
            element = container.select_one(selector)
            if element:
                desc = element.get_text(strip=True)
                if desc and len(desc) > 5:
                    return desc[:200]  # 限制长度

        return None

    def parse_homework_content(self, html_content: str, course_name: str = "") -> List[Dict[str, Any]]:
        """解析作业列表HTML内容
        
        Args:
            html_content (str): HTML内容
            course_name (str): 课程名称
            
        Returns:
            list: 作业列表
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 查找作业列表容器
            homework_containers = self.find_homework_containers(soup)
            
            if not homework_containers:
                app_logger.info(" 未找到作业列表容器")
                return []
            
            app_logger.info(f" 找到 {len(homework_containers)} 个作业容器")
            
            # 解析每个作业
            homework_list = []
            for i, container in enumerate(homework_containers, 1):
                app_logger.info(f"   解析作业 {i}: ")
                homework_info = self.extract_homework_info(container, i, course_name)
                if homework_info:
                    homework_list.append(homework_info)
                    app_logger.info(homework_info['title'])
                else:
                    app_logger.debug("已过滤无效内容")
            
            return homework_list
                
        except Exception as e:
            app_logger.error(f" 解析HTML内容失败: {e}")
            return []

    def get_homework_list(self, course_data):
        """获取指定课程的作业列表（支持多页）
        
        Args:
            course_data (dict): 课程信息
            
        Returns:
            list: 作业列表（包含所有页面的作业）
        """
        try:
            course_name = course_data.get('name', '未知课程')
            
            app_logger.info(f" 正在获取课程 {course_name} 的作业列表...")
            
            # 提取课程参数
            course_params = self.extract_course_params(course_data)
            if not course_params:
                app_logger.info(f" 无法提取课程 {course_name} 的参数")
                return []
            
            # 获取加密参数
            encryption_params = self.get_encryption_params(
                course_params['courseid'],
                course_params['clazzid'],
                course_params['cpi']
            )
            if not encryption_params:
                app_logger.info(f" 无法获取课程 {course_name} 的加密参数")
                return []
            
            # 构建作业列表基础URL
            base_homework_url = self.build_homework_url(
                course_params['courseid'],
                course_params['clazzid'],
                course_params['cpi'],
                encryption_params
            )
            
            # 获取第一页作业列表
            first_page_content = self.fetch_homework_list_online(base_homework_url, course_name)
            if not first_page_content:
                app_logger.info(f" 无法获取课程 {course_name} 的作业列表页面")
                return []
            
            # 解析第一页并获取总页数
            from bs4 import BeautifulSoup
            first_soup = BeautifulSoup(first_page_content, 'html.parser')
            total_pages = self.extract_total_pages(first_soup)
            
            # 解析第一页作业
            all_homework = self.parse_homework_content(first_page_content, course_name)
            app_logger.info(f" 第1页找到 {len(all_homework)} 个作业")
            
            # 如果有多页，继续获取后续页面
            if total_pages > 1:
                app_logger.info(f" 检测到多页作业列表，共 {total_pages} 页，正在获取剩余页面...")
                
                for page_num in range(2, total_pages + 1):
                    # 构建带页码的URL
                    page_url = self.build_homework_url_with_page(base_homework_url, page_num)
                    app_logger.info(f" 第{page_num}页URL: {page_url}")
                    
                    # 获取该页内容
                    page_content = self.fetch_homework_list_online(page_url, f"{course_name} (第{page_num}页)")
                    if page_content:
                        # 解析该页作业
                        page_homework = self.parse_homework_content(page_content, course_name)
                        app_logger.info(f" 第{page_num}页找到 {len(page_homework)} 个作业")
                        
                        # 合并到总列表
                        all_homework.extend(page_homework)
                    else:
                        app_logger.warning(f" 获取第{page_num}页失败，跳过")
            
            # 去重（根据URL或title去重，防止重复）
            seen_urls = set()
            unique_homework = []
            for hw in all_homework:
                hw_url = hw.get('url', '')
                if hw_url and hw_url not in seen_urls:
                    seen_urls.add(hw_url)
                    unique_homework.append(hw)
                elif not hw_url:
                    # 没有URL的作业，基于标题去重
                    hw_title = hw.get('title', '')
                    if hw_title and hw_title not in seen_urls:
                        seen_urls.add(hw_title)
                        unique_homework.append(hw)
            
            app_logger.info(f" 课程 {course_name} 共找到 {len(unique_homework)} 个作业（去重后）")
            return unique_homework
            
        except Exception as e:
            app_logger.error(f" 获取作业列表失败: {e}")
            return []
