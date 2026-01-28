#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导出历史管理模块
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

from core.enterprise_logger import app_logger


class ExportHistoryManager:
    """导出历史管理器"""
    
    def __init__(self, history_file: str = None):
        """初始化
        
        Args:
            history_file: 历史记录文件路径，默认为应用目录下的 export_history.json
        """
        if history_file is None:
            # 默认保存在应用目录
            app_dir = Path(__file__).parent.parent
            history_file = str(app_dir / "export_history.json")
        
        self.history_file = history_file
        self._history: List[Dict] = []
        self._load_history()
    
    def _load_history(self):
        """从文件加载历史记录"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self._history = json.load(f)
                app_logger.debug(f"加载了 {len(self._history)} 条导出历史")
        except Exception as e:
            app_logger.warning(f"加载导出历史失败: {e}")
            self._history = []
    
    def _save_history(self):
        """保存历史记录到文件"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self._history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            app_logger.warning(f"保存导出历史失败: {e}")
    
    def add_record(self, 
                   course_name: str,
                   homework_titles: List[str],
                   question_count: int,
                   export_format: str,
                   file_path: str,
                   file_size: int = 0) -> Dict:
        """添加导出记录
        
        Args:
            course_name: 课程名称
            homework_titles: 作业标题列表
            question_count: 题目数量
            export_format: 导出格式 (HTML/JSON/Markdown/Word/PDF)
            file_path: 导出文件路径
            file_size: 文件大小（字节）
            
        Returns:
            新创建的记录
        """
        record = {
            "id": len(self._history) + 1,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "course_name": course_name,
            "homework_titles": homework_titles,
            "homework_count": len(homework_titles),
            "question_count": question_count,
            "export_format": export_format,
            "file_path": file_path,
            "file_size": file_size,
            "file_exists": os.path.exists(file_path)
        }
        
        self._history.insert(0, record)  # 新记录插入到最前面
        
        # 限制历史记录数量（最多保存100条）
        if len(self._history) > 100:
            self._history = self._history[:100]
        
        self._save_history()
        app_logger.info(f"添加导出记录: {course_name} - {export_format}")
        
        return record
    
    def get_history(self, limit: int = None) -> List[Dict]:
        """获取历史记录
        
        Args:
            limit: 返回记录数量限制
            
        Returns:
            历史记录列表（按时间倒序）
        """
        # 更新文件存在状态
        for record in self._history:
            record["file_exists"] = os.path.exists(record.get("file_path", ""))
        
        if limit:
            return self._history[:limit]
        return self._history
    
    def delete_record(self, record_id: int) -> bool:
        """删除指定记录
        
        Args:
            record_id: 记录ID
            
        Returns:
            是否删除成功
        """
        for i, record in enumerate(self._history):
            if record.get("id") == record_id:
                self._history.pop(i)
                self._save_history()
                return True
        return False
    
    def clear_history(self):
        """清空所有历史记录"""
        self._history = []
        self._save_history()
        app_logger.info("已清空导出历史")
    
    def get_statistics(self) -> Dict:
        """获取统计信息
        
        Returns:
            统计信息字典
        """
        if not self._history:
            return {
                "total_exports": 0,
                "total_questions": 0,
                "formats": {},
                "courses": []
            }
        
        formats = {}
        courses = set()
        total_questions = 0
        
        for record in self._history:
            fmt = record.get("export_format", "未知")
            formats[fmt] = formats.get(fmt, 0) + 1
            courses.add(record.get("course_name", ""))
            total_questions += record.get("question_count", 0)
        
        return {
            "total_exports": len(self._history),
            "total_questions": total_questions,
            "formats": formats,
            "courses": list(courses)
        }


# 全局单例
_export_history_manager: Optional[ExportHistoryManager] = None


def get_export_history_manager() -> ExportHistoryManager:
    """获取导出历史管理器单例"""
    global _export_history_manager
    if _export_history_manager is None:
        _export_history_manager = ExportHistoryManager()
    return _export_history_manager
