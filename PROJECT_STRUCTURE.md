# 项目结构说明

## 目录结构

```
@yingyong/
├── main.py                 # 程序入口
├── requirements.txt        # 依赖列表
├── build.py               # 打包脚本
├── core/                  # 核心业务逻辑
│   ├── __init__.py
│   ├── common.py          # 公共常量和工具函数
│   ├── config_manager.py  # 配置管理
│   ├── login_manager.py   # 登录管理（Cookie/二维码/账密）
│   ├── course_manager.py  # 课程管理
│   ├── homework_manager.py         # 作业列表管理
│   ├── homework_question_parser/    # 题目解析器（包含图片处理 ImageHandler）
│   ├── question_exporter.py        # 题目导出（多格式）
│   ├── export_history.py           # 导出历史管理
│   ├── enterprise_logger.py        # 日志系统
│   └── version.py                  # 版本信息
├── ui/                    # UI界面
│   ├── __init__.py
│   ├── main_window.py     # 主窗口（导航中心）
│   ├── login_dialog.py    # 登录对话框
│   ├── course_list.py     # 课程列表页
│   ├── homework_list.py   # 作业列表页
│   ├── question_list.py   # 题目列表页
│   ├── export_dialog.py   # 导出对话框
│   ├── export_history.py  # 导出历史页
│   └── image_preview.py   # 图片预览
├── data/                  # 数据存储
└── logs/                  # 日志文件
```

## 核心流程

```
登录 → 课程列表 → 作业列表 → 题目解析 → 导出
```

### 1. 登录流程
- `LoginManager` 支持三种方式：Cookie、二维码、账号密码
- 登录成功后保存Session用于后续请求

### 2. 数据获取流程
```
CourseManager.get_courses()     → 获取课程列表
HomeworkManager.get_homework()  → 获取作业列表（支持分页）
HomeworkQuestionParser.parse_homework_questions()  → 解析题目详情
```

### 3. 导出流程
```
QuestionExporter → 支持 HTML/JSON/Markdown/Word/PDF
ExportHistoryManager → 记录导出历史
```

## 信号流（UI层）

```
MainWindow
├── CourseList
│   └── course_selected → 加载作业列表
├── HomeworkList
│   ├── homework_selected → 加载题目
│   └── batch_export → 批量导出
├── QuestionList
│   └── export → 导出题目
└── ExportHistory
    └── 查看导出记录
```

## 模块职责

| 模块 | 职责 |
|------|------|
| `login_manager` | 处理登录认证，维护Session |
| `course_manager` | 获取和缓存课程列表 |
| `homework_manager` | 获取作业列表，处理分页 |
| `homework_question_parser` | 解析作业页面，提取题目信息 |
| `question_exporter` | 多格式导出题目 |
| `export_history` | 记录和管理导出历史 |
