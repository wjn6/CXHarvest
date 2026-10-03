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
import threading
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
from Crypto.Util.Padding import pad, unpad

# =============================================================================
# 项目内部导入
# =============================================================================
from .enterprise_logger import app_logger

class TwoFactorRequired(Exception):
    """登录触发双因子（安全验证）异常，携带 2FA 页面地址"""

    def __init__(self, url: str):
        super().__init__("需要双因子安全验证")
        self.url = url

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
    
    # -----------------------------------------------------------------
    # 本地存储加密（与超星传输加密无关，搭配随机 IV 使用）
    # -----------------------------------------------------------------
    @staticmethod
    def _derive_local_key() -> bytes:
        """派生本地存储专用密钥（基于机器特征，不存在文件中）"""
        import hashlib, getpass
        # 使用当前系统用户名 + 固定盐值派生密钥，不同机器不同
        seed = f"CXHarvest:{getpass.getuser()}:local_enc_salt_v1"
        return hashlib.sha256(seed.encode('utf-8')).digest()[:16]

    @classmethod
    def _encrypt_local(cls, plaintext: str) -> str:
        """使用随机 IV 的 AES-CBC 加密，返回 base64(iv + ciphertext)"""
        if not plaintext:
            return ''
        key = cls._derive_local_key()
        iv = os.urandom(16)
        cipher = AES.new(key, AES.MODE_CBC, iv=iv)
        ct = cipher.encrypt(pad(plaintext.encode('utf-8'), AES.block_size))
        return base64.b64encode(iv + ct).decode('utf-8')

    @classmethod
    def _decrypt_local(cls, encoded: str) -> str:
        """解密 _encrypt_local 产出的密文"""
        if not encoded:
            return ''
        try:
            raw = base64.b64decode(encoded)
            iv, ct = raw[:16], raw[16:]
            key = cls._derive_local_key()
            cipher = AES.new(key, AES.MODE_CBC, iv=iv)
            return unpad(cipher.decrypt(ct), AES.block_size).decode('utf-8')
        except Exception:
            # 解密失败（可能是旧的明文格式），原样返回
            return encoded
        
    def login_with_password(self, username, password):
        """使用账号密码登录 - 按照原始login.py的方式"""
        try:
            app_logger.info("正在初始化会话...")
            # 主动登录需干净会话：清掉自动加载的旧 cookies，避免新旧混杂导致校验失败
            self.session.cookies.clear()
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
                    if result.get('containTwoFactorLogin'):
                        # 触发双因子安全验证，抛出专用异常交给 UI 层弹窗处理
                        two_url = result.get('twoFactorLoginUrl', '')
                        app_logger.info(f"触发双因子安全验证: {two_url}")
                        raise TwoFactorRequired(two_url)
                    if result.get('status'):
                        app_logger.success("登录成功!")
                        app_logger.info(f"重定向到: {result.get('url')}")
                        self.save_cookies()
                        self.get_user_info()
                        return True
                    else:
                        error_msg = result.get('msg2', '登录失败，请检查用户名和密码')
                        raise Exception(error_msg)
                except TwoFactorRequired:
                    raise
                except Exception as e:
                    app_logger.error(f"解析响应失败: {e}")
                    app_logger.info(f"响应状态: {response.status_code}, 长度: {len(response.text)}")
                    raise Exception("登录失败，请检查用户名和密码")
            else:
                raise Exception(f"请求失败，状态码: {response.status_code}")

        except TwoFactorRequired:
            raise
        except Exception as e:
            app_logger.error(f"登录失败: {e}")
            return False
            
    @staticmethod
    def parse_two_factor_params(two_url: str) -> dict:
        """解析 2FA 地址中的参数（uid/enc/enc2/time/type/fid/loginTimeout）"""
        return dict(re.findall(r'([^?&=]+)=([^&]*)', two_url or ''))

    def get_two_factor_phone(self, two_url: str) -> str:
        """从 2FA 页面提取绑定手机号（隐藏域 #phone 或 #msg）"""
        try:
            response = self.session.get(f"{self.base_url}{two_url}",
                                        headers=self.headers, timeout=self._default_timeout)
            m = (re.search(r'id="phone"[^>]*value="([^"]*)"', response.text)
                 or re.search(r'value="([^"]*)"[^>]*id="phone"', response.text)
                 or re.search(r'id="msg"[^>]*value="([^"]*)"', response.text)
                 or re.search(r'value="([^"]*)"[^>]*id="msg"', response.text))
            return m.group(1) if m else ''
        except Exception as e:
            app_logger.warning(f"提取2FA手机号失败: {e}")
            return ''

    def two_factor_send_sms(self, phone: str, validate: str) -> dict:
        """2FA：发送短信验证码（需行为验证码 validate）

        参数与浏览器实际请求保持一致（needcode=false、countrycode 为空）。
        返回 {'result': bool, 'msg': str}
        """
        url = (f"{self.base_url}/num/phonecode?phone={phone}&code=&type=1"
               f"&needcode=false&countrycode=&validate={validate or ''}")
        headers = self.headers.copy()
        headers['Referer'] = f"{self.base_url}/toTwoFactorLogin"
        response = self.session.get(url, headers=headers, timeout=self._default_timeout)
        data = response.json()
        return {'result': bool(data.get('result')), 'msg': data.get('msg', '')}

    def _complete_sso_redirect(self):
        """2FA 验证成功后，模拟官方页面 window.location = refer 的跳转，完成 SSO 补齐业务域 cookies

        官方 2FA 页面验证成功后跳转到 refer（默认为 http://i.mooc.chaoxing.com），
        该跳转会经过 passport SSO，在 session 中写入 _uid/UID/lv 等业务域 cookies，
        缺少这些 cookies 会导致后续课程/作业接口校验失败。
        """
        try:
            url = "http://i.mooc.chaoxing.com"
            resp = self.session.get(url, headers=self.headers, allow_redirects=True,
                                    timeout=self._default_timeout)
            # 再访问一次业务主页，确保 i.chaoxing.com 域 cookies 齐全
            self.session.get("https://i.chaoxing.com/base", headers=self.headers,
                             allow_redirects=True, timeout=self._default_timeout)
            names = sorted({c.name for c in self.session.cookies})
            app_logger.info(f"2FA 登录后 SSO 跳转完成: {resp.status_code} -> {resp.url}; cookies: {names}")
        except Exception as e:
            app_logger.warning(f"2FA 登录后 SSO 跳转失败（不影响已登录状态）: {e}")

    def two_factor_check(self, two_url: str, phone: str, vcode: str) -> dict:
        """2FA：提交短信验证码完成安全验证，成功后当前 session 即登录态

        返回 {'status': bool, 'mes': str}
        """
        p = self.parse_two_factor_params(two_url)
        url = (f"{self.base_url}/v11/checkmessage?enc2={p.get('enc2', '')}"
               f"&time={p.get('time', '')}&type={p.get('type', '3')}")
        # 与浏览器实际提交保持一致：phone/vcode/fid/loginTimeout
        data = {
            'phone': phone,
            'vcode': vcode,
            'fid': p.get('fid', '-1'),
            'loginTimeout': p.get('loginTimeout', '1'),
        }
        headers = self.headers.copy()
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        headers['Referer'] = f"{self.base_url}{two_url}"
        response = self.session.post(url, data=data, headers=headers, timeout=self._default_timeout)
        result = response.json()
        app_logger.info(f"2FA checkmessage 响应: status={result.get('status')} "
                        f"type={result.get('type')} mes={result.get('mes')}")
        if result.get('status'):
            # type=='1' 表示服务端强制要求重置弱密码，由 UI 层引导用户改密后再完成登录
            if str(result.get('type')) == '1':
                return {'status': True, 'mes': result.get('mes', ''),
                        'weak_pwd': True,
                        'userid': result.get('userid', ''),
                        'token': result.get('token', '')}
            # 无需改密：跟随官方 refer 跳转补齐 SSO cookies 后保存
            self._complete_sso_redirect()
            self.save_cookies()
        return {'status': bool(result.get('status')), 'mes': result.get('mes', ''),
                'weak_pwd': False}

    def two_factor_reset_password(self, userid: str, token: str,
                                  new_password: str, validate: str) -> dict:
        """2FA 弱密码重置：POST /v11/updateweakpwd（新密码需 AES 加密）

        成功后跟随 refer 跳转补齐 SSO cookies 并保存。
        返回 {'status': bool, 'mes': str}
        """
        # 先加载改密页建立上下文（与浏览器流程一致）
        page_url = (f"{self.base_url}/v11/updateweakpwd?uid={userid}&token={token}"
                    f"&passwordTimeout=1&refer=http%3A%2F%2Fi.mooc.chaoxing.com")
        try:
            self.session.get(page_url, headers=self.headers, timeout=self._default_timeout)
        except Exception:
            pass

        enc_pwd = self.encrypt_aes(new_password)
        data = {
            'pwdValidatorType': '',
            'token': token,
            'uid': userid,
            'oldpwd': '',
            '_blank': '',
            'refer': 'http://i.mooc.chaoxing.com',
            'validate': validate or '',
            'password': enc_pwd,
            'password2': enc_pwd,
        }
        headers = self.headers.copy()
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        headers['Referer'] = page_url
        headers['X-Requested-With'] = 'XMLHttpRequest'
        response = self.session.post(f"{self.base_url}/v11/updateweakpwd", data=data,
                                     headers=headers, timeout=self._default_timeout)
        try:
            result = response.json()
        except Exception:
            result = {}
        app_logger.info(f"2FA 弱密码重置响应: status={result.get('status')} mes={result.get('mes')}")
        if result.get('status'):
            self._complete_sso_redirect()
            self.save_cookies()
        return {'status': bool(result.get('status')), 'mes': result.get('mes', '')}

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

            if threading.current_thread() is not threading.main_thread():
                # 未注入回调时不在工作线程建对话框：Qt 要求 GUI 只在主线程操作
                app_logger.error("当前不在主线程且未注入 captcha_handler，跳过图形验证码")
                return ""

            # 检查是否在GUI环境中
            from PySide6.QtWidgets import QApplication, QDialog
            
            app = QApplication.instance()
            if app is not None:
                # GUI模式 - 使用现代化验证码对话框（MessageBoxBase 需要父窗口来定位遮罩）
                parent = app.activeWindow()
                if parent is None:
                    visible = [w for w in app.topLevelWidgets() if w.isVisible()]
                    parent = visible[0] if visible else None
                if parent is None:
                    app_logger.error("无可用父窗口，无法显示图形验证码")
                    return ""
                from ui.captcha_dialog import CaptchaDialog
                
                dialog = CaptchaDialog(self.session, self.headers, parent)
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
                    
                    # 如果失败原因是需要图形验证码，则尝试重新发送（最多1次）
                    if "验证码" in result.get('msg', '') and not captcha_code and not getattr(self, '_sms_retry', False):
                        self._sms_retry = True
                        app_logger.info("需要图形验证码，正在重试(1/1)...")
                        try:
                            return self.send_verification_code(phone, country_code)
                        finally:
                            self._sms_retry = False
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

    def is_session_valid(self):
        """轻量校验保存的登录状态是否有效（不依赖用户名解析）

        请求 i.chaoxing.com/base（禁止重定向）：
        - 200 且不含登录页特征 -> 已登录，返回 True
        - 302/登录页特征         -> 已过期，返回 False
        - 网络异常               -> 状态未知，返回 None（调用方应保留本地 session）
        """
        try:
            url = "https://i.chaoxing.com/base"
            response = self.session.get(url, headers=self.headers,
                                        allow_redirects=False, timeout=self._default_timeout)
            if response.status_code == 200:
                text = response.text
                if 'passport2.chaoxing.com/login' in text or '<title>用户登录</title>' in text:
                    app_logger.info("保存的登录状态已过期（base 返回登录页）")
                    return False
                return True
            if response.status_code in (301, 302, 303, 307, 308):
                app_logger.info("保存的登录状态已过期（base 重定向到登录页）")
                return False
            app_logger.warning(f"登录状态校验异常状态码: {response.status_code}")
            return None
        except Exception as e:
            app_logger.warning(f"登录状态校验网络异常: {e}")
            return None

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
            
            # 清理登录信息文件
            login_path = PathManager.get_file_path("login_info.json", "data")
            if login_path.exists():
                login_path.unlink()
                
            # 清理session cookies
            self.session.cookies.clear()
            
            # 清理用户信息
            self.user_info = {}
            
            return True
        except Exception as e:
            app_logger.error(f"退出登录失败: {e}")
            return False
            
    def save_login_info(self, info):
        """保存登录信息（密码字段加密后存储）"""
        try:
            from .common import PathManager
            # 加密敏感字段后再写入磁盘
            safe_info = dict(info)
            if 'password' in safe_info and safe_info['password']:
                safe_info['password'] = self._encrypt_local(safe_info['password'])
                safe_info['_encrypted'] = True  # 标记已加密
            login_path = PathManager.get_file_path("login_info.json", "data")
            with open(login_path, 'w', encoding='utf-8') as f:
                json.dump(safe_info, f, ensure_ascii=False, indent=2)
        except Exception as e:
            app_logger.error(f"保存登录信息失败: {e}")
            
    def load_login_info(self):
        """加载登录信息（自动解密密码字段）"""
        try:
            from .common import PathManager
            login_path = PathManager.get_file_path("login_info.json", "data")
            if login_path.exists():
                with open(login_path, 'r', encoding='utf-8') as f:
                    info = json.load(f)
                # 如果有加密标记，解密密码
                if info.get('_encrypted') and 'password' in info:
                    info['password'] = self._decrypt_local(info['password'])
                    del info['_encrypted']  # 返回给调用方时不需要此标记
                return info
        except Exception as e:
            app_logger.error(f"加载登录信息失败: {e}")
        return {}
        
    def get_session(self):
        """获取当前session"""
        return self.session
