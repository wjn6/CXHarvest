#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
作业数量获取管理器
用于快速获取课程的作业数量，不需要完整解析作业内容
"""

from .common import (
    AppConstants, safe_json_load, safe_json_save, PathManager,
    os, json, requests, BeautifulSoup, re
)
from .enterprise_logger import app_logger

class HomeworkCountManager:
    """作业数量管理器"""
    
    def __init__(self, login_manager=None):
        """初始化作业数量管理器"""
        app_logger.info(f"HomeworkCountManager初始化 - 接收login_manager: {id(login_manager)}")
        if login_manager:
            self.login_manager = login_manager
        else:
            from .login_manager import LoginManager
            self.login_manager = LoginManager()
            
        self.headers = AppConstants.DEFAULT_HEADERS.copy()
        self.headers['Referer'] = 'https://mooc1.chaoxing.com'
        # 使用 PathManager 统一管理缓存路径
        self.count_cache_file = str(PathManager.get_file_path("homework_counts.json", "cache"))

    def get_session(self):
        """获取登录session"""
        app_logger.debug(f"HomeworkCountManager检查登录状态 - login_manager: {id(self.login_manager)}")
        if not self.login_manager:
            app_logger.info("login_manager为空")
            raise Exception("用户未登录，请先登录")
            
        if not self.login_manager.check_login_status():
            app_logger.info("用户未登录")
            raise Exception("用户未登录，请先登录")
            
        session = self.login_manager.session
        app_logger.info(f"获取到session，cookies数量: {len(session.cookies)}")
        return session

    def load_count_cache(self):
        """加载作业数量缓存"""
        return safe_json_load(self.count_cache_file, {})

    def save_count_cache(self, cache):
        """保存作业数量缓存"""
        safe_json_save(cache, self.count_cache_file)

    def extract_course_params(self, course_link):
        """从课程链接中提取参数"""
        try:
            courseid_match = re.search(r'courseid=(\d+)', course_link)
            clazzid_match = re.search(r'clazzid=(\d+)', course_link)
            cpi_match = re.search(r'cpi=(\d+)', course_link)
            
            if not all([courseid_match, clazzid_match, cpi_match]):
                raise ValueError("无法从课程链接中提取必要参数")
                
            return {
                'courseid': courseid_match.group(1),
                'clazzid': clazzid_match.group(1),
                'cpi': cpi_match.group(1)
            }
        except Exception as e:
            app_logger.error(f"提取课程参数失败: {e}")
            return None

    def get_encryption_params(self, courseid, clazzid, cpi):
        """获取加密参数"""
        try:
            course_url = "https://mooc2-ans.chaoxing.com/mooc2-ans/mycourse/studentcourse"
            params = {
                'courseid': courseid,
                'clazzid': clazzid, 
                'cpi': cpi,
                'ismooc2': '1'
            }
            
            session = self.get_session()
            response = session.get(course_url, params=params, headers=self.headers)
            
            if response.status_code != 200:
                raise Exception(f"访问课程主页失败: {response.status_code}")
                
            soup = BeautifulSoup(response.text, 'html.parser')
            enc_elem = soup.select_one('input[name="enc"]')
            work_enc_elem = soup.select_one('input[name="workEnc"]')
            exam_enc_elem = soup.select_one('input[name="examEnc"]')
            t_elem = soup.select_one('input[name="t"]')
            
            if not all([enc_elem, work_enc_elem, t_elem]):
                raise Exception("未能找到所有必需的加密参数")
                
            encryption_params = {
                'enc': enc_elem.get('value'),
                'workEnc': work_enc_elem.get('value'),
                'examEnc': exam_enc_elem.get('value') if exam_enc_elem else '',
                't': t_elem.get('value'),
                'stuenc': enc_elem.get('value')
            }
            return encryption_params
            
        except Exception as e:
            app_logger.error(f"获取加密参数失败: {e}")
            return None

    def build_homework_url(self, courseid, clazzid, cpi, encryption_params):
        """构建作业列表URL"""
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

    def get_homework_count_for_course(self, course_info):
        """获取指定课程的作业数量"""
        course_id = course_info.get('id')
        course_link = course_info.get('link')
        course_name = course_info.get('name', '未知课程')

        app_logger.info(f"正在获取课程 {course_name} 的作业数量...")
        app_logger.info(f"课程ID: {course_id}")
        app_logger.info(f"课程链接: {course_link}")

        if not course_id or not course_link:
            app_logger.info(f"课程信息不完整，无法获取作业数量: {course_name}")
            return 0

        # 尝试从缓存加载
        cache = self.load_count_cache()
        if course_id in cache:
            app_logger.info(f"从缓存获取作业数量: {course_name} -> {cache[course_id]} 个")
            return cache[course_id]

        try:
            app_logger.info(f"正在从网络获取 {course_name} 的作业数量...")
            
            # 检查登录状态
            try:
                session = self.get_session()
            except Exception as login_error:
                app_logger.error(f"登录检查失败: {login_error}")
                return 0
            
            course_params = self.extract_course_params(course_link)
            if not course_params:
                raise Exception("无法提取课程参数")

            encryption_params = self.get_encryption_params(
                course_params['courseid'],
                course_params['clazzid'],
                course_params['cpi']
            )
            if not encryption_params:
                raise Exception("无法获取加密参数")

            homework_url = self.build_homework_url(
                course_params['courseid'],
                course_params['clazzid'],
                course_params['cpi'],
                encryption_params
            )

            response = session.get(homework_url, headers=self.headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            # 查找作业列表项
            homework_items = soup.select('li[onclick*="goTask"]') or soup.select('.bottomList ul li')
            count = len(homework_items)

            app_logger.info(f"获取 {course_name} 作业数量: {count} 个")

            # 保存到缓存
            cache[course_id] = count
            self.save_count_cache(cache)

            return count

        except Exception as e:
            app_logger.error(f"获取 {course_name} 作业数量失败: {e}")
            return 0
