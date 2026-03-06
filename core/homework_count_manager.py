#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
作业数量获取管理器
复用 HomeworkManager 的参数提取和URL构建逻辑，仅做轻量计数
"""

from bs4 import BeautifulSoup

from .common import AppConstants, safe_json_load, safe_json_save, PathManager
from .session_manager import SessionManagerMixin
from .enterprise_logger import app_logger


class HomeworkCountManager(SessionManagerMixin):
    """作业数量管理器
    
    继承 SessionManagerMixin 获得统一的 session 管理能力，
    复用 HomeworkManager 的 URL 构建逻辑进行轻量计数。
    """
    
    def __init__(self, login_manager=None):
        super().__init__(login_manager)
        self.headers = AppConstants.DEFAULT_HEADERS.copy()
        self.headers['Referer'] = 'https://mooc1.chaoxing.com'
        self.count_cache_file = str(PathManager.get_file_path("homework_counts.json", "cache"))

    def load_count_cache(self):
        return safe_json_load(self.count_cache_file, {})

    def save_count_cache(self, cache):
        safe_json_save(cache, self.count_cache_file)

    def get_homework_count_for_course(self, course_info: dict) -> int:
        """获取指定课程的作业数量（优先缓存）"""
        course_id = course_info.get('id')
        course_name = course_info.get('name', '未知课程')

        if not course_id:
            return 0

        cache = self.load_count_cache()
        if course_id in cache:
            return cache[course_id]

        try:
            from .homework_manager import HomeworkManager
            hm = HomeworkManager(self._login_manager)
            course_params = hm.extract_course_params(course_info)
            if not course_params:
                return 0

            encryption_params = hm.get_encryption_params(
                course_params['courseid'],
                course_params['clazzid'],
                course_params['cpi']
            )
            if not encryption_params:
                return 0

            homework_url = hm.build_homework_url(
                course_params['courseid'],
                course_params['clazzid'],
                course_params['cpi'],
                encryption_params
            )

            session = self.get_session()
            response = session.get(homework_url, headers=self.headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            homework_items = soup.select('li[onclick*="goTask"]') or soup.select('.bottomList ul li')
            count = len(homework_items)

            cache[course_id] = count
            self.save_count_cache(cache)
            app_logger.info(f"获取 {course_name} 作业数量: {count} 个")
            return count

        except Exception as e:
            app_logger.error(f"获取 {course_name} 作业数量失败: {e}")
            return 0
