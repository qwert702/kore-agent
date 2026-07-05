"""结构化日志模块

设计原则：
- 模块顶层不输出任何日志到控制台（由调用方决定）
- 通过 setup_logger() 显式初始化
- get_logger() 惰性创建子日志器
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from kore.utils.config import settings


# ── REPL 静默控制台模式 ────────────────────────────────
_console_silent = False


def set_console_silent(silent: bool) -> None:
    """设置控制台静默模式（REPL 模式下隐藏 JSON 日志）"""
    global _console_silent
    _console_silent = silent
    settings.log_console_silent = silent

    # 禁用所有相关日志器的控制台输出
    # 根日志器
    root = logging.getLogger()
    root.handlers.clear()
    root.propagate = False

    # agent 及其子 logger
    agent_logger = logging.getLogger("agent")
    agent_logger.handlers.clear()
    agent_logger.propagate = False

    # 其他已知会输出的日志器
    for name in ("apscheduler", "uvicorn", "uvicorn.error",
                 "uvicorn.access", "httpx", "openai", "sqlalchemy",
                 "apscheduler.executors.default", "apscheduler.scheduler"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = False

    # 禁用 Python logging 的 lastResort handler（WARNING 级别 fallback）
    import logging as _logging
    if hasattr(_logging, 'lastResort') and _logging.lastResort:
        _logging.lastResort = None
    # 捕获 "No handlers could be found" 警告
    logging.raiseExceptions = False
    # 给相关日志器加 NullHandler 避免 "No handlers could be found" 警告
    for _name in ("agent", "agent.trigger", "agent.notifier", "agent.scheduler",
                  "agent.web", "agent.chat", "agent.tool_handlers",
                  "agent.task.shell", "agent.task.http", "agent.task.python",
                  "uvicorn", "uvicorn.error", "uvicorn.access"):
        _lg = logging.getLogger(_name)
        if not _lg.handlers:
            _lg.addHandler(logging.NullHandler())


class JSONFormatter(logging.Formatter):
    """输出 JSON 格式的日志"""

    def format(self, record: logging.LogRecord) -> str:
        obj: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            obj["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "task_id"):
            obj["task_id"] = record.task_id
        if hasattr(record, "extra"):
            obj["extra"] = record.extra
        return json.dumps(obj, ensure_ascii=False)


def setup_logger(name: str = "agent") -> logging.Logger:
    """配置并返回应用日志器（含控制台 + 文件输出）"""
    logger = logging.getLogger(name)
    logger.setLevel(settings.log_level.upper())
    logger.handlers.clear()

    # 控制台输出（REPL 模式下静音）
    if not _console_silent and not settings.log_console_silent:
        console_handler = logging.StreamHandler(sys.stdout)
        if settings.log_format == "json":
            console_handler.setFormatter(JSONFormatter())
        else:
            console_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
        logger.addHandler(console_handler)

    # 文件输出
    log_file = settings.logs_dir / "agent.log"
    try:
        file_handler = RotatingFileHandler(
            filename=str(log_file),
            maxBytes=settings.log_max_bytes,
            backupCount=settings.log_backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)
    except (OSError, PermissionError):
        pass  # 文件日志失败不阻塞

    return logger


_initialized_loggers: set[str] = set()


def get_logger(name: str) -> logging.Logger:
    """获取子模块日志器（惰性初始化，不添加 handler，传播到根日志器）"""
    logger = logging.getLogger(f"agent.{name}")
    if name not in _initialized_loggers:
        _initialized_loggers.add(name)
        logger.setLevel(settings.log_level.upper())
    return logger


# 模块顶层的默认日志器（不添加 handler — 靠 setup_logger 或上层应用管理）
logger = logging.getLogger("agent")
logger.setLevel(logging.DEBUG if settings.log_level.upper() == "DEBUG" else logging.INFO)
logger.propagate = True  # 传播到根日志器
