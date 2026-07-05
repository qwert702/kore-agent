# kore - 自动化任务编排引擎 / Automated Task Orchestration Engine

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

一个轻量级的自动化任务编排引擎，CLI 优先、Web 可选的渐进式架构。支持**定时任务**、**HTTP 请求**、**Python 脚本**和 **Shell 命令**的编排与自动调度，内置 AI 对话辅助与 Web 管理面板。

A lightweight task orchestration engine with a CLI-first, Web-optional progressive architecture. Supports **scheduled jobs**, **HTTP requests**, **Python scripts**, and **Shell commands** with built-in AI chat assistance and Web management dashboard.

```bash
# 在任何目录直接使用 / Use from any directory
kore --help
kore task list
kore task run 1
```

---

## 功能特性 / Features

- **📟 CLI 优先**：Typer 构建的丰富命令行界面，子命令体系完整
- **🤖 AI 对话**：内置 AI 对话模式，可用自然语言管理任务
- **🌐 Web 管理面板**：FastAPI + Bootstrap 5 构建的响应式管理界面（密码认证）
- **⏰ 定时调度**：APScheduler 支持的 Cron 表达式与固定间隔调度
- **🔌 多任务类型**：Shell 命令、Python 脚本、HTTP 请求
- **📊 执行追踪**：完整执行记录（stdout/stderr/退出码/耗时）
- **🛡️ 安全防护**：SSRF 防护、路径遍历防护、命令注入防护、暴力破解防护
- **⚡ 自动启动**：输入 `kore` 自动进入 AI 对话并启动 Web 服务

- **📟 CLI First**: Rich command-line interface built with Typer
- **🤖 AI Chat**: Built-in AI chat mode for natural language task management
- **🌐 Web Dashboard**: Responsive management UI powered by FastAPI + Bootstrap 5 (password-protected)
- **⏰ Scheduled Jobs**: Cron expressions and fixed-interval scheduling via APScheduler
- **🔌 Multi-task Types**: Shell commands, Python scripts, HTTP requests
- **📊 Execution Tracking**: Complete run history (stdout/stderr/exit code/duration)
- **🛡️ Security**: SSRF protection, path traversal prevention, command injection prevention, brute-force protection
- **⚡ Auto-start**: Type `kore` to automatically enter AI chat and launch Web service

---

## 快速开始 / Quick Start

### 安装 / Installation

```bash
# 克隆仓库 / Clone repository
git clone https://github.com/qwert702/D--CBN-Desktop-agent.git
cd D--CBN-Desktop-agent

# 创建虚拟环境并安装 / Create venv and install
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

pip install -e .
pip install -e ".[web]"   # 安装 Web 依赖 / Install Web dependencies
```

### 配置 / Configuration

创建 `.env` 文件（或从现有环境变量读取）：

Create a `.env` file (or read from existing environment variables):

```bash
OPENAI_API_KEY=sk-xxxxx
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-v4-flash

# Web 管理面板密码 / Web dashboard password
AGENT_WEB_SECRET_KEY=your-password-here
```

### 启动 / Launch

```bash
# 直接输入 kore → 自动进入 AI 对话 + 启动 Web 管理面板
# Type kore → automatically enters AI chat + starts Web dashboard
kore
```

Web 管理面板访问 `http://127.0.0.1:18081`，密码为 `AGENT_WEB_SECRET_KEY`。

---

## 使用示例 / Usage Examples

### 任务管理 / Task Management

```bash
# 创建 Shell 任务 / Create a Shell task
kore task add --name "hello" --type shell --command "echo Hello kore!"

# 创建 Python 任务 / Create a Python task
kore task add --name "py-demo" --type python --command "print('hello')"

# 创建 HTTP 定时任务（每5分钟）/ Create an HTTP scheduled task (every 5 min)
kore task add --name "health" --type http --url "https://api.example.com/health" --interval 300

# 创建 cron 定时任务（每天凌晨3点）/ Create a cron task (daily at 3am)
kore task add --name "backup" --type shell --command "./backup.sh" --schedule "0 3 * * *"

# 列出所有任务 / List all tasks
kore task list

# 查看任务详情 / View task details
kore task get 1 --runs

# 立即执行 / Run immediately
kore task run 1

# 暂停 / 恢复 / Pause / Resume
kore task pause 1
kore task resume 1

# 查看执行日志 / View run logs
kore task logs 1 --limit 10

# 删除任务 / Delete task
kore task delete 1 --force
```

### 守护进程 / Daemon

```bash
# 启动（前台运行）/ Start (foreground)
kore daemon start

# 查看状态 / Check status
kore daemon status

# 停止 / Stop
kore daemon stop
```

### Web 管理 / Web Management

```bash
# 手动启动 Web 服务 / Manually start Web service
kore web start

# 带热重载的开发模式 / Dev mode with hot reload
kore web start --reload --port 18081
```

---

## AI 对话模式 / AI Chat Mode

`kore` 无参数运行时自动进入 AI 对话模式，界面类似 Claude Code 的对话框风格：

When `kore` runs without arguments, it enters AI chat mode with a Claude Code-like dialog interface:

```
--------------------------------------------------

--------------------------------------------------
> 帮我创建一个每天备份数据库的任务
> Create a daily database backup task for me
```

支持用自然语言管理任务，例如：

You can manage tasks using natural language, for example:

> "帮我列出所有暂停的任务" / "List all paused tasks"
>
> "创建一个每5分钟检查网站健康的HTTP任务" / "Create an HTTP health check task every 5 minutes"
>
> "显示ID为3的任务详情" / "Show details of task ID 3"

---

## 项目结构 / Project Structure

```
kore/
├── cli/                  # CLI 层 / CLI Layer
│   ├── main.py               # Typer CLI 入口 / Entry point
│   ├── formatter.py          # 终端格式化 / Terminal formatting
│   └── commands/
│       ├── chat.py           # AI 对话 / AI Chat
│       ├── task.py           # 任务 CRUD / Task CRUD
│       ├── daemon.py         # 守护进程 / Daemon management
│       └── web.py            # Web 服务 / Web service
├── core/                 # 核心引擎 / Core Engine
│   ├── event_bus.py          # 事件总线 / Event bus
│   ├── executor.py           # 任务执行器 / Task executor
│   └── scheduler.py          # APScheduler 封装 / Scheduler wrapper
├── tasks/                # 内建任务类型 / Built-in Task Types
│   ├── base.py               # 任务基类 / Base class
│   ├── shell.py              # Shell 命令 / Shell commands
│   ├── python_task.py        # Python 脚本 / Python scripts
│   └── http.py               # HTTP 请求 / HTTP requests
├── storage/              # 持久化层 / Storage Layer
│   ├── db.py                 # 数据库引擎 / DB engine
│   ├── models.py             # ORM 模型 / ORM models
│   └── repository.py         # 数据访问层 / Data access layer
├── utils/                # 工具模块 / Utilities
│   ├── config.py             # 配置管理 / Configuration
│   ├── logger.py             # 结构化日志 / Structured logging
│   ├── retry.py              # 重试机制 / Retry mechanism
│   └── safe_path.py          # 路径安全 / Path safety
├── llm/                  # AI 对话模块 / AI Chat Module
│   ├── chat.py               # 对话引擎 / Chat engine
│   ├── client.py             # API 客户端 / API client
│   ├── tools.py              # 工具定义 / Tool definitions
│   └── tool_handlers.py      # 工具处理 / Tool handlers
├── web/                  # Web 管理面板 / Web Dashboard
│   ├── app.py                # FastAPI 应用 / FastAPI application
│   ├── auth.py               # 密码认证 / Password auth
│   ├── static/               # 静态文件 / Static files
│   ├── templates/            # Jinja2 模板 / Jinja2 templates
│   └── routes/
│       ├── dashboard.py      # 仪表盘 / Dashboard
│       ├── tasks.py          # 任务管理 / Task management
│       └── runs.py           # 执行记录 / Run history
├── tests/                # 测试 / Tests
├── pyproject.toml
└── README.md
```

---

## 安全设计 / Security Design

| 安全措施 / Measure | 说明 / Description |
|---|---|
| **SSRF 防护** | HTTP 任务 URL 自动校验，阻止内网地址请求 |
| **路径遍历防护** | 所有文件路径通过 `safe_resolve()` 规范化校验 |
| **命令注入防护** | 使用参数列表而非 shell 字符串执行命令 |
| **Web 密码认证** | Session 密码认证 + 暴力破解锁定 |
| **敏感数据保护** | Token/密码从环境变量读取，日志自动脱敏 |
| **任务超时控制** | 内置超时防止僵尸进程 |
| **审计日志** | 所有操作记录持久化到数据库，支持追溯 |

| **SSRF Protection** | HTTP task URLs validated against internal network addresses |
|---|---|
| **Path Traversal Prevention** | All file paths normalized via `safe_resolve()` |
| **Command Injection Prevention** | Parameters passed as list, not shell strings |
| **Web Auth** | Session-based password auth with brute-force lockout |
| **Sensitive Data** | Tokens/passwords from env vars, logs auto-masked |
| **Task Timeout** | Built-in timeout prevents zombie processes |
| **Audit Trail** | All operations persisted to database, fully traceable |

---

## 测试 / Testing

```bash
# 运行全部测试 / Run all tests
pytest tests/ -v

# 带覆盖率 / With coverage
pytest tests/ --cov=. --cov-report=term
```

---

## 技术栈 / Tech Stack

- **Python 3.11+** — 异步核心 / Async core
- **Typer** — CLI 框架 / CLI framework
- **FastAPI + Uvicorn** — Web 服务 / Web service
- **SQLAlchemy 2.0+** — ORM 框架 / ORM framework
- **APScheduler** — 任务调度 / Task scheduling
- **Jinja2 + Bootstrap 5** — 前端模板 / Frontend templates
- **OpenAI SDK** — AI 对话 / AI chat
- **Pydantic Settings** — 配置管理 / Config management

---

## 许可证 / License

MIT License © 2024 CBN
