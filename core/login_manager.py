#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
登录管理器 - 核心业务逻辑
集成原项目的登录功能
"""

# =============================================================================
# 标准库导入
# =============================================================================
import os
import json
import requests
import base64
import time
import re
import uuid

# =============================================================================
# 第三方库导入
# =============================================================================
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from PIL import Image
from io import BytesIO

# =============================================================================
# 项目内部导入
# =============================================================================
from .enterprise_logger import app_logger

class LoginManager:
    """登录管理器类"""
    
    def __init__(self):
        """初始化登录管理器"""
        self.session = requests.Session()
        # 读取网络配置
        try:
            from .config_manager import get_app_config
            net_cfg = get_app_config().network
            _timeout = int(getattr(net_cfg, 'timeout', 10) or 10)
            _retries = int(getattr(net_cfg, 'max_retries', 3) or 3)
            _backoff = float(getattr(net_cfg, 'retry_delay', 0.5) or 0.5)
            _verify = bool(getattr(net_cfg, 'verify_ssl', True))
            _pool = int(getattr(net_cfg, 'max_connections', 10) or 10)
        except Exception:
            _timeout, _retries, _backoff, _verify, _pool = 10, 3, 0.5, True, 10

        # 配置SSL与重试
        self.session.verify = _verify
        retry_strategy = Retry(
            total=_retries,
            connect=_retries,
            read=_retries,
            status=_retries,
            backoff_factor=_backoff,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=_pool, pool_maxsize=_pool)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        if not _verify:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # 超星学习通前端 JavaScript 中的公开密钥，非私密信息。
        # 该密钥可从 passport2.chaoxing.com 登录页面 JS 源码中获取，
        # 用于客户端对密码等字段进行 AES-CBC 加密后传输。
        self.transfer_key = "u2oh6Vu^HWe4_AES"
        from .common import AppConstants
        self.headers = AppConstants.DEFAULT_HEADERS.copy()
        self.headers['Referer'] = 'https://passport2.chaoxing.com/login'
        # 设定默认超时
        self._default_timeout = _timeout
        # 将默认headers应用到会话
        self.session.headers.update(self.headers)
        self.base_url = 'https://passport2.chaoxing.com'
        # 二维码登录参数
        self.uuid = None
        self.enc = None
        self.user_info = {}
        
        # 尝试加载保存的登录状态
        self.load_cookies()
        
    def encrypt_aes(self, text):
        """AES-CBC加密，密钥为超星前端公开密钥（非私密，来自平台前端JS）"""
        text_bytes = text.encode('utf-8')
        key_bytes = self.transfer_key.encode('utf-8')
    
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv=key_bytes)
        padded_data = pad(text_bytes, AES.block_size)
        encrypted = cipher.encrypt(padded_data)
        
        return base64.b64encode(encrypted).decode('utf-8')
        
    def login_with_password(self, username, password):
        """使用账号密码登录 - 按照原始login.py的方式"""
        try:
            app_logger.info("正在初始化会话...")
            # 获取验证串
            validate = self.get_validate_string()
            app_logger.info(f"获取到验证串: {validate[:10]}***")
            
            # 加密手机号和密码（按照原始实现，手机号也需要加密）
            encrypted_phone = self.encrypt_aes(username)
            encrypted_password = self.encrypt_aes(password)
            
            # 登录请求 - 使用原始login.py中的URL和参数
            login_url = "https://passport2.chaoxing.com/fanyalogin"
            data = {
                'fid': '',
                'uname': encrypted_phone,
                'password': encrypted_password,
                'refer': 'https://i.chaoxing.com',
                't': 'true',
                'forbidotherlogin': '',
                'validate': validate,
                'doubleFactorLogin': '',
                'independentId': '',
                'independentNameId': ''
            }
            
            headers = self.headers.copy()
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            
            response = self.session.post(login_url, data=data, headers=headers, timeout=self._default_timeout)
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    if result.get('status'):
                        app_logger.success("登录成功!")
                        app_logger.info(f"重定向到: {result.get('url')}")
                        self.save_cookies()
                        self.get_user_info()
                        return True
                    else:
                        error_msg = result.get('msg2', '登录失败，请检查用户名和密码')
                        raise Exception(error_msg)
                except Exception as e:
                    app_logger.error(f"解析响应失败: {e}")
                    app_logger.info(f"响应状态: {response.status_code}, 长度: {len(response.text)}")
                    raise Exception("登录失败，请检查用户名和密码")
            else:
                raise Exception(f"请求失败，状态码: {response.status_code}")
                    
        except Exception as e:
            app_logger.error(f"登录失败: {e}")
            return False
            
    def get_qrcode_params(self):
        """获取二维码登录参数 - 从登录页面提取uuid和enc"""
        try:
            app_logger.info("正在获取登录页面...")
            url = f"{self.base_url}/login?fid=&newversion=true"
            response = self.session.get(url, headers=self.headers, timeout=self._default_timeout)
            
            if response.status_code == 200:
                # 使用BeautifulSoup解析HTML
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 尝试找到UUID和ENC输入字段
                uuid_input = soup.find('input', {'id': 'uuid'})
                enc_input = soup.find('input', {'id': 'enc'})
                
                if uuid_input and enc_input:
                    self.uuid = uuid_input.get('value')
                    self.enc = enc_input.get('value')
                    app_logger.success(f"成功获取参数 - UUID: {self.uuid[:8]}***, ENC: {self.enc[:8]}***")
                    return True
                else:
                    # 如果找不到，可能是页面结构变化，尝试直接生成随机值
                    app_logger.info("无法在页面中找到UUID和ENC参数，尝试生成随机值...")
                    import secrets
                    self.uuid = secrets.token_hex(16)
                    self.enc = secrets.token_hex(16)
                    app_logger.info(f"生成随机参数 - UUID: {self.uuid[:8]}***, ENC: {self.enc[:8]}***")
                    return True
            else:
                app_logger.error(f"获取登录页面失败，状态码: {response.status_code}")
            
        except Exception as e:
            app_logger.error(f"获取登录参数失败: {e}")
        
        return False

    def get_qr_code(self):
        """获取二维码 - 按照原始login.py的方式"""
        try:
            # 每次都重新获取二维码参数，确保生成新的二维码
            app_logger.info("重新获取二维码参数...")
            if not self.get_qrcode_params():
                raise Exception("获取二维码参数失败")
            
            app_logger.info("正在获取二维码...")
            # 使用原始login.py中的API端点
            url = f"{self.base_url}/createqr?uuid={self.uuid}&enc={self.enc}"
            response = self.session.get(url, headers=self.headers, timeout=self._default_timeout)
            app_logger.info(f"二维码请求响应状态: {response.status_code}")
            
            if response.status_code == 200:
                # 检查响应内容类型
                content_type = response.headers.get('content-type', '')
                app_logger.info(f"响应内容类型: {content_type}")
                
                # 检查响应内容长度
                content_length = len(response.content)
                app_logger.info(f"响应内容长度: {content_length} bytes")
                
                # 如果返回HTML而不是图片，说明参数可能有问题
                if 'text/html' in content_type or content_length < 1000:
                    app_logger.info(f"响应内容（前200字符）: {response.text[:200]}")
                    raise Exception("服务器返回HTML而不是二维码图片，可能参数无效")
                
                # 保存二维码图片到应用临时目录
                from .common import PathManager
                temp_dir = str(PathManager.get_temp_dir())
                qr_path = os.path.join(temp_dir, f"chaoxing_qrcode_{self.uuid}.png")
                
                with open(qr_path, 'wb') as f:
                    f.write(response.content)
                
                app_logger.info(f"二维码已保存到: {qr_path}")
                app_logger.info(f"文件大小: {os.path.getsize(qr_path)} bytes")
                
                # 验证文件是否正确保存
                if os.path.exists(qr_path) and os.path.getsize(qr_path) > 0:
                    return qr_path
                else:
                    raise Exception("二维码文件保存失败")
            else:
                raise Exception(f"获取二维码失败: HTTP {response.status_code}")
                
        except Exception as e:
            app_logger.error(f"获取二维码失败: {e}")
            return None
            
    def wait_for_qr_login(self, stop_flag=None):
        """等待二维码扫描登录 - 按照原始login.py的方式"""
        try:
            if not hasattr(self, 'uuid') or not hasattr(self, 'enc') or not self.uuid or not self.enc:
                raise Exception("缺少必要的登录参数")
            
            # 使用原始login.py中的状态检查端点
            check_url = f"{self.base_url}/getauthstatus"
            max_attempts = 50
            interval = 3
            
            app_logger.info(f"开始轮询登录状态，最多 {max_attempts} 次，间隔 {interval} 秒")
            app_logger.info("请使用超星学习通APP扫描二维码...")
            
            for attempt in range(max_attempts):
                # 检查停止标志
                if stop_flag and stop_flag():
                    app_logger.info("收到停止请求，退出二维码登录轮询")
                    return False
                
                # 使用POST方式发送参数
                data = {
                    "uuid": self.uuid,
                    "enc": self.enc
                }
                
                try:
                    response = self.session.post(check_url, data=data, headers=self.headers, timeout=5)
                    app_logger.debug(f"第 {attempt+1} 次检查状态: {response.status_code}")
                    
                    if response.status_code == 200:
                        try:
                            result = response.json()
                            app_logger.debug(f"检查结果: status={result.get('status')}, type={result.get('type')}")
                            
                            # 根据原始login.py的逻辑判断状态
                            if result.get('status'):
                                app_logger.success("登录成功!")
                                if result.get('url'):
                                    app_logger.info(f"重定向到: {result.get('url')}")
                                self.save_cookies()
                                self.get_user_info()
                                return True
                            elif result.get('type') == 4:
                                app_logger.info(f"手机已扫描，用户: {result.get('nickname')}，等待确认...")
                            elif result.get('type') == 6:
                                app_logger.info("客户端取消登录")
                                return False
                            elif result.get('mes') == "参数为空":
                                app_logger.info("服务器返回参数为空，可能是UUID和ENC无效")
                                return False
                                
                        except json.JSONDecodeError:
                            app_logger.debug(f"状态检查返回非JSON: {response.text[:100]}")
                        except Exception as e:
                            app_logger.error(f"解析状态响应失败: {e}")
                            
                except requests.exceptions.RequestException as e:
                    app_logger.error(f"网络请求失败: {e}")
                    # 网络错误时继续重试
                        
                # 分割sleep，以便更快响应停止请求
                for i in range(interval):
                    if stop_flag and stop_flag():
                        app_logger.info("收到停止请求，退出二维码登录轮询")
                        return False
                    time.sleep(1)
                
            app_logger.info("二维码已过期")
            return False
            
        except Exception as e:
            app_logger.error(f"二维码登录失败: {e}")
            return False
    
    def handle_captcha(self):
        """处理图形验证码 - 企业级GUI界面"""
        try:
            # 优先使用外部注入的处理函数（用于多线程GUI环境）
            if hasattr(self, 'captcha_handler') and self.captcha_handler:
                return self.captcha_handler(self.session, self.headers)

            # 检查是否在GUI环境中
            from PySide6.QtWidgets import QApplication, QDialog
            
            app = QApplication.instance()
            if app is not None:
                # GUI模式 - 使用现代化验证码对话框
                from ui.captcha_dialog import CaptchaDialog
                
                dialog = CaptchaDialog(self.session, self.headers)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    return dialog.get_captcha_code()
                else:
                    return ""  # 用户取消
            else:
                # 命令行模式 - 保持兼容性
                return self._handle_captcha_cli()
                
        except ImportError:
            # 没有GUI环境，使用命令行模式
            return self._handle_captcha_cli()
        except Exception as e:
            app_logger.error(f"处理验证码失败: {e}")
            return ""
    
    def _handle_captcha_cli(self):
        """命令行模式的验证码处理"""
        try:
            captcha_url = f"https://passport2.chaoxing.com/num/code?{int(time.time() * 1000)}"
            response = self.session.get(captcha_url, headers=self.headers, timeout=self._default_timeout)
            
            if response.status_code == 200:
                import uuid
                from .common import PathManager
                captcha_filename = str(PathManager.get_temp_dir() / f"captcha_{uuid.uuid4().hex}.png")
                with open(captcha_filename, "wb") as f:
                    f.write(response.content)
                
                try:
                    try:
                        from PIL import Image
                        Image.open(captcha_filename).show()
                    except ImportError:
                        app_logger.info(f"验证码已保存到 {captcha_filename}，请手动打开查看")
                    
                    captcha_code = input("请输入图片验证码: ")
                    return captcha_code
                finally:
                    try:
                        os.remove(captcha_filename)
                    except Exception:
                        pass
        except Exception as e:
            app_logger.error(f"获取验证码失败: {e}")
        
        return ""
    
    def send_verification_code(self, phone, country_code="86"):
        """发送验证码"""
        try:
            # 初始化会话
            app_logger.info("正在初始化会话...")
            validate = self.get_validate_string()
            app_logger.info(f"获取到验证串: {validate[:10]}..." if validate else "未获取到验证串")
            
            # 处理图形验证码
            captcha_code = self.handle_captcha()
            
            # 验证码发送请求
            verify_url = "https://passport2.chaoxing.com/num/phonecode"
            params = {
                'phone': phone,
                'code': captcha_code,
                'type': "1",
                'needcode': "true" if captcha_code else "false",
                'countrycode': country_code,
                'validate': validate,
                'fid': "0"
            }
            
            headers = self.headers.copy()
            headers['X-Requested-With'] = 'XMLHttpRequest'
            
            response = self.session.get(verify_url, params=params, headers=headers, timeout=self._default_timeout)
            app_logger.debug(f"验证码请求响应: {response.text}")
            
            try:
                result = response.json()
                if result.get("result", False):
                    app_logger.success("验证码发送成功，请查收手机短信")
                    return True
                else:
                    app_logger.error(f"验证码发送失败: {result.get('msg', '未知错误')}")
                    
                    # 如果失败原因是需要图形验证码，则尝试重新发送
                    if "验证码" in result.get('msg', '') and not captcha_code:
                        app_logger.info("需要图形验证码，正在重试...")
                        return self.send_verification_code(phone, country_code)
            except Exception as e:
                app_logger.error(f"请求失败: {e}")
            
            return False
                
        except Exception as e:
            app_logger.error(f"发送验证码失败: {e}")
            return False
    
    def login_with_verification_code(self, phone, verification_code, country_code="86"):
        """使用手机号和验证码登录"""
        # 加密验证码
        encrypted_code = self.encrypt_aes(verification_code)
    
        # 登录请求
        login_url = "https://passport2.chaoxing.com/fanyaloginbycode"
        data = {
            'fid': '',
            'uname': phone,  # 手机号不加密
            'verCode': requests.utils.quote(encrypted_code),
            'refer': 'https://i.chaoxing.com',
            'doubleFactorLogin': '',
            'independentNameId': '',
            'validate': self.get_validate_string()
        }
        
        headers = self.headers.copy()
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        headers['Referer'] = 'https://passport2.chaoxing.com/login?loginType=2&newversion=true'
        
        response = self.session.post(login_url, data=data, headers=headers, timeout=self._default_timeout)
        
        if response.status_code == 200:
            try:
                result = response.json()
                if result.get('status'):
                    app_logger.success("登录成功!")
                    app_logger.info(f"重定向到: {result.get('url')}")
                    self.save_cookies()
                    return result
                else:
                    app_logger.error(f"登录失败: {result.get('msg2', '未知错误')}")
            except Exception as e:
                app_logger.error(f"解析响应失败: {e}")
                app_logger.debug(f"原始响应: {response.text}")
        else:
            app_logger.error(f"请求失败，状态码: {response.status_code}")
    
        return None
    
    def get_validate_string(self):
        """获取验证串"""
        try:
            login_url = "https://passport2.chaoxing.com/login?loginType=2&newversion=true"
            response = self.session.get(login_url, headers=self.headers, timeout=self._default_timeout)
            
            if response.status_code == 200:
                validate_pattern = r'id="validate"\s+value="([^"]+)"'
                match = re.search(validate_pattern, response.text)
                if match:
                    return match.group(1)
            
            # 尝试从API获取token
            token_url = "https://passport2.chaoxing.com/api/token"
            response = self.session.get(token_url, headers=self.headers, timeout=self._default_timeout)
            if response.status_code == 200:
                data = response.json()
                if "token" in data:
                    return data["token"]
        except Exception:
            pass
        
        return ""

    def check_login_status(self):
        """检查当前登录状态"""
        try:
            app_logger.debug(f" 检查登录状态 - 已有用户信息: {bool(self.user_info)}")
            
            # 检查是否有用户信息（说明已登录）
            if self.user_info and self.user_info.get('name'):
                app_logger.debug(f" 通过用户信息验证登录状态: {self.user_info.get('name')}")
                return True
                
            # 检查session是否有有效cookies
            app_logger.debug(f"检查cookies数量: {len(self.session.cookies)}")
            if self.session.cookies:
                # 尝试访问用户页面验证登录状态
                test_url = "https://i.chaoxing.com/base"
                app_logger.info(f" 测试访问: {test_url}")
                response = self.session.get(test_url, headers=self.headers, allow_redirects=False, timeout=self._default_timeout)
                app_logger.info(f" 响应状态码: {response.status_code}")
                
                # 如果没有重定向到登录页，说明已登录
                if response.status_code == 200:
                    app_logger.debug(" 通过网络请求验证登录状态")
                    return True
                    
            app_logger.info(" 未检测到有效登录状态")
            return False
            
        except Exception as e:
            app_logger.error(f"检查登录状态失败: {e}")
            return False
            
    def get_user_info(self):
        """获取用户信息 - 参考原始login.py的方式"""
        try:
            # 访问个人主页，按照原始方式检查登录状态并获取用户名
            url = "https://i.chaoxing.com/base"
            response = self.session.get(url, headers=self.headers, allow_redirects=False, timeout=self._default_timeout)
            
            # 如果返回200并且页面包含用户信息，则已登录
            if response.status_code == 200:
                try:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    username_elem = soup.select_one('.user-block .user-name')
                    
                    if username_elem:
                        username = username_elem.text.strip()
                        self.user_info['name'] = username
                        app_logger.success(f" 从主页获取用户信息成功: {username}")
                        return self.user_info
                    else:
                        # 尝试其他可能的用户名元素
                        alt_selectors = [
                            '.profile .username',
                            '.header-user .username', 
                            '.user-info .name',
                            '#username',
                            '.loginname'
                        ]
                        for selector in alt_selectors:
                            elem = soup.select_one(selector)
                            if elem:
                                username = elem.text.strip()
                                self.user_info['name'] = username
                                app_logger.info(f" 从备用选择器获取用户信息: {username}")
                                return self.user_info
                        
                        # 如果找不到用户名元素，设置默认值但标记为已登录
                        self.user_info['name'] = '学习通用户'
                        app_logger.info(" 未找到用户名元素，使用默认名称")
                        return self.user_info
                        
                except Exception as e:
                    app_logger.error(f"解析用户信息失败: {e}")
            
            # 如果无法获取具体信息，但有cookies，设置默认用户信息
            if self.session.cookies:
                self.user_info['name'] = '学习通用户'
                app_logger.info(" 使用默认用户信息，因为有有效session")
                return self.user_info
                
        except Exception as e:
            app_logger.error(f"获取用户信息失败: {e}")
        
        # 最后的兜底方案
        self.user_info['name'] = '学习通用户'
        self.user_info['phone'] = ''
        app_logger.info(" 使用兜底用户信息")
        return self.user_info
        
    def save_cookies(self):
        """保存cookies到文件"""
        try:
            from .common import PathManager
            cookies_dict = requests.utils.dict_from_cookiejar(self.session.cookies)
            session_path = PathManager.get_file_path("session.txt", "data")
            with open(session_path, 'w', encoding='utf-8') as f:
                json.dump(cookies_dict, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            app_logger.error(f"保存cookies失败: {e}")
            return False
            
    def load_cookies(self):
        """从文件加载cookies"""
        try:
            from .common import PathManager
            session_path = PathManager.get_file_path("session.txt", "data")
            if session_path.exists():
                with open(session_path, 'r', encoding='utf-8') as f:
                    cookies_dict = json.load(f)
                if cookies_dict:
                    self.session.cookies.update(cookies_dict)
                    app_logger.info(f"已加载保存的登录状态，cookies数量: {len(cookies_dict)}")
                    return True
        except Exception as e:
            app_logger.warning(f"加载cookies失败: {e}")
        return False
            
    def logout(self):
        """退出登录"""
        try:
            from .common import PathManager
            # 清理cookies文件
            session_path = PathManager.get_file_path("session.txt", "data")
            if session_path.exists():
                session_path.unlink()
                
            # 清理session cookies
            self.session.cookies.clear()
            
            # 清理用户信息
            self.user_info = {}
            
            return True
        except Exception as e:
            app_logger.error(f"退出登录失败: {e}")
            return False
            
    def save_login_info(self, info):
        """保存登录信息"""
        try:
            from .common import PathManager
            login_path = PathManager.get_file_path("login_info.json", "data")
            with open(login_path, 'w', encoding='utf-8') as f:
                json.dump(info, f, ensure_ascii=False, indent=2)
        except Exception as e:
            app_logger.error(f"保存登录信息失败: {e}")
            
    def load_login_info(self):
        """加载登录信息"""
        try:
            from .common import PathManager
            login_path = PathManager.get_file_path("login_info.json", "data")
            if login_path.exists():
                with open(login_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            app_logger.error(f"加载登录信息失败: {e}")
        return {}
        
    def get_session(self):
        """获取当前session"""
        return self.session
