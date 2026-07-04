"""任务管理命令"""

from __future__ import annotations

import json
import asyncio
from datetime import datetime
from typing import Any, Optional

import typer

from kore.cli.formatter import (
    error,
    info,
    print_run_detail,
    print_task_detail,
    print_task_list,
    success,
    warning,
)
from kore.core.scheduler import scheduler
from kore.storage.db import get_sync_session
from kore.storage.models import RunStatus, ScheduleType, TaskStatus, TaskType
from kore.storage.repository import TaskRepository
from kore.utils.logger import logger

task_app = typer.Typer(help="任务管理（创建/查看/执行/暂停/删除）")


def _task_to_dict(task: Any) -> dict[str, Any]:
    """将 ORM Task 转为纯字典（避免 detached session 问题）"""
    return {
        "id": task.id,
        "name": task.name,
        "task_type": task.task_type.value if hasattr(task.task_type, "value") else str(task.task_type),
        "description": task.description or "",
        "schedule_expr": task.schedule_expr or "",
        "schedule_type": task.schedule_type.value if task.schedule_type and hasattr(task.schedule_type, "value") else str(task.schedule_type) if task.schedule_type else "",
        "timeout": task.timeout,
        "status": task.status.value if hasattr(task.status, "value") else str(task.status),
        "tags": task.tags or "",
        "config": json.loads(task.config) if isinstance(task.config, str) else (task.config or {}),
        "created_at": task.created_at.isoformat() if hasattr(task, "created_at") and task.created_at else "",
    }


def _run_to_dict(run: Any, task_name: str = "") -> dict[str, Any]:
    """将 ORM TaskRun 转为纯字典"""
    return {
        "id": run.id,
        "task_id": run.task_id,
        "task_name": task_name,
        "status": run.status.value if hasattr(run.status, "value") else str(run.status),
        "trigger": run.trigger or "",
        "started_at": run.started_at.isoformat() if run.started_at else "",
        "finished_at": run.finished_at.isoformat() if run.finished_at else "",
        "duration_ms": run.duration_ms,
        "exit_code": run.exit_code,
        "stdout": run.stdout or "",
        "stderr": run.stderr or "",
        "error_message": run.error_message or "",
    }


@task_app.command("add")
def task_add(
    name: str = typer.Option(..., "--name", "-n", help="任务名称"),
    task_type: str = typer.Option(
        ..., "--type", "-t", help="任务类型: shell / python / http"
    ),
    command: Optional[str] = typer.Option(
        None, "--command", "-c", help="Shell 命令或 Python 代码"
    ),
    script_path: Optional[str] = typer.Option(
        None, "--script", "-s", help="Python 脚本路径"
    ),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="HTTP 请求 URL"),
    method: Optional[str] = typer.Option(
        "GET", "--method", "-m", help="HTTP 方法"
    ),
    description: str = typer.Option("", "--desc", "-d", help="任务描述"),
    schedule: Optional[str] = typer.Option(
        None, "--schedule", help="调度表达式: cron('0 9 * * *') / interval('300'或'5m') / date('2026-07-04 09:00')"
    ),
    schedule_type: Optional[str] = typer.Option(
        None, "--schedule-type", help="调度类型: cron / interval / date"
    ),
    timeout: int = typer.Option(300, "--timeout", help="超时时间（秒）"),
    tags: str = typer.Option("", "--tags", help="标签（逗号分隔）"),
) -> None:
    """添加新任务"""
    # 验证任务类型
    try:
        ttype = TaskType(task_type.lower())
    except ValueError:
        error(f"不支持的任务类型: {task_type}，可选: shell, python, http")
        raise typer.Exit(1)

    # 构建配置
    config: dict = {}
    if ttype == TaskType.SHELL:
        if not command:
            error("shell 类型需要 --command 参数")
            raise typer.Exit(1)
        config["command"] = command
    elif ttype == TaskType.PYTHON:
        if command:
            config["script"] = command
        elif script_path:
            config["script_path"] = script_path
        else:
            error("python 类型需要 --command（内联代码）或 --script（脚本路径）")
            raise typer.Exit(1)
    elif ttype == TaskType.HTTP:
        if not url:
            error("http 类型需要 --url 参数")
            raise typer.Exit(1)
        config["url"] = url
        config["method"] = method or "GET"

    # 处理调度
    sched_type: ScheduleType | None = None
    sched_expr: str | None = None
    if schedule:
        if schedule_type:
            try:
                sched_type = ScheduleType(schedule_type.lower())
            except ValueError:
                error(f"不支持的调度类型: {schedule_type}，可选: cron, interval, date")
                raise typer.Exit(1)
            sched_expr = schedule
        else:
            # 自动检测调度类型
            if " " in schedule and not schedule.replace(" ", "").isdigit():
                sched_type = ScheduleType.CRON
            elif any(schedule.endswith(suf) for suf in ("s", "m", "h", "d")):
                sched_type = ScheduleType.INTERVAL
            elif schedule.isdigit():
                sched_type = ScheduleType.INTERVAL
            else:
                try:
                    datetime.fromisoformat(schedule)
                    sched_type = ScheduleType.DATE
                except ValueError:
                    error(f"无法识别调度表达式: {schedule}")
                    raise typer.Exit(1)
            sched_expr = schedule

    # 持久化
    with get_sync_session() as session:
        repo = TaskRepository(session)
        try:
            task = repo.create_task(
                name=name,
                task_type=ttype,
                config=config,
                description=description,
                schedule_type=sched_type,
                schedule_expr=sched_expr,
                timeout=timeout,
                tags=tags,
            )
            task_id = task.id
            created_name = task.name
        except Exception as e:
            error(f"创建任务失败: {e}")
            raise typer.Exit(1)

    success(f"任务 '{created_name}' 已创建 (ID: {task_id})")


@task_app.command("list")
def task_list(
    status: Optional[str] = typer.Option(
        None, "--status", "-s", help="按状态筛选: active / paused / disabled"
    ),
    task_type: Optional[str] = typer.Option(
        None, "--type", "-t", help="按类型筛选: shell / python / http"
    ),
    limit: int = typer.Option(100, "--limit", "-l", help="最大返回数量"),
) -> None:
    """列出所有任务"""
    t_status = TaskStatus(status) if status else None
    t_type = TaskType(task_type) if task_type else None

    with get_sync_session() as session:
        repo = TaskRepository(session)
        tasks = repo.list_tasks(status=t_status, task_type=t_type, limit=limit)

        task_dicts = []
        for t in tasks:
            runs = repo.get_task_runs(t.id, limit=1)
            last_run = runs[0].started_at.isoformat() if runs else ""
            d = _task_to_dict(t)
            d["last_run"] = last_run
            task_dicts.append(d)

    print_task_list(task_dicts)


@task_app.command("get")
def task_get(
    task_id: int = typer.Argument(..., help="任务 ID"),
    runs: bool = typer.Option(False, "--runs", "-r", help="显示执行记录"),
    run_limit: int = typer.Option(5, "--run-limit", help="执行记录数量"),
) -> None:
    """查看任务详情"""
    with get_sync_session() as session:
        repo = TaskRepository(session)
        task = repo.get_task(task_id)
        if not task:
            error(f"任务 #{task_id} 不存在")
            raise typer.Exit(1)
        task_dict = _task_to_dict(task)

        run_dicts = None
        if runs:
            run_list = repo.get_task_runs(task_id, limit=run_limit)
            run_dicts = [_run_to_dict(r) for r in run_list]

    print_task_detail(task_dict, run_dicts)


@task_app.command("run")
def task_run(
    task_id: int = typer.Argument(..., help="任务 ID"),
) -> None:
    """立即执行任务"""
    from kore.core.executor import execute_task

    # 在 session 内获取任务数据和创建运行记录
    with get_sync_session() as session:
        repo = TaskRepository(session)
        task = repo.get_task(task_id)
        if not task:
            error(f"任务 #{task_id} 不存在")
            raise typer.Exit(1)
        task_dict = _task_to_dict(task)
        task_run_obj = repo.create_run(task_id=task_id, trigger="manual")
        run_id = task_run_obj.id

    info(f"开始执行任务 '{task_dict['name']}'...")

    # 异步执行（在 session 内创建 ORM 对象后，异步环境需重新查询）
    async def run_and_save():
        from kore.core.executor import execute_task

        # 在异步环境中重新查询 ORM 对象
        with get_sync_session() as session:
            repo = TaskRepository(session)
            task_obj = repo.get_task(task_id)
            if not task_obj:
                logger.error("任务 %d 不存在（异步执行时）", task_id)
                return None

            try:
                result = await execute_task(task_obj)
                repo = TaskRepository(session)
                repo.update_run(
                    run_id=run_id,
                    status=RunStatus.SUCCESS if result.success else RunStatus.FAILED,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.exit_code,
                    error_message=result.error_message,
                )
                return result
            except Exception as e:
                logger.error("任务执行异常: %s", e)
                repo = TaskRepository(session)
                repo.update_run(
                    run_id=run_id,
                    status=RunStatus.FAILED,
                    error_message=str(e),
                )
                raise

    result = asyncio.run(run_and_save())

    if result.success:
        success(f"任务 '{task_dict['name']}' 执行成功")
        if result.stdout:
            print(result.stdout)
    else:
        error(f"任务 '{task_dict['name']}' 执行失败")
        if result.stderr:
            print(result.stderr)


@task_app.command("pause")
def task_pause(
    task_id: int = typer.Argument(..., help="任务 ID"),
) -> None:
    """暂停任务"""
    with get_sync_session() as session:
        repo = TaskRepository(session)
        task = repo.set_task_status(task_id, TaskStatus.PAUSED)
        if not task:
            error(f"任务 #{task_id} 不存在")
            raise typer.Exit(1)
        task_name = task.name

    scheduler.remove_task(task_id)
    warning(f"任务 '{task_name}' 已暂停")


@task_app.command("resume")
def task_resume(
    task_id: int = typer.Argument(..., help="任务 ID"),
) -> None:
    """恢复暂停的任务"""
    with get_sync_session() as session:
        repo = TaskRepository(session)
        task = repo.set_task_status(task_id, TaskStatus.ACTIVE)
        if not task:
            error(f"任务 #{task_id} 不存在")
            raise typer.Exit(1)
        task_dict = _task_to_dict(task)

    success(f"任务 '{task_dict['name']}' 已恢复")


@task_app.command("delete")
def task_delete(
    task_id: int = typer.Argument(..., help="任务 ID"),
    force: bool = typer.Option(False, "--force", "-f", help="强制删除，不确认"),
) -> None:
    """删除任务"""
    if not force:
        warning(f"确认删除任务 #{task_id}？使用 --force 确认")
        raise typer.Exit(1)

    with get_sync_session() as session:
        repo = TaskRepository(session)
        deleted = repo.delete_task(task_id)

    if not deleted:
        error(f"任务 #{task_id} 不存在")
        raise typer.Exit(1)

    scheduler.remove_task(task_id)
    success(f"任务 #{task_id} 已删除")


@task_app.command("logs")
def task_logs(
    task_id: int = typer.Argument(..., help="任务 ID"),
    limit: int = typer.Option(20, "--limit", "-l", help="显示条数"),
    run_id: Optional[int] = typer.Option(None, "--run-id", help="查看指定运行记录"),
) -> None:
    """查看任务执行日志"""
    with get_sync_session() as session:
        repo = TaskRepository(session)

        if run_id:
            from kore.storage.models import TaskRun as TR
            run_obj = session.get(TR, run_id)
            if not run_obj:
                error(f"运行记录 #{run_id} 不存在")
                raise typer.Exit(1)
            task_obj = repo.get_task(run_obj.task_id)
            task_name = task_obj.name if task_obj else ""
            runs_data = [_run_to_dict(run_obj, task_name)]
        else:
            task_obj = repo.get_task(task_id)
            if not task_obj:
                error(f"任务 #{task_id} 不存在")
                raise typer.Exit(1)
            task_name = task_obj.name
            run_objs = repo.get_task_runs(task_id, limit=limit)
            runs_data = [_run_to_dict(r, task_name) for r in run_objs]

    for r_data in runs_data:
        print_run_detail(r_data)
