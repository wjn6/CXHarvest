#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片处理模块
包含：Base64转换、图片提取等功能
"""

import base64
import io
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Optional
from urllib.parse import urlparse
from PIL import Image
from ..enterprise_logger import app_logger
from ..common import AppConstants

ALLOWED_IMAGE_DOMAINS = {
    'chaoxing.com', 'ananas.chaoxing.com', 'p.ananas.chaoxing.com',
    's.ananas.chaoxing.com', 'mooc1.chaoxing.com', 'mooc2-ans.chaoxing.com',
    'photo.chaoxing.com', 'img.chaoxing.com',
}


class ImageHandler:
    """图片处理器"""
    
    def __init__(self, login_manager=None, max_cache_size: int = 100, max_image_size: int = 1024):
        self.login_manager = login_manager
        self.headers = {
            'User-Agent': AppConstants.DEFAULT_HEADERS['User-Agent']
        }
        self.max_cache_size = max_cache_size
        self.max_image_size = max_image_size
        self._cache: Dict[str, str] = {}
        self._cache_lock = threading.Lock()
        self._session = None

        if self.login_manager and hasattr(self.login_manager, 'session'):
            self._session = self.login_manager.session

    def set_session(self, session):
        self._session = session

    def clear_cache(self):
        with self._cache_lock:
            self._cache.clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        with self._cache_lock:
            return {
                'cached_images': len(self._cache),
                'max_cache_size': self.max_cache_size,
                'cache_usage': f"{len(self._cache)}/{self.max_cache_size}"
            }

    def _get_session(self):
        if self.login_manager and hasattr(self.login_manager, 'session'):
            return self.login_manager.session
        return self._session

    def _is_allowed_domain(self, url: str) -> bool:
        """检查 URL 域名是否在白名单中"""
        try:
            parsed = urlparse(url)
            host = parsed.hostname or ''
            return any(host == d or host.endswith('.' + d) for d in ALLOWED_IMAGE_DOMAINS)
        except Exception:
            return False

    def _normalize_url(self, url: str) -> str:
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('/'):
            return 'https://mooc1.chaoxing.com' + url
        if url.startswith('http://'):
            return url.replace('http://', 'https://')
        if url.startswith('https://'):
            return url

        if url.startswith('p.ananas.chaoxing.com') or url.startswith('s.ananas.chaoxing.com'):
            return 'https://' + url

        if url and not url.startswith(('javascript:', 'file:', 'data:')):
            return f"https://p.ananas.chaoxing.com/star3/240_130c/{url}"
        return ''

    def _download_image(self, url: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
        session = self._get_session()
        if not session:
            return None

        if not self._is_allowed_domain(url):
            app_logger.warning(f"图片域名不在白名单中，已跳过: {url[:80]}")
            return None

        headers = {**self.headers, 'Referer': 'https://i.chaoxing.com/'}

        for attempt in range(max_retries):
            try:
                response = session.get(url, headers=headers, timeout=15)
                response.raise_for_status()

                content_type = (response.headers.get('content-type', '') or '').split(';')[0].strip()
                if not content_type.startswith('image/'):
                    return None

                return {
                    'bytes': response.content,
                    'content_type': content_type
                }
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise

    def _compress_image(self, image_data: bytes) -> bytes:
        try:
            image = Image.open(io.BytesIO(image_data))
            width, height = image.size

            if max(width, height) > self.max_image_size:
                if width > height:
                    new_width = self.max_image_size
                    new_height = int(height * self.max_image_size / width)
                else:
                    new_height = self.max_image_size
                    new_width = int(width * self.max_image_size / height)
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            if image.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background

            output = io.BytesIO()
            image.save(output, format='JPEG', quality=85, optimize=True)
            return output.getvalue()
        except Exception:
            return image_data

    def _cache_image(self, key: str, value: str):
        with self._cache_lock:
            if len(self._cache) >= self.max_cache_size:
                first_key = next(iter(self._cache))
                del self._cache[first_key]
            self._cache[key] = value
    
    def get_image_as_base64(self, url, compress: bool = False):
        """将图片转换为Base64编码"""
        try:
            if not url or not url.strip():
                return None
            
            # 对于已经是base64的数据，直接返回
            if url.startswith('data:image'):
                return url

            cache_key = f"{1 if compress else 0}:{url}"
            with self._cache_lock:
                cached = self._cache.get(cache_key)
            if cached:
                return cached

            safe_url = self._normalize_url(url)

            download = self._download_image(safe_url)
            if not download:
                return None

            image_bytes = download.get('bytes')
            content_type = download.get('content_type') or 'image/png'
            if not image_bytes:
                return None

            if compress:
                image_bytes = self._compress_image(image_bytes)
                content_type = 'image/jpeg'

            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            data_url = f"data:{content_type};base64,{image_base64}"

            self._cache_image(cache_key, data_url)
            return data_url
            
        except Exception as e:
            app_logger.error(f"转换图片到Base64失败 {url}: {e}")
            return None
    
    def _process_single_image(self, img_info):
        """处理单个图片（用于并行处理）- 保证不抛异常"""
        # 安全解包
        try:
            src = img_info[0]
            alt = img_info[1] if len(img_info) > 1 else None
            compress = img_info[2] if len(img_info) > 2 else False
        except (ValueError, TypeError, IndexError):
            return None
        
        if not src:
            return None
            
        try:
            normalized_src = src
            if not src.startswith('data:image'):
                normalized_src = self._normalize_url(src)

            base64_data = self.get_image_as_base64(src, compress=compress)
            
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
                'src': normalized_src,
                'alt': alt or '图片',
                'data': base64_data,
                'width': width,
                'height': height
            }
        except Exception:
            # 任何异常都返回降级结果，不抛出
            return {
                'src': normalized_src if 'normalized_src' in locals() else src,
                'alt': alt or '图片',
                'data': None,
                'width': 0,
                'height': 0
            }

    def extract_images_from_element(self, element, compress: bool = False):
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
                src = img.get('src') or img.get('data-src')
                if src and src not in unique_urls:
                    unique_urls.add(src)
                    img_tasks.append((src, img.get('alt', '图片'), compress))
            
            # 并行处理图片（最多5个线程），使用map保持顺序
            if img_tasks:
                with ThreadPoolExecutor(max_workers=5) as executor:
                    # executor.map 保持提交顺序返回结果
                    results = list(executor.map(self._process_single_image, img_tasks))
                    images = [r for r in results if r]
            
        except Exception as e:
            app_logger.error(f"从元素提取图片失败: {e}")
        
        return images
    
    def batch_get_images_as_base64(self, urls, compress: bool = True):
        """批量并行获取图片Base64（用于加速）"""
        results = {}
        if not urls:
            return results

        unique_urls = [u for u in dict.fromkeys([u for u in urls if u])]
        if not unique_urls:
            return results

        def fetch_one(url):
            return url, self.get_image_as_base64(url, compress=compress)

        max_workers = min(6, max(1, len(unique_urls)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(fetch_one, url): url for url in unique_urls}
            for future in as_completed(future_to_url):
                orig_url = future_to_url[future]
                try:
                    url, data = future.result()
                    results[url] = data
                except Exception:
                    results[orig_url] = None
        
        for url in unique_urls:
            if url not in results:
                results[url] = None

        return results

    def process_image_url(self, url: str, compress: bool = True) -> Optional[str]:
        return self.get_image_as_base64(url, compress=compress)

    def batch_process_images(self, urls, compress: bool = True) -> Dict[str, Optional[str]]:
        """批量处理图片（委托给 batch_get_images_as_base64）"""
        return self.batch_get_images_as_base64(urls, compress=compress)
