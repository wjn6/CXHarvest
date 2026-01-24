#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片处理模块
提供高效的图片处理功能，包括Base64转换、图片压缩等
"""

import base64
import io
import tempfile
import concurrent.futures
import threading
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
from PIL import Image
import requests

from .common import safe_json_load, safe_json_save
from .exceptions import handle_exceptions, NetworkError, FileOperationError
from .enterprise_logger import app_logger

class ImageProcessor:
    """图片处理器 - 优化内存使用和处理性能"""
    
    def __init__(self, max_cache_size: int = 100, max_image_size: int = 1024):
        """初始化图片处理器
        
        Args:
            max_cache_size: 最大缓存图片数量
            max_image_size: 图片最大尺寸（像素），用于压缩
        """
        self.max_cache_size = max_cache_size
        self.max_image_size = max_image_size
        self._cache = {}  # URL -> base64 缓存
        self._cache_lock = threading.Lock()
        self._session = None
        
    def set_session(self, session: requests.Session):
        """设置网络会话"""
        self._session = session
    
    @handle_exceptions
    def process_image_url(self, url: str, compress: bool = True) -> Optional[str]:
        """处理图片URL，转换为Base64
        
        Args:
            url: 图片URL
            compress: 是否压缩图片
            
        Returns:
            Base64编码的图片数据，失败返回None
        """
        if not url or not url.strip():
            return None
            
        # 检查是否已经是base64数据
        if url.startswith('data:image'):
            return url
            
        # 检查缓存
        with self._cache_lock:
            if url in self._cache:
                return self._cache[url]
        
        try:
            # 处理URL格式
            processed_url = self._normalize_url(url)
            
            # 下载图片
            image_data = self._download_image(processed_url)
            if not image_data:
                return None
            
            # 压缩图片（如果需要）
            if compress:
                image_data = self._compress_image(image_data)
            
            # 转换为Base64
            base64_data = self._to_base64(image_data)
            
            # 缓存结果
            self._cache_image(url, base64_data)
            
            return base64_data
            
        except Exception as e:
            app_logger.error(f" 处理图片失败 {url}: {e}")
            return None
    
    def _normalize_url(self, url: str) -> str:
        """标准化URL格式"""
        # 处理相对路径
        if url.startswith('//'):
            return f"https:{url}"
        elif url.startswith('/'):
            return f"https://mooc1.chaoxing.com{url}"
        elif url.startswith('http://'):
            return url.replace('http://', 'https://')
        elif not url.startswith('https://'):
            # 补充超星学习通的图片域名
            if not url.startswith('/'):
                url = f"https://p.ananas.chaoxing.com/star3/240_130c/{url}"
            else:
                url = f"https://p.ananas.chaoxing.com{url}"
        
        return url
    
    def _download_image(self, url: str) -> Optional[bytes]:
        """下载图片数据"""
        if not self._session:
            raise NetworkError("未设置网络会话")
            
        try:
            response = self._session.get(url, timeout=10)
            response.raise_for_status()
            
            # 检查内容类型
            content_type = response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                app_logger.info(f" 非图片类型: {content_type}")
                return None
            
            return response.content
            
        except Exception as e:
            app_logger.error(f" 下载图片失败 {url}: {e}")
            return None
    
    def _compress_image(self, image_data: bytes) -> bytes:
        """压缩图片以减少内存使用"""
        try:
            # 打开图片
            image = Image.open(io.BytesIO(image_data))
            
            # 检查图片尺寸
            width, height = image.size
            
            # 如果图片过大，进行压缩
            if max(width, height) > self.max_image_size:
                # 计算新尺寸，保持宽高比
                if width > height:
                    new_width = self.max_image_size
                    new_height = int(height * self.max_image_size / width)
                else:
                    new_height = self.max_image_size
                    new_width = int(width * self.max_image_size / height)
                
                # 调整图片大小
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                app_logger.info(f" 图片已压缩: {width}x{height} → {new_width}x{new_height}")
            
            # 转换为JPEG格式以减少文件大小
            if image.mode in ('RGBA', 'LA', 'P'):
                # 透明图片转换为RGB
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background
            
            # 保存为JPEG
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=85, optimize=True)
            return output.getvalue()
            
        except Exception as e:
            app_logger.error(f" 压缩图片失败: {e}")
            return image_data  # 返回原始数据
    
    def _to_base64(self, image_data: bytes) -> str:
        """转换为Base64编码"""
        encoded = base64.b64encode(image_data).decode('utf-8')
        return f"data:image/jpeg;base64,{encoded}"
    
    def _cache_image(self, url: str, base64_data: str):
        """缓存图片数据"""
        with self._cache_lock:
            # 如果缓存已满，删除最旧的条目
            if len(self._cache) >= self.max_cache_size:
                # 删除第一个条目（假设是最旧的）
                first_key = next(iter(self._cache))
                del self._cache[first_key]
            
            self._cache[url] = base64_data
    
    def clear_cache(self):
        """清空图片缓存"""
        with self._cache_lock:
            self._cache.clear()
        app_logger.info("图片缓存已清空")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._cache_lock:
            return {
                'cached_images': len(self._cache),
                'max_cache_size': self.max_cache_size,
                'cache_usage': f"{len(self._cache)}/{self.max_cache_size}"
            }
    
    def batch_process_images(self, urls: List[str], compress: bool = True) -> Dict[str, Optional[str]]:
        """批量处理图片（并发）
        
        Args:
            urls: 图片URL列表
            compress: 是否压缩图片
            
        Returns:
            URL到Base64数据的映射
        """
        results: Dict[str, Optional[str]] = {}
        unique_urls = [u for u in dict.fromkeys([u for u in urls if u])]
        if not unique_urls:
            return results
        
        # 控制并发数量，避免占满带宽与CPU
        max_workers = min(6, max(1, len(unique_urls)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(self.process_image_url, url, compress): url for url in unique_urls}
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    results[url] = future.result()
                except Exception as e:
                    app_logger.error(f"批量处理图片失败: {e}")
                    results[url] = None
        return results

# 全局图片处理器实例
_image_processor = ImageProcessor()

def get_image_processor() -> ImageProcessor:
    """获取全局图片处理器实例"""
    return _image_processor

def process_image_url(url: str, session: requests.Session = None, compress: bool = True) -> Optional[str]:
    """便捷函数：处理单个图片URL
    
    Args:
        url: 图片URL
        session: 网络会话
        compress: 是否压缩图片
        
    Returns:
        Base64编码的图片数据
    """
    processor = get_image_processor()
    
    if session:
        processor.set_session(session)
    
    return processor.process_image_url(url, compress)

def batch_process_images(urls: List[str], session: requests.Session = None, compress: bool = True) -> Dict[str, Optional[str]]:
    """便捷函数：批量处理图片
    
    Args:
        urls: 图片URL列表
        session: 网络会话
        compress: 是否压缩图片
        
    Returns:
        URL到Base64数据的映射
    """
    processor = get_image_processor()
    
    if session:
        processor.set_session(session)
    
    return processor.batch_process_images(urls, compress)


