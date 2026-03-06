#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
课程管理器 - 核心业务逻辑
集成原项目的课程和作业列表功能
"""

# =============================================================================
# 标准库导入
# =============================================================================
import json
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

# =============================================================================
# 第三方库导入
# =============================================================================
import requests
from bs4 import BeautifulSoup

# =============================================================================
# 项目内部导入
# =============================================================================
from .common import (
    AppConstants, CourseInfo, NetworkError, ParseError,
    safe_json_load, safe_json_save, PathManager
)
from .login_manager import LoginManager
from .session_manager import SessionManagerMixin
from .enterprise_logger import app_logger, network_logger, file_logger

class CourseManager(SessionManagerMixin):
    """课程管理器类
    
    负责课程信息的获取、解析和缓存管理。继承SessionManagerMixin
    提供统一的session管理功能。
    
    Attributes:
        headers: HTTP请求头配置
        courses: 缓存的课程列表
        courses_file: 课程缓存文件路径
    """
    
    def __init__(self, login_manager: Optional[LoginManager] = None):
        """初始化课程管理器
        
        Args:
            login_manager: 可选的登录管理器实例，如果不提供将在需要时创建
        """
        # 调用父类初始化，设置session管理
        super().__init__(login_manager)
        
        if login_manager:
            app_logger.info("课程管理器使用提供的登录管理器实例初始化",
                          {"manager_id": id(login_manager)})
        else:
            app_logger.info("课程管理器将在需要时创建登录管理器")
            
        self.headers = AppConstants.DEFAULT_HEADERS.copy()
        self.headers['Referer'] = 'https://i.chaoxing.com/base'
        self.courses: List[Dict[str, Any]] = []
        # 使用 PathManager 获取课程缓存文件路径（放在 cache 目录）
        self.courses_file = PathManager.get_file_path("courses.json", "cache")
        
    def load_courses_from_cache(self) -> List[Dict[str, Any]]:
        """从缓存文件加载课程列表
        
        Returns:
            课程列表数据
        """
        courses = safe_json_load(self.courses_file, [])
        if courses:
            file_logger.file_operation("加载", self.courses_file, 
                                     {"courses_count": len(courses)})
        return courses
    
    def save_courses_to_cache(self, courses: List[Dict[str, Any]]) -> bool:
        """保存课程列表到缓存文件
        
        Args:
            courses: 要保存的课程列表
            
        Returns:
            是否保存成功
        """
        success = safe_json_save(courses, self.courses_file)
        if success:
            file_logger.file_operation("保存", self.courses_file,
                                     {"courses_count": len(courses)})
        else:
            app_logger.error("保存课程缓存失败", 
                           {"file": self.courses_file})
        return success

    def get_course_list(self, use_cache: bool = True) -> List[Dict[str, Any]]:
        """获取课程列表"""
        try:
            # 如果允许使用缓存，先尝试从缓存加载
            if use_cache:
                cached_courses = self.load_courses_from_cache()
                if cached_courses:
                    self.courses = cached_courses
                    return cached_courses
            
            session = self.get_session()
            
            # 直接调用课程数据API
            api_url = AppConstants.COURSE_LIST_URL
            app_logger.operation("从网络获取课程数据", "开始", 
                               {"api_url": api_url})

            # 准备POST数据，模拟AJAX请求
            data = {
                'courseType': '1',  # 1表示我学的课，0表示我教的课
                'courseFolderId': '0',
                'baseEducation': '1'
            }

            headers = self.headers.copy()
            headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
            headers['X-Requested-With'] = 'XMLHttpRequest'

            response = session.post(api_url, data=data, headers=headers)
            network_logger.network_request("POST", api_url, response.status_code)

            if response.status_code == 200:
                # 检测是否被重定向到登录页（超星可能返回200但内容是登录页）
                resp_text = response.text
                if '<title>用户登录</title>' in resp_text or 'passport2.chaoxing.com/login' in resp_text:
                    app_logger.warning("课程API返回了登录页面，session已失效")
                    self.invalidate_session()
                    from .common import LoginError
                    raise LoginError("登录已过期，请重新登录")
                
                courses = self.parse_course_data(resp_text)
                self.courses = courses
                
                # 仅在成功获取到课程时保存缓存
                if courses:
                    self.save_courses_to_cache(courses)
                
                app_logger.success("成功获取课程数据", 
                                 {"course_count": len(courses)})
                return courses
            else:
                error_msg = f"获取课程数据失败: HTTP {response.status_code}"
                app_logger.error(error_msg, {"status_code": response.status_code})
                raise Exception(error_msg)
                
        except Exception as e:
            app_logger.error(f"获取课程列表失败: {e}")
            # 如果在线获取失败，尝试使用缓存
            if not use_cache:
                cached_courses = self.load_courses_from_cache()
                if cached_courses:
                    app_logger.info("使用缓存的课程数据")
                    self.courses = cached_courses
                    return cached_courses
            raise
            
    def parse_course_data(self, html_content: str) -> List[Dict[str, Any]]:
        """解析课程数据 - 参考原始course_list.py"""
        app_logger.info("正在解析课程页面内容...")
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 找到课程列表容器
            course_list = soup.select('div.course.clearfix.learnCourse')

            if not course_list:
                app_logger.info("未找到课程列表元素，尝试其他选择器")
                course_list = soup.select('.course.clearfix')

            if not course_list:
                app_logger.info("未找到任何课程元素")
                app_logger.info(f"HTML内容长度: {len(html_content)}")
                app_logger.info(f"HTML前200字符: {html_content[:200]}")
                return []

            app_logger.info(f"找到 {len(course_list)} 个课程")
            courses = []
            
            for idx, course in enumerate(course_list, 1):
                try:
                    # 获取课程ID和班级ID
                    course_id_elem = course.select_one('input.courseId')
                    clazz_id_elem = course.select_one('input.clazzId')
                    
                    course_id = course_id_elem.get('value', '') if course_id_elem else ""
                    clazz_id = clazz_id_elem.get('value', '') if clazz_id_elem else ""
                    
                    # 获取课程信息区域
                    course_info = course.select_one('.course-info')
                    if not course_info:
                        app_logger.info(f"课程 {idx}: 未找到课程信息区域")
                        continue
                    
                    # 获取课程名称
                    course_name_elem = course_info.select_one('.course-name')
                    course_name = course_name_elem.get('title', '') if course_name_elem else ""
                    
                    # 获取教师名称
                    teacher_elem = course_info.select_one('.color3')
                    teacher = teacher_elem.get('title', '') if teacher_elem else ""
                    
                    # 获取课程描述
                    desc_elem = course_info.select_one('.margint10.line2.color2')
                    course_desc = desc_elem.get('title', '') if desc_elem else ""
                    
                    # 获取课程链接
                    link_elem = course_info.select_one('a.color1')
                    link = link_elem.get('href', '') if link_elem else ""
                    
                    # 获取封面图
                    cover_img_elem = course.select_one('.course-cover img')
                    cover_img = cover_img_elem.get('src', '') if cover_img_elem else ""
                    
                    # 修复图片URL格式问题
                    if cover_img:
                        app_logger.info(f" 原始图片URL: {cover_img}")
                        # 如果URL中有反斜杠，替换为正斜杠
                        if '\\' in cover_img:
                            cover_img = cover_img.replace('\\', '/')
                            app_logger.info(f" 修复后URL: {cover_img}")
                        
                        # 强制使用HTTPS并补充完整域名
                        if cover_img.startswith('//'):
                            cover_img = f"https:{cover_img}"
                        elif cover_img.startswith('http://'):
                            cover_img = cover_img.replace('http://', 'https://')
                        elif not cover_img.startswith('https://'):
                            if cover_img.startswith('./'):
                                cover_img = cover_img[2:]
                            if not cover_img.startswith('/'):
                                cover_img = f"https://p.ananas.chaoxing.com/star3/240_130c/{cover_img}"
                            else:
                                cover_img = f"https://p.ananas.chaoxing.com{cover_img}"
                        
                        app_logger.info(f" 修正后HTTPS图片URL: {cover_img}")
                    
                    # 获取任务进度
                    progress_text_elem = course.select_one('.l-txt')
                    progress_text = progress_text_elem.get_text(strip=True) if progress_text_elem else ""
                    
                    # 获取完成百分比
                    progress_percent_elem = course.select_one('.bar-tip')
                    progress_percent = progress_percent_elem.get_text(strip=True) if progress_percent_elem else "无进度信息"
                    
                    # 检查课程是否已结束
                    not_open_tip = course.select_one('.not-open-tip')
                    course_ended = False
                    if not_open_tip and '课程已结束' in not_open_tip.get_text():
                        course_ended = True
                    
                    # 确定课程状态：只有已结束和进行中两种状态
                    course_status = "进行中"
                    if course_ended:
                        course_status = "已结束"
                    
                    course_data = {
                        "序号": idx,
                        "id": course_id,  # 添加id字段
                        "name": course_name,  # 改为name字段以适配UI
                        "course_name": course_name,
                        "teacher": teacher,
                        "description": course_desc,
                        "link": link,
                        "image": cover_img,  # 改为image字段以适配UI背景图片
                        "cover_img": cover_img,
                        "progress_text": progress_text,
                        "progress_percent": progress_percent,
                        "progress": progress_percent,  # 添加progress字段
                        "status": course_status,
                        "course_id": course_id,
                        "clazz_id": clazz_id,
                        "homework_count": 0  # 初始作业数量
                    }
                    
                    courses.append(course_data)
                    app_logger.info(f"已解析课程: {course_name}")
                except Exception as e:
                    app_logger.info(f"解析课程信息出错: {e}")
                    continue
            
            return courses
        except Exception as e:
            app_logger.error(f"解析HTML内容时发生错误: {e}")
            return []
            
    def get_course_info_by_id(self, course_id):
        """根据课程ID获取课程信息"""
        for course in self.courses:
            if course.get('id') == course_id:
                return course
        return {'id': course_id, 'name': '未知课程', 'teacher': '未知教师'}
        
    def update_homework_count(self, course_id, count):
        """更新课程的作业数量"""
        for course in self.courses:
            if course.get('id') == course_id:
                course['homework_count'] = count
                break
                
    def search_courses(self, keyword):
        """搜索课程"""
        keyword = keyword.lower()
        results = []
        
        for course in self.courses:
            if (keyword in course.get('name', '').lower() or 
                keyword in course.get('teacher', '').lower() or
                keyword in course.get('description', '').lower()):
                results.append(course)
                
        return results
        
    def filter_courses_by_status(self, status):
        """按状态过滤课程"""
        return [course for course in self.courses if course.get('status') == status]
        
    def get_course_stats(self):
        """获取课程统计信息"""
        total_courses = len(self.courses)
        total_homework = sum(course.get('homework_count', 0) for course in self.courses)
        active_courses = len([c for c in self.courses if c.get('status') in ('进行中', 'active')])
        
        return {
            'total_courses': total_courses,
            'total_homework': total_homework,
            'active_courses': active_courses
        }
