"""结构化日志模块"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from kore.utils.config import settings


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
    """配置并返回应用日志器"""
    logger = logging.getLogger(name)
    logger.setLevel(settings.log_level.upper())
    logger.handlers.clear()

    # 控制台输出（始终有）
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

    # 文件输出（可配置）
    log_file = settings.logs_dir / "agent.log"
    file_handler = RotatingFileHandler(
        filename=str(log_file),
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)

    return logger


logger = setup_logger()


def get_logger(name: str) -> logging.Logger:
    """获取子模块日志器"""
    return logging.getLogger(f"agent.{name}")
