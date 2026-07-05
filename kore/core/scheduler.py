"""调度器 - 基于 APScheduler 的任务调度引擎"""

from __future__ import annotations

import json
import signal
from datetime import datetime, timezone
from typing import Any

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.date import DateTrigger
    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False
    AsyncIOScheduler = object  # type: ignore

from kore.core.event_bus import event_bus
from kore.core.executor import execute_task
from kore.storage.db import get_sync_session
from kore.storage.models import ScheduleType, Task, TaskRun, TaskStatus, RunStatus
from kore.storage.repository import TaskRepository
from kore.utils.config import settings
from kore.utils.logger import get_logger

logger = get_logger("scheduler")


class SchedulerEngine:
    """调度引擎 - 管理定时任务的触发和执行"""

    def __init__(self) -> None:
        self._scheduler: AsyncIOScheduler | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def _get_jobstore_url(self) -> str:
        """获取 APScheduler 专用的 jobstore URL"""
        db_path = settings.data_dir / "agent.db"
        return f"sqlite:///{db_path}"

    async def start(self) -> None:
        """启动调度器 + 崩溃恢复"""
        if not HAS_APSCHEDULER:
            logger.warning("APScheduler 未安装，跳过调度器启动")
            return

        if self._running:
            logger.warning("调度器已在运行")
            return

        # 崩溃恢复：标记所有 RUNNING 状态的任务为 FAILED
        try:
            with get_sync_session() as session:
                repo = TaskRepository(session)
                recovered = repo.mark_running_as_failed()
                if recovered:
                    logger.warning("崩溃恢复：已将 %d 个正在运行的任务标记为 FAILED", recovered)
        except Exception as e:
            logger.warning("崩溃恢复检查失败: %s", e)

        jobstore = SQLAlchemyJobStore(url=self._get_jobstore_url())

        self._scheduler = AsyncIOScheduler(
            jobstores={"default": jobstore},
            timezone=settings.scheduler_timezone,
        )

        # 从数据库加载所有激活的任务
        self._load_tasks()

        self._scheduler.start()
        self._running = True
        logger.info("调度器已启动 (timezone=%s)", settings.scheduler_timezone)

    async def stop(self) -> None:
        """停止调度器"""
        if self._scheduler and self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("调度器已停止")

    def _load_tasks(self) -> None:
        """从数据库加载所有活动任务到调度器"""
        if not self._scheduler:
            return

        with get_sync_session() as session:
            repo = TaskRepository(session)
            tasks = repo.list_tasks(status=TaskStatus.ACTIVE)

        count = 0
        for task in tasks:
            if task.schedule_type and task.schedule_expr:
                self._schedule_task(task)
                count += 1

        logger.info("已加载 %d 个定时任务", count)

    def _schedule_task(self, task: Task) -> str | None:
        """注册单个任务到调度器"""
        if not self._scheduler or not task.schedule_type or not task.schedule_expr:
            return None

        job_id = f"task_{task.id}"

        # 移除已存在的 job
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

        trigger = self._build_trigger(task.schedule_type, task.schedule_expr)
        if trigger is None:
            logger.warning("任务 %s 调度表达式无效: %s %s", task.name, task.schedule_type, task.schedule_expr)
            return None

        self._scheduler.add_job(
            func=self._run_task_job,
            trigger=trigger,
            args=[task.id, task.name],
            id=job_id,
            name=task.name,
            replace_existing=True,
            misfire_grace_time=60,
        )

        logger.info("注册定时任务: %s (id=%s, trigger=%s)", task.name, job_id, task.schedule_expr)
        return job_id

    def _build_trigger(
        self, schedule_type: ScheduleType, expr: str
    ) -> Any | None:
        """构建 APScheduler 触发器"""
        try:
            if schedule_type == ScheduleType.CRON:
                # 标准 5 字段 cron: "分 时 日 月 周"
                parts = expr.strip().split()
                if len(parts) == 5:
                    return CronTrigger(
                        minute=parts[0],
                        hour=parts[1],
                        day=parts[2],
                        month=parts[3],
                        day_of_week=parts[4],
                        timezone=settings.scheduler_timezone,
                    )
                elif len(parts) == 6:
                    return CronTrigger(
                        second=parts[0],
                        minute=parts[1],
                        hour=parts[2],
                        day=parts[3],
                        month=parts[4],
                        day_of_week=parts[5],
                        timezone=settings.scheduler_timezone,
                    )
            elif schedule_type == ScheduleType.INTERVAL:
                # 间隔: "300" (秒) 或 "5m"、"1h"、"2d"
                seconds = self._parse_interval(expr)
                if seconds:
                    return IntervalTrigger(seconds=seconds)
            elif schedule_type == ScheduleType.DATE:
                # 一次性: "2026-07-04 09:00:00"
                dt = datetime.fromisoformat(expr)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return DateTrigger(run_date=dt)
        except Exception as e:
            logger.error("触发器构建失败: %s", e)
        return None

    def _parse_interval(self, expr: str) -> int | None:
        """解析间隔表达式为秒数"""
        expr = expr.strip().lower()
        try:
            if expr.endswith("s"):
                return int(expr[:-1])
            elif expr.endswith("m"):
                return int(expr[:-1]) * 60
            elif expr.endswith("h"):
                return int(expr[:-1]) * 3600
            elif expr.endswith("d"):
                return int(expr[:-1]) * 86400
            else:
                return int(expr)
        except ValueError:
            return None

    async def _run_task_job(self, task_id: int, task_name: str) -> None:
        """调度器触发的任务执行回调"""
        logger.info("调度器触发任务: %s (id=%d)", task_name, task_id)

        with get_sync_session() as session:
            repo = TaskRepository(session)
            task = repo.get_task(task_id)
            if not task:
                logger.warning("任务 %d 不存在，跳过", task_id)
                return

            task_run = repo.create_run(task_id=task_id, trigger="schedule")
            run_id = task_run.id

            try:
                result = await execute_task(task)

                if result.success:
                    repo.update_run(
                        run_id=run_id,
                        status=RunStatus.SUCCESS,
                        stdout=result.stdout,
                        stderr=result.stderr,
                        exit_code=result.exit_code or 0,
                    )
                else:
                    repo.update_run(
                        run_id=run_id,
                        status=RunStatus.FAILED,
                        stdout=result.stdout,
                        stderr=result.stderr,
                        exit_code=result.exit_code,
                        error_message=result.error_message,
                    )

                await event_bus.publish(
                    "task.completed" if result.success else "task.failed",
                    task_id=task_id,
                    task_name=task_name,
                    run_id=run_id,
                    result=result,
                )
            except Exception as e:
                logger.error("任务 %s 执行异常: %s", task_name, e)
                repo.update_run(
                    run_id=run_id,
                    status=RunStatus.FAILED,
                    error_message=str(e),
                )

    def add_task(self, task: Task) -> str | None:
        """添加任务到调度器（调用前确保 task 已持久化）"""
        return self._schedule_task(task)

    def remove_task(self, task_id: int) -> None:
        """从调度器移除任务"""
        if self._scheduler:
            job_id = f"task_{task_id}"
            self._scheduler.remove_job(job_id)
            logger.info("移除定时任务: task_%d", task_id)

    def update_task(self, task: Task) -> str | None:
        """更新调度器中的任务"""
        self.remove_task(task.id)
        return self._schedule_task(task)

    def list_jobs(self) -> list[dict[str, Any]]:
        """列出当前调度器中的所有任务"""
        if not self._scheduler:
            return []
        jobs = self._scheduler.get_jobs()
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": str(job.next_run_time) if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
            for job in sorted(jobs, key=lambda j: j.next_run_time or datetime.max.replace(tzinfo=timezone.utc))
        ]


# 全局单例
scheduler = SchedulerEngine()
