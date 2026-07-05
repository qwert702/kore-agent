"""数据访问层 - 任务 CRUD + 通知 CRUD + 数据清理"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, update

from kore.storage.models import (
    Notification,
    RunStatus,
    ScheduleType,
    Task,
    TaskRun,
    TaskStatus,
    TaskType,
)
from kore.utils.config import settings


class TaskRepository:
    """任务仓储"""

    def __init__(self, session: Any) -> None:
        self.session = session

    # --- Task CRUD ---

    def _serialize_config(self, config: Any) -> str:
        if isinstance(config, str):
            return config
        return json.dumps(config, ensure_ascii=False, default=str)

    def create_task(
        self,
        name: str,
        task_type: TaskType,
        config: dict[str, Any] | None = None,
        description: str = "",
        schedule_type: ScheduleType | None = None,
        schedule_expr: str | None = None,
        schedule_timezone: str = "Asia/Shanghai",
        timeout: int = 300,
        tags: str = "",
        trigger_condition: str | None = None,
        trigger_task_id: int | None = None,
    ) -> Task:
        """创建任务"""
        task = Task(
            name=name,
            task_type=task_type,
            config=self._serialize_config(config or {}),
            description=description,
            schedule_type=schedule_type,
            schedule_expr=schedule_expr,
            schedule_timezone=schedule_timezone,
            timeout=timeout,
            tags=tags,
        )
        if trigger_condition:
            from kore.storage.models import TriggerCondition
            task.trigger_condition = TriggerCondition(trigger_condition)
        if trigger_task_id:
            task.trigger_task_id = trigger_task_id
        self.session.add(task)
        self.session.flush()
        return task

    def get_task(self, task_id: int) -> Task | None:
        return self.session.get(Task, task_id)

    def get_task_by_name(self, name: str) -> Task | None:
        stmt = select(Task).where(Task.name == name)
        return self.session.scalar(stmt)

    def list_tasks(
        self,
        status: TaskStatus | None = None,
        task_type: TaskType | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Task]:
        stmt = select(Task)
        if status:
            stmt = stmt.where(Task.status == status)
        if task_type:
            stmt = stmt.where(Task.task_type == task_type)
        stmt = stmt.offset(offset).limit(limit).order_by(Task.created_at.desc(), Task.id.desc())
        return list(self.session.scalars(stmt).all())

    def update_task(self, task_id: int, **kwargs: Any) -> Task | None:
        if "config" in kwargs:
            kwargs["config"] = self._serialize_config(kwargs["config"])
        kwargs["updated_at"] = datetime.now()
        stmt = (
            update(Task)
            .where(Task.id == task_id)
            .values(**kwargs)
        )
        self.session.execute(stmt)
        self.session.flush()
        self.session.expire_all()
        return self.get_task(task_id)

    def delete_task(self, task_id: int) -> bool:
        task = self.get_task(task_id)
        if not task:
            return False
        self.session.delete(task)
        self.session.flush()
        return True

    def set_task_status(self, task_id: int, status: TaskStatus) -> Task | None:
        return self.update_task(task_id, status=status)

    def list_tasks_with_trigger(self) -> list[Task]:
        """列出有链式触发配置的任务"""
        stmt = select(Task).where(
            Task.trigger_condition.isnot(None),
            Task.trigger_task_id.isnot(None),
        )
        return list(self.session.scalars(stmt).all())

    # --- TaskRun ---

    def create_run(self, task_id: int, trigger: str = "manual") -> TaskRun:
        run = TaskRun(
            task_id=task_id,
            trigger=trigger,
            status=RunStatus.PENDING,
            started_at=datetime.now(),
        )
        self.session.add(run)
        self.session.flush()
        return run

    def update_run(
        self,
        run_id: int,
        status: RunStatus,
        stdout: str = "",
        stderr: str = "",
        error_message: str = "",
        exit_code: int | None = None,
    ) -> TaskRun | None:
        run = self.session.get(TaskRun, run_id)
        if not run:
            return None
        run.status = status
        run.finished_at = datetime.now()
        if run.started_at and run.finished_at:
            run.duration_ms = int(
                (run.finished_at - run.started_at).total_seconds() * 1000
            )
        if stdout:
            run.stdout = stdout
        if stderr:
            run.stderr = stderr
        if error_message:
            run.error_message = error_message
        if exit_code is not None:
            run.exit_code = exit_code
        self.session.flush()
        return run

    def get_task_runs(
        self,
        task_id: int,
        offset: int = 0,
        limit: int = 50,
    ) -> list[TaskRun]:
        stmt = (
            select(TaskRun)
            .where(TaskRun.task_id == task_id)
            .order_by(TaskRun.started_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def clean_old_runs(self, days: int = 90) -> int:
        """清理超过指定天数的执行记录"""
        cutoff = datetime.now() - timedelta(days=days)
        stmt = delete(TaskRun).where(TaskRun.started_at < cutoff)
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def clean_excess_runs(self, max_per_task: int = 1000) -> int:
        """每个任务保留最多 max_per_task 条执行记录"""
        total = 0
        tasks = self.list_tasks(limit=5000)
        for task in tasks:
            stmt = select(TaskRun.id).where(TaskRun.task_id == task.id).order_by(TaskRun.started_at.desc()).offset(max_per_task)
            excess_ids = [row[0] for row in self.session.execute(stmt).fetchall()]
            if excess_ids:
                delete_stmt = delete(TaskRun).where(TaskRun.id.in_(excess_ids))
                result = self.session.execute(delete_stmt)
                total += result.rowcount
        if total:
            self.session.flush()
        return total

    def mark_running_as_failed(self) -> int:
        """标记所有 RUNNING 状态的任务为 FAILED（用于崩溃恢复）"""
        stmt = (
            update(TaskRun)
            .where(TaskRun.status == RunStatus.RUNNING)
            .values(
                status=RunStatus.FAILED,
                error_message="进程崩溃，任务未正常完成",
                finished_at=datetime.now(),
            )
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    # --- Notification CRUD ---

    def create_notification(
        self,
        name: str,
        channel: str,
        webhook_url: str = "",
        webhook_method: str = "POST",
        webhook_headers: str = "{}",
        smtp_host: str = "",
        smtp_port: int = 587,
        smtp_user: str = "",
        smtp_password: str = "",
        email_from: str = "",
        email_to: str = "",
        enabled: bool = True,
    ) -> Notification:
        """创建通知渠道"""
        from kore.storage.models import NotifyChannelType
        n = Notification(
            name=name,
            channel=NotifyChannelType(channel),
            webhook_url=webhook_url,
            webhook_method=webhook_method,
            webhook_headers=webhook_headers,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_user=smtp_user,
            smtp_password=smtp_password,
            email_from=email_from,
            email_to=email_to,
            enabled=enabled,
        )
        self.session.add(n)
        self.session.flush()
        return n

    def list_notifications(self) -> list[Notification]:
        stmt = select(Notification).order_by(Notification.created_at.desc())
        return list(self.session.scalars(stmt).all())

    def get_notification(self, notification_id: int) -> Notification | None:
        return self.session.get(Notification, notification_id)

    def delete_notification(self, notification_id: int) -> bool:
        n = self.get_notification(notification_id)
        if not n:
            return False
        self.session.delete(n)
        self.session.flush()
        return True
