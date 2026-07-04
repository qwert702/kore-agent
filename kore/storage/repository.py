"""数据访问层 - 任务 CRUD"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select, update

from kore.storage.models import Task, TaskRun, TaskStatus, RunStatus, ScheduleType, TaskType


class TaskRepository:
    """任务仓储"""

    def __init__(self, session: Any) -> None:
        self.session = session

    # --- Task CRUD ---

    def _serialize_config(self, config: Any) -> str:
        """将配置序列化为 JSON 字符串"""
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
        self.session.add(task)
        self.session.flush()
        return task

    def get_task(self, task_id: int) -> Task | None:
        """获取单个任务"""
        return self.session.get(Task, task_id)

    def get_task_by_name(self, name: str) -> Task | None:
        """按名称获取任务"""
        stmt = select(Task).where(Task.name == name)
        return self.session.scalar(stmt)

    def list_tasks(
        self,
        status: TaskStatus | None = None,
        task_type: TaskType | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Task]:
        """列出任务"""
        stmt = select(Task)
        if status:
            stmt = stmt.where(Task.status == status)
        if task_type:
            stmt = stmt.where(Task.task_type == task_type)
        stmt = stmt.offset(offset).limit(limit).order_by(Task.created_at.desc())
        return list(self.session.scalars(stmt).all())

    def update_task(self, task_id: int, **kwargs: Any) -> Task | None:
        """更新任务"""
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
        return self.get_task(task_id)

    def delete_task(self, task_id: int) -> bool:
        """删除任务"""
        task = self.get_task(task_id)
        if not task:
            return False
        self.session.delete(task)
        self.session.flush()
        return True

    def set_task_status(self, task_id: int, status: TaskStatus) -> Task | None:
        """设置任务状态（暂停/恢复/禁用）"""
        return self.update_task(task_id, status=status)

    # --- TaskRun ---

    def create_run(
        self,
        task_id: int,
        trigger: str = "manual",
    ) -> TaskRun:
        """创建执行记录"""
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
        """更新执行记录"""
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
        """获取任务执行历史"""
        stmt = (
            select(TaskRun)
            .where(TaskRun.task_id == task_id)
            .order_by(TaskRun.started_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())
