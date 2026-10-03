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

    # 缓存有效期（秒）：作业数量会随学期推进变化，
    # 永久缓存会导致整个学期都显示学期初抓到的旧数量
    CACHE_TTL = 7 * 24 * 3600  # 7 天
    
    def __init__(self, login_manager=None):
        super().__init__(login_manager)
        self.headers = AppConstants.DEFAULT_HEADERS.copy()
        self.headers['Referer'] = 'https://mooc1.chaoxing.com'
        self.count_cache_file = str(PathManager.get_file_path("homework_counts.json", "cache"))

    def load_count_cache(self):
        cache = safe_json_load(self.count_cache_file, {})
        return cache if isinstance(cache, dict) else {}

    def save_count_cache(self, cache):
        safe_json_save(cache, self.count_cache_file)

    def _read_cached_count(self, course_id: str):
        """读取未过期的缓存数量，返回 (命中, 数量)"""
        cache = self.load_count_cache()
        entry = cache.get(course_id)
        if entry is None:
            return False, 0
        # 兼容旧的裸数值格式（只有数量、没有时间戳），视为已过期
        if not isinstance(entry, dict):
            return False, 0
        import time
        try:
            age = time.time() - float(entry.get('ts', 0))
            count = max(0, int(entry.get('count', 0)))
        except (TypeError, ValueError):
            return False, 0
        if age < 0 or age > self.CACHE_TTL:
            return False, 0
        return True, count

    def _write_cached_count(self, course_id: str, count: int):
        import time
        cache = self.load_count_cache()
        cache[course_id] = {'count': int(count), 'ts': time.time()}
        self.save_count_cache(cache)

    def peek_cached_count(self, course_id) -> int:
        """只读本地缓存的作业数量，不发网络请求；未命中或过期返回 0"""
        if not course_id:
            return 0
        hit, count = self._read_cached_count(str(course_id))
        return count if hit else 0

    def remember_count(self, course_id, count: int):
        """作业列表加载完成后回写真实数量，省掉一次只为计数的列表请求"""
        if course_id:
            self._write_cached_count(str(course_id), count)

    def get_homework_count_for_course(self, course_info: dict) -> int:
        """获取指定课程的作业数量（优先缓存）"""
        course_id = course_info.get('id')
        course_name = course_info.get('name', '未知课程')

        if not course_id:
            return 0

        hit, cached = self._read_cached_count(course_id)
        if hit:
            return cached

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

            self._write_cached_count(course_id, count)
            app_logger.info(f"获取 {course_name} 作业数量: {count} 个")
            return count

        except Exception as e:
            app_logger.error(f"获取 {course_name} 作业数量失败: {e}")
            return 0
