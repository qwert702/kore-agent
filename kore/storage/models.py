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


class TriggerCondition(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    ALWAYS = "always"


class NotifyChannelType(str, enum.Enum):
    WEBHOOK = "webhook"
    EMAIL = "email"
    DESKTOP = "desktop"


class Task(Base):
    """任务定义"""

    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    description = Column(Text, default="")

    # 任务类型
    task_type = Column(Enum(TaskType), nullable=False)

    # 任务配置（JSON）
    config = Column(Text, nullable=False, default="{}")

    # 调度配置
    schedule_type = Column(Enum(ScheduleType), nullable=True)
    schedule_expr = Column(String(256), nullable=True)
    schedule_timezone = Column(String(64), default="Asia/Shanghai")

    # 执行配置
    timeout = Column(Integer, default=300)
    retry_enabled = Column(Boolean, default=False)
    retry_max_attempts = Column(Integer, default=3)
    retry_delay = Column(Float, default=5.0)

    # 链式触发
    trigger_condition = Column(Enum(TriggerCondition), nullable=True)
    trigger_task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)

    # 通知关联
    notify_on_success = Column(Boolean, default=False)
    notify_on_failure = Column(Boolean, default=True)
    notify_channel_ids = Column(String(256), default="")  # 逗号分隔的 Notification 记录 ID

    # 状态
    status = Column(Enum(TaskStatus), default=TaskStatus.ACTIVE, index=True)

    # 元数据
    tags = Column(String(512), default="")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # 关系
    runs = relationship(
        "TaskRun", back_populates="task", cascade="all, delete-orphan", order_by="TaskRun.started_at.desc()"
    )
    child_trigger = relationship(
        "Task", remote_side=[id],
        foreign_keys=[trigger_task_id],
        primaryjoin="Task.id == Task.trigger_task_id",
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"<Task(id={self.id}, name={self.name!r}, type={self.task_type})>"


class TaskRun(Base):
    """任务执行记录"""

    __tablename__ = "task_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)
    status = Column(Enum(RunStatus), nullable=False, default=RunStatus.PENDING)
    trigger = Column(String(32), default="manual")

    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    exit_code = Column(Integer, nullable=True)
    stdout = Column(Text, default="")
    stderr = Column(Text, default="")
    error_message = Column(Text, default="")

    task = relationship("Task", back_populates="runs")

    def __repr__(self) -> str:
        return f"<TaskRun(id={self.id}, task_id={self.task_id}, status={self.status})>"


class Notification(Base):
    """通知渠道配置"""

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False, index=True)
    channel = Column(Enum(NotifyChannelType), nullable=False)

    # Webhook 配置
    webhook_url = Column(String(512), default="")
    webhook_method = Column(String(16), default="POST")
    webhook_headers = Column(Text, default="{}")  # JSON

    # Email 配置
    smtp_host = Column(String(256), default="")
    smtp_port = Column(Integer, default=587)
    smtp_user = Column(String(256), default="")
    smtp_password = Column(String(256), default="")
    email_from = Column(String(256), default="")
    email_to = Column(String(512), default="")

    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, name={self.name!r}, channel={self.channel})>"


class Workflow(Base):
    """工作流定义（二期）"""

    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    description = Column(Text, default="")
    definition = Column(Text, nullable=False)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
