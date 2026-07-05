"""工具定义注册表 - kore 功能的 function calling schema"""

from __future__ import annotations

from typing import Any

# DeepSeek/OpenAI 兼容的 tools 格式
TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": "在 generated/ 目录下创建或覆写一个文件。可以用来生成 Python 游戏、脚本、HTML 页面等任何代码文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "文件名（如 game.py、index.html）。会自动放到 generated/ 目录下",
                    },
                    "content": {
                        "type": "string",
                        "description": "文件内容（代码）",
                    },
                    "description": {
                        "type": "string",
                        "description": "这个文件是做什么的（用于文件头注释）",
                    },
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bash_run",
            "description": "在终端执行一条非交互式命令并获取输出。适合运行 pip install、python game.py 等",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 bash 命令",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时秒数（默认 30）",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_list",
            "description": "列出所有已创建的任务，可按状态（active/paused/disabled）或类型（shell/python/http）筛选",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["active", "paused", "disabled"],
                        "description": "按状态筛选",
                    },
                    "task_type": {
                        "type": "string",
                        "enum": ["shell", "python", "http"],
                        "description": "按任务类型筛选",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_add",
            "description": "创建新的自动化任务。支持 shell 命令、Python 脚本、HTTP 请求三种类型。可设置定时调度（cron/间隔）",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "任务名称，需唯一"},
                    "task_type": {
                        "type": "string",
                        "enum": ["shell", "python", "http"],
                        "description": "任务类型",
                    },
                    "command": {
                        "type": "string",
                        "description": "shell 命令或 Python 内联代码。shell 类型必填",
                    },
                    "url": {
                        "type": "string",
                        "description": "HTTP 请求的 URL。http 类型必填",
                    },
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                        "description": "HTTP 请求方法（默认 GET）",
                    },
                    "description": {"type": "string", "description": "任务描述"},
                    "schedule": {
                        "type": "string",
                        "description": "调度表达式。cron格式如 '0 9 * * *'（每天9点），间隔如 '300' 或 '5m' 或 '1h'，日期如 '2026-07-05 09:00:00'",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "执行超时时间（秒），默认 300",
                    },
                    "tags": {"type": "string", "description": "标签，逗号分隔"},
                },
                "required": ["name", "task_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_get",
            "description": "查看单个任务的详细信息，包括配置和执行历史",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "任务 ID",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_run",
            "description": "立即执行一个已存在的任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "要执行的任务 ID",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_pause",
            "description": "暂停一个定时任务，暂停后不会再被调度执行",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "任务 ID",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_resume",
            "description": "恢复一个已暂停的定时任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "任务 ID",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_delete",
            "description": "删除一个任务及其所有执行记录",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "任务 ID",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_logs",
            "description": "查看任务的最近执行日志，包括执行结果、标准输出、错误信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "任务 ID",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "显示最近多少条记录（默认 5）",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "daemon_status",
            "description": "查看守护进程运行状态，调度器是否正常运行，以及当前注册的定时任务数量",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]
