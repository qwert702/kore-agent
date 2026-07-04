# kore - 自动化任务编排引擎

一个轻量级的自动化任务编排引擎，CLI 优先、Web 可选的渐进式架构。支持**定时任务**、**HTTP 请求**、**Python 脚本**和 **Shell 命令**的编排与自动调度。

```bash
# 在任何目录直接使用
kore --help
kore task list
kore task run 1
```

## 快速开始

```bash
# 安装依赖
pip install typer rich apscheduler sqlalchemy httpx pyyaml pydantic pydantic-settings

# 确认安装
kore --help
```

> `kore` 命令会自动注册到 PATH（位于 venv Scripts 目录），在任何目录下直接输入即可使用。

## 使用示例

### 任务管理

```bash
# 创建 Shell 任务
kore task add --name "hello" --type shell --command "echo Hello kore!"

# 创建 Python 内联任务
kore task add --name "py-demo" --type python --command "print('hello')"

# 创建 HTTP 定时任务（每5分钟）
kore task add --name "health" --type http --url "https://api.example.com/health" --interval 300

# 创建定时任务（cron 表达式，每天凌晨3点）
kore task add --name "backup" --type shell --command "./backup.sh" --schedule "0 3 * * *"

# 列出所有任务
kore task list

# 查看任务详情
kore task get 1 --runs

# 立即执行
kore task run 1

# 暂停/恢复
kore task pause 1
kore task resume 1

# 查看执行日志
kore task logs 1 --limit 10

# 删除任务
kore task delete 1 --force
```

### 守护进程

```bash
# 启动（前台运行）
kore daemon start

# 查看状态
kore daemon status

# 停止
kore daemon stop
```

## 项目结构

```
kore/
├── cli/              # CLI 层
│   ├── main.py           # Typer CLI 入口
│   ├── formatter.py      # 终端格式化输出
│   └── commands/
│       ├── task.py       # 任务 CRUD
│       └── daemon.py     # 守护进程管理
├── core/             # 核心引擎
│   ├── event_bus.py      # 事件总线（解耦组件）
│   ├── executor.py       # 任务执行器（类型注册+分发）
│   └── scheduler.py      # APScheduler 调度封装
├── tasks/            # 内建任务类型
│   ├── base.py           # 任务基类
│   ├── shell.py          # Shell 命令
│   ├── python_task.py    # Python 脚本
│   └── http.py           # HTTP 请求
├── storage/          # 持久化层
│   ├── db.py             # 数据库引擎（同步+异步惰性加载）
│   ├── models.py         # ORM 模型
│   └── repository.py     # 数据访问层
├── utils/            # 工具模块
│   ├── config.py         # Pydantic 配置管理
│   ├── logger.py         # 结构化日志（JSON+文件回滚）
│   ├── retry.py          # 重试机制（同步+异步）
│   └── safe_path.py      # 路径安全校验
├── web/              # Web 服务（二期）
├── tests/            # 测试
├── pyproject.toml
└── README.md
```

## 安全设计

- **路径遍历防护**：所有文件路径通过 `safe_resolve()` 进行规范化校验
- **命令注入防护**：默认使用 `shlex.split()` + `subprocess.run` 传参数列表，不使用 shell
- **敏感数据**：Token/密码从环境变量读取（`KORE_*` 前缀），日志自动脱敏
- **任务超时**：内置超时控制，防止僵尸进程
- **审计日志**：所有任务执行记录持久化到数据库，支持追溯

## 测试

```bash
# 运行全部测试
pytest tests/ -v

# 带覆盖率
pytest tests/ --cov=. --cov-report=term
```

## 二期规划

- [ ] Web 管理界面（FastAPI + HTMX）
- [ ] 文件监控（watchfiles）
- [ ] 工作流编排（YAML DAG 定义）
- [ ] 桌面通知（plyer）
- [ ] 与英语学习平台集成
