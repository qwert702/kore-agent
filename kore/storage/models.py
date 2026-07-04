"""数据模型定义"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from kore.storage.db import Base


class TaskType(str, enum.Enum):
    SHELL = "shell"
    PYTHON = "python"
    HTTP = "http"
    FILE_OPS = "file_ops"
    NOTIFY = "notify"
    WORKFLOW = "workflow"


class TaskStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


class ScheduleType(str, enum.Enum):
    CRON = "cron"
    INTERVAL = "interval"
    DATE = "date"


class RunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class Task(Base):
    """任务定义"""

    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    description = Column(Text, default="")

    # 任务类型
    task_type = Column(Enum(TaskType), nullable=False)

    # 任务配置（JSON 字符串，包含不同任务类型的参数）
    config = Column(Text, nullable=False, default="{}")

    # 调度配置
    schedule_type = Column(Enum(ScheduleType), nullable=True)
    schedule_expr = Column(String(256), nullable=True)  # cron / interval / date
    schedule_timezone = Column(String(64), default="Asia/Shanghai")

    # 执行配置
    timeout = Column(Integer, default=300)  # 秒
    retry_enabled = Column(Boolean, default=False)
    retry_max_attempts = Column(Integer, default=3)
    retry_delay = Column(Float, default=5.0)

    # 状态
    status = Column(Enum(TaskStatus), default=TaskStatus.ACTIVE, index=True)

    # 元数据
    tags = Column(String(512), default="")  # 逗号分隔
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # 关系
    runs = relationship(
        "TaskRun", back_populates="task", cascade="all, delete-orphan", order_by="TaskRun.started_at.desc()"
    )

    def __repr__(self) -> str:
        return f"<Task(id={self.id}, name={self.name!r}, type={self.task_type})>"


class TaskRun(Base):
    """任务执行记录"""

    __tablename__ = "task_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)
    status = Column(Enum(RunStatus), nullable=False, default=RunStatus.PENDING)
    trigger = Column(String(32), default="manual")  # manual / schedule / watch

    # 执行信息
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # 结果
    exit_code = Column(Integer, nullable=True)
    stdout = Column(Text, default="")
    stderr = Column(Text, default="")
    error_message = Column(Text, default="")

    # 关联
    task = relationship("Task", back_populates="runs")

    def __repr__(self) -> str:
        return f"<TaskRun(id={self.id}, task_id={self.task_id}, status={self.status})>"


class Workflow(Base):
    """工作流定义（二期）"""

    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    description = Column(Text, default="")
    definition = Column(Text, nullable=False)  # YAML/JSON 定义
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
