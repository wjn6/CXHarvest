<div align="center">

# 🌾 超星收割机 (CXHarvest)

[![Python](https://img.shields.io/badge/Python-3.8+-3776ab.svg?logo=python&logoColor=white)](https://python.org)
[![PySide6](https://img.shields.io/badge/PySide6-6.0+-41cd52.svg?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)
[![License](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078d4.svg?logo=windows&logoColor=white)](https://github.com/wjn6/CXHarvest/releases)

**一款现代化的超星学习通作业题目导出桌面应用**

[📥 立即下载](https://github.com/wjn6/CXHarvest/releases) · 
[🐛 问题反馈](https://github.com/wjn6/CXHarvest/issues)

</div>

---

## ✨ 功能特点

<table>
<tr>
<td width="50%">

### 🔐 多样化登录
- 账号密码 / 短信验证码 / 二维码扫码
- 记住密码和手机号
- 自动保持登录状态

</td>
<td width="50%">

### 📚 智能内容管理
- 课程 → 作业 → 题目层次化浏览
- 实时搜索 + 关键词高亮
- 表格排序 + 状态智能识别

</td>
</tr>
<tr>
<td width="50%">

### 📄 强大导出功能
- **6种格式**: Markdown / HTML / Word / PDF / Excel / JSON
- 自定义导出内容（题目/答案/解析）
- 导出后自动打开文件目录

</td>
<td width="50%">

### 🎨 现代化界面
- Fluent Design 风格（QFluentWidgets）
- 深色 / 浅色主题切换（持久化）
- 流畅动画 + 进度条反馈

</td>
</tr>
</table>

### ⌨️ 快捷键

| 快捷键 | 功能 |
|:------:|------|
| `Ctrl+R` | 刷新当前页面 |
| `Esc` | 返回上一级 |
| `Ctrl+E` | 导出全部题目 |

---

## 🚀 快速开始

### 📥 下载发布版（推荐）

1. 前往 **[Releases](https://github.com/wjn6/CXHarvest/releases)** 下载最新 Setup 安装包
2. 运行安装程序，按提示完成安装
3. 从开始菜单或桌面快捷方式启动

> [!TIP]
> 发布版已打包所有依赖，**无需安装 Python 环境**

### 🔧 从源码运行

```bash
# 克隆仓库
git clone https://github.com/wjn6/CXHarvest.git
cd CXHarvest

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # macOS/Linux

# 安装依赖并启动
pip install -r requirements.txt
python main.py
```

### 📋 系统要求

| 项目 | 发布版 | 源码版 |
|:----:|:------:|:------:|
| 系统 | Windows 10+ | Windows / macOS / Linux |
| Python | ❌ 不需要 | 3.8+ |
| 内存 | 256MB+ | 256MB+ |

---

## 📖 使用指南

```
🚀 启动 → 🔐 登录 → 📚 课程 → 📝 作业 → ❓ 题目 → 📄 导出
```

| 步骤 | 操作说明 |
|:----:|----------|
| 1️⃣ | 点击左侧导航栏底部 **「登录」** 按钮 |
| 2️⃣ | 选择登录方式：密码 / 验证码 / 扫码 |
| 3️⃣ | 浏览课程卡片，搜索框支持关键词高亮 |
| 4️⃣ | 选择作业，点击列头可排序 |
| 5️⃣ | 勾选题目，点击 **「导出选中」** 或按 `Ctrl+E` |

<details>
<summary><b>🔍 更多高级功能</b></summary>

- **搜索筛选**: 按课程名/教师名/题型/正确性筛选
- **批量操作**: 全选/只选正确/只选错误
- **主题切换**: 深色/浅色主题（自动保存）
- **应用内更新**: 自动检查 + SHA256 校验下载

</details>

---

## 🛠️ 开发指南

### 技术栈

| 类别 | 技术 |
|:----:|------|
| 界面 | PySide6 + QFluentWidgets |
| 网络 | requests + urllib3 |
| 解析 | BeautifulSoup4 |
| 导出 | python-docx, reportlab, openpyxl |
| 加密 | pycryptodome (AES-CBC) |

### 项目结构

```
├── ui/                          # 界面组件
│   ├── main_window.py           # 主窗口（快捷键 + 应用内更新）
│   ├── login_dialog.py          # 登录对话框
│   ├── course_list.py           # 课程列表（搜索高亮）
│   ├── homework_list.py         # 作业列表（表格排序）
│   ├── question_list.py         # 题目列表
│   └── export_dialog.py         # 导出对话框
├── core/                        # 核心业务
│   ├── common.py                # 通用工具（PathManager）
│   ├── config_manager.py        # 配置管理
│   ├── enterprise_logger.py     # 日志系统
│   ├── login_manager.py         # 登录管理（凭据加密存储）
│   ├── course_manager.py        # 课程管理
│   └── homework_manager.py      # 作业管理
├── core/homework_question_parser/  # 题目解析
│   ├── parser.py                # 主解析器
│   ├── content_extractor.py     # 内容提取
│   └── image_handler.py         # 图片处理
├── installer/                   # Inno Setup 安装脚本
├── data/                        # 数据缓存
├── logs/                        # 日志输出
├── exports/                     # 导出文件
├── main.py                      # 程序入口
├── build.py                     # PyInstaller 打包脚本
└── requirements.txt             # 依赖列表
```

### 构建发布版

```bash
# 使用打包脚本（推荐）
python build.py

# 快速重复打包（跳过 clean）
python build.py --no-clean
```

> 说明: 推送 `v*.*.*` 格式的 tag 后，GitHub Actions 会自动构建 Setup 安装包并发布 Release。

---

## 📋 更新日志

### v3.0.0 — 2026.03 🎉

> 从 v2.0.0 到 v3.0.0 的所有更新汇总

#### 🔒 安全加固
| 更新内容 |
|----------|
| 登录凭据 AES-CBC 加密存储（随机 IV + 机器派生密钥） |
| 退出登录完整清除本地凭据（cookie / login_info） |
| 修复短信验证码发送无限递归风险（retry guard） |
| 更新下载增加 HTTP 状态校验 + SHA256 完整性验证 |

#### ✨ 新功能
| 更新内容 |
|----------|
| 应用内一键更新（自动检查 → 下载 → 安装） |
| 6 种导出格式（HTML / PDF / Word / Excel / JSON / Markdown） |
| 3 种 HTML 导出模板（青色 / 紫色 / 暗色），含 SVG 实时预览 |
| 三种登录方式（密码 / 短信验证码 / 扫码登录） |
| 深色 / 浅色主题切换（自动持久化） |
| 导出历史记录管理 |
| 全局快捷键支持（Ctrl+E 导出等） |
| 记住登录凭据（加密存储） |

#### 🔧 优化
| 更新内容 |
|----------|
| 统一全局 User-Agent，修改一处全局生效 |
| 合并 image_handler 重复批处理代码 |
| PathManager 集中管理所有输出路径 |
| 应用数据存储至 `%LOCALAPPDATA%\CXHarvest`（避免权限问题） |
| 导出目录默认为桌面 `CXHarvest_exports`，方便查找 |
| 安装路径改为全英文 `CXHarvest`（兼容性更好） |
| 导出支持取消、.tmp 安全写入防文件损坏 |
| 日志系统（毫秒精度 + 行号 + 日志轮转） |

#### 🎨 界面
| 更新内容 |
|----------|
| 全新 Fluent Design 界面（基于 QFluentWidgets） |
| 导出对话框圆角卡片式布局，浅灰底色层次分明 |
| 更新对话框文字颜色适配浅色 / 深色模式 |
| 课程列表搜索高亮、作业列表表格排序 |
| 题目列表空状态提示优化 |
| 进度条 / 加载动画指示 |

#### 🚀 DevOps
| 更新内容 |
|----------|
| GitHub Actions CI/CD 自动打包发布 |
| Inno Setup 生成 Windows 安装程序 |
| 推送 `v*.*.*` tag 自动构建正式 Release |
| main 分支推送自动构建 nightly 预览版 |
| SHA256 校验文件随安装包一起发布 |

#### 🐛 修复
| 更新内容 |
|----------|
| 课程列表 / 作业列表 / 题目列表空状态显示异常 |
| 导出取消后不再显示虚假成功消息 |
| 多页作业解析修复 |
| 题型识别升级 |
| 打包后 Program Files 目录写入权限崩溃 |
| 崩溃诊断日志写入 `%TEMP%` 方便排查 |

<details>
<summary><b>历史版本</b></summary>

### v2.0.0
- 全新 Fluent Design 界面
- 三种登录方式
- 6种导出格式

### v1.5.0
- 二维码登录
- 界面美化

</details>

---

## 💡 常见问题

<details>
<summary><b>❓ 应用无法启动</b></summary>

1. 确认系统为 Windows 10 或更高版本
2. 若使用源码版，检查 Python 版本 ≥ 3.8
3. 查看 `logs/` 目录下的日志文件

</details>

<details>
<summary><b>❓ 登录失败</b></summary>

1. 检查网络连接
2. 确认账号密码正确
3. 尝试其他登录方式（验证码/扫码）
4. 删除 `data/` 目录后重试

</details>

<details>
<summary><b>❓ 导出文件位置</b></summary>

默认保存在应用目录的 `exports/` 文件夹，导出完成后会自动打开目录。

</details>

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

```bash
# Fork 后本地开发
git checkout -b feature/your-feature
git commit -m "feat: add your feature"
git push origin feature/your-feature
```

---

## 📄 许可证

本项目基于 [GPL-3.0](LICENSE) 许可证开源。

---

<div align="center">

**⭐ 如果这个项目对你有帮助，请点个 Star！**

Made with ❤️ by [wjn6](https://github.com/wjn6)

</div>
