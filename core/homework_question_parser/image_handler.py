#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片处理模块
包含：Base64转换、图片提取等功能
"""

import base64
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
from ..enterprise_logger import app_logger


class ImageHandler:
    """图片处理器"""
    
    def __init__(self, login_manager=None):
        self.login_manager = login_manager
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'
        }
    
    def get_image_as_base64(self, url):
        """将图片转换为Base64编码"""
        try:
            if not url or not url.strip():
                return None
            
            # 对于已经是base64的数据，直接返回
            if url.startswith('data:image'):
                return url
            
            # 处理相对路径，强制使用HTTPS
            if url.startswith('//'):
                safe_url = 'https:' + url
            elif url.startswith('/'):
                safe_url = 'https://mooc1.chaoxing.com' + url
            elif url.startswith('http://'):
                safe_url = url.replace('http://', 'https://')
            else:
                safe_url = url
            
            # 使用登录管理器的session获取图片
            if self.login_manager and hasattr(self.login_manager, 'session'):
                session = self.login_manager.session
                headers = {**self.headers, 'Referer': 'https://i.chaoxing.com/'}
                response = session.get(safe_url, headers=headers, timeout=10, verify=False)
                response.raise_for_status()
                
                # 获取图片内容类型
                content_type = response.headers.get('content-type', 'image/png')
                if not content_type.startswith('image/'):
                    content_type = 'image/png'
                
                # 转换为Base64
                image_base64 = base64.b64encode(response.content).decode('utf-8')
                data_url = f"data:{content_type};base64,{image_base64}"
                
                return data_url
            else:
                app_logger.info("无法获取登录session")
                return url
            
        except Exception as e:
            app_logger.error(f"转换图片到Base64失败 {url}: {e}")
            return url  # 如果转换失败，返回原始URL
    
    def _process_single_image(self, img_info):
        """处理单个图片（用于并行处理）- 保证不抛异常"""
        # 安全解包
        try:
            src, alt = img_info
        except (ValueError, TypeError):
            return None
        
        if not src:
            return None
            
        try:
            base64_data = self.get_image_as_base64(src)
            
            # 尝试获取图片尺寸
            width = height = 0
            try:
                if base64_data and base64_data.startswith('data:image'):
                    image_data = base64_data.split(',')[1]
                    image_bytes = base64.b64decode(image_data)
                    with Image.open(io.BytesIO(image_bytes)) as pil_img:
                        width, height = pil_img.size
            except Exception:
                pass
            
            return {
                'src': src,
                'alt': alt or '图片',
                'data': base64_data,
                'width': width,
                'height': height
            }
        except Exception:
            # 任何异常都返回降级结果，不抛出
            return {
                'src': src,
                'alt': alt or '图片',
                'data': src,
                'width': 0,
                'height': 0
            }

    def extract_images_from_element(self, element):
        """从指定元素中提取图片并转换为Base64（并行处理，保持顺序）"""
        images = []
        if not element:
            return images
        
        try:
            # 查找该元素内的所有图片
            img_elements = element.find_all('img')
            unique_urls = set()
            img_tasks = []
            
            for img in img_elements:
                src = img.get('src')
                if src and src not in unique_urls:
                    unique_urls.add(src)
                    img_tasks.append((src, img.get('alt', '图片')))
            
            # 并行处理图片（最多5个线程），使用map保持顺序
            if img_tasks:
                with ThreadPoolExecutor(max_workers=5) as executor:
                    # executor.map 保持提交顺序返回结果
                    results = list(executor.map(self._process_single_image, img_tasks))
                    images = [r for r in results if r]
            
        except Exception as e:
            app_logger.error(f"从元素提取图片失败: {e}")
        
        return images
    
    def batch_get_images_as_base64(self, urls):
        """批量并行获取图片Base64（用于加速）"""
        results = {}
        if not urls:
            return results
        
        def fetch_one(url):
            return url, self.get_image_as_base64(url)
        
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(fetch_one, url) for url in urls]
            for future in as_completed(futures):
                try:
                    url, data = future.result()
                    results[url] = data
                except Exception:
                    pass
        
        return results
