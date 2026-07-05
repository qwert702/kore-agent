"""工具执行器 - 把 LLM 函数调用映射到 kore 的操作"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Callable, Coroutine

from kore.core.executor import execute_task
from kore.storage.db import get_sync_session
from kore.storage.models import (
    RunStatus,
    ScheduleType,
    TaskStatus as TaskStatusEnum,
    TaskType,
)
from kore.storage.repository import TaskRepository
from kore.utils.logger import get_logger

logger = get_logger("tool_handlers")

HandlerFn = Callable[..., Coroutine[Any, Any, str]]


# --- 工具处理器注册表 ---

_handlers: dict[str, HandlerFn] = {}


def register(name: str) -> Callable[[HandlerFn], HandlerFn]:
    """装饰器：注册一个工具处理器"""
    def decorator(fn: HandlerFn) -> HandlerFn:
        _handlers[name] = fn
        return fn
    return decorator


def get_handler(name: str) -> HandlerFn | None:
    return _handlers.get(name)


async def call_tool(name: str, args: dict[str, Any]) -> str:
    """调用工具，异常安全"""
    handler = get_handler(name)
    if handler is None:
        return f"错误：未知工具 '{name}'"
    try:
        return await handler(**args)
    except Exception as e:
        logger.error("工具调用失败: %s args=%s: %s", name, args, e)
        return f"工具 '{name}' 执行失败: {e}"


def _task_to_row(t: Any) -> str:
    """把 ORM Task 转成一行文本（在 session 内调用）"""
    sched = t.schedule_expr or "-"
    return f"{t.id:<4} {t.name:<20} {t.task_type.value:<8} {sched:<14} {t.status.value:<8}"


def _task_to_dict(t: Any) -> dict:
    """在 session 内提取 Task 字段"""
    return {
        "id": t.id,
        "name": t.name,
        "task_type": t.task_type.value,
        "description": t.description or "",
        "schedule_expr": t.schedule_expr or "",
        "timeout": t.timeout,
        "status": t.status.value,
        "tags": t.tags or "",
        "config": t.config or "",
    }


# --- 工具处理器实现 ---


@register("file_write")
async def handle_file_write(filename: str, content: str, description: str = "") -> str:
    """在 generated/ 目录下写入文件"""
    from kore.utils.config import settings

    generated_dir = settings.project_root / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)

    # 路径安全校验：防止目录遍历
    safe_name = Path(filename).name  # 只取文件名，忽略路径
    filepath = generated_dir / safe_name

    # 只在 generated/ 目录下写
    if not str(filepath.resolve()).startswith(str(generated_dir.resolve())):
        return f"错误：只能在 generated/ 目录下写入文件"

    try:
        file_content = content
        if description:
            ext = Path(safe_name).suffix
            comment_char = "#" if ext in (".py", ".sh", ".yaml", ".yml") else "//"
            file_content = f"{comment_char} {description}\n{content}"

        filepath.write_text(file_content, encoding="utf-8")
        return f"[OK] 文件已创建: generated/{safe_name} ({filepath.stat().st_size} 字节)\n{description}"
    except Exception as e:
        return f"写入文件失败: {e}"


@register("bash_run")
async def handle_bash_run(command: str, timeout: int = 30) -> str:
    """执行一条 bash 命令"""
    # 安全黑名单
    dangerous = [
        "rm -rf /", "rm -rf /*", "mkfs", "dd if=", "> /dev/sda",
        ":(){ :|:& };:", "chmod -R 000 /", "wget", "curl",
    ]
    for d in dangerous:
        if d in command.lower():
            return f"错误：禁止执行危险命令"

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(Path(__file__).resolve().parent.parent.parent),
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        out = stdout.decode("utf-8", errors="replace")[:2000]
        err = stderr.decode("utf-8", errors="replace")[:2000]

        result = f"返回码: {proc.returncode}"
        if out:
            result += f"\n\n标准输出:\n```\n{out}\n```"
        if err:
            result += f"\n\n标准错误:\n```\n{err}\n```"
        return result
    except asyncio.TimeoutError:
        return f"命令执行超时（{timeout}秒）"
    except Exception as e:
        return f"命令执行失败: {e}"


@register("task_list")
async def handle_task_list(status: str = "", task_type: str = "") -> str:
    with get_sync_session() as session:
        repo = TaskRepository(session)
        t_status = TaskStatusEnum(status) if status else None
        t_type = TaskType(task_type) if task_type else None
        tasks = repo.list_tasks(status=t_status, task_type=t_type)

        if not tasks:
            return "暂无任务。"

        lines = ["## 任务列表\n"]
        lines.append(f"{'ID':<4} {'名称':<20} {'类型':<8} {'调度':<14} {'状态':<8}")
        lines.append("-" * 60)
        for t in tasks:
            lines.append(_task_to_row(t))
        return "\n".join(lines)


@register("task_add")
async def handle_task_add(
    name: str,
    task_type: str,
    command: str = "",
    url: str = "",
    method: str = "GET",
    description: str = "",
    schedule: str = "",
    timeout: int = 300,
    tags: str = "",
) -> str:
    ttype = TaskType(task_type)
    config: dict[str, Any] = {}

    if ttype == TaskType.SHELL:
        if not command:
            return "错误：shell 类型需要提供 command 参数"
        config["command"] = command
    elif ttype == TaskType.PYTHON:
        if not command:
            return "错误：python 类型需要提供 command（内联 Python 代码）"
        config["script"] = command
    elif ttype == TaskType.HTTP:
        if not url:
            return "错误：http 类型需要提供 url 参数"
        config["url"] = url
        config["method"] = method

    # 处理调度
    sched_type = None
    sched_expr = None
    if schedule:
        if " " in schedule and not schedule.replace(" ", "").isdigit():
            sched_type = ScheduleType.CRON
        elif any(schedule.endswith(suf) for suf in ("s", "m", "h", "d")):
            sched_type = ScheduleType.INTERVAL
        elif schedule.isdigit():
            sched_type = ScheduleType.INTERVAL
        else:
            sched_type = ScheduleType.DATE
        sched_expr = schedule

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
        except Exception as e:
            return f"创建任务失败: {e}"

    parts = [f"[OK] 任务 **{name}** 已创建 (ID: {task_id})"]
    parts.append(f"  类型: {task_type}")
    if sched_expr:
        parts.append(f"  调度: {sched_expr} ({sched_type.value if sched_type else ''})")
    return "\n".join(parts)


@register("task_get")
async def handle_task_get(task_id: int) -> str:
    with get_sync_session() as session:
        repo = TaskRepository(session)
        task = repo.get_task(task_id)

        if not task:
            return f"[X] 任务 #{task_id} 不存在"

        d = _task_to_dict(task)

        lines = [f"## 任务: {d['name']} (ID: {d['id']})\n"]
        lines.append(f"  **类型**: {d['task_type']}")
        lines.append(f"  **描述**: {d['description'] or '-'}")
        lines.append(f"  **调度**: {d['schedule_expr'] or '无'}")
        lines.append(f"  **超时**: {d['timeout']}s")
        lines.append(f"  **状态**: {d['status']}")
        lines.append(f"  **标签**: {d['tags'] or '-'}")

        # 最近执行（在 session 内读取）
        runs = repo.get_task_runs(task_id, limit=3)
        if runs:
            lines.append(f"\n  **最近执行**:")
            for r in runs:
                status_icon = "[OK]" if r.status == RunStatus.SUCCESS else "[X]"
                ts = r.started_at.strftime("%Y-%m-%d %H:%M:%S") if r.started_at else ""
                lines.append(f"    {status_icon} #{r.id} {r.status.value} ({r.duration_ms}ms) {ts}")

    return "\n".join(lines)


@register("task_run")
async def handle_task_run(task_id: int) -> str:
    # 先在 session 获取任务数据
    with get_sync_session() as session:
        repo = TaskRepository(session)
        task = repo.get_task(task_id)
        if not task:
            return f"[X] 任务 #{task_id} 不存在"
        task_run = repo.create_run(task_id=task_id, trigger="manual")
        run_id = task_run.id
        task_name = task.name

    # 异步执行
    try:
        result = await execute_task(task)
        with get_sync_session() as session:
            repo = TaskRepository(session)
            repo.update_run(
                run_id=run_id,
                status=RunStatus.SUCCESS if result.success else RunStatus.FAILED,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.exit_code,
                error_message=result.error_message,
            )
    except Exception as e:
        with get_sync_session() as session:
            repo = TaskRepository(session)
            repo.update_run(run_id=run_id, status=RunStatus.FAILED, error_message=str(e))
        return f"[X] 任务 '{task_name}' 执行异常: {e}"

    if result.success:
        text = f"[OK] 任务 **{task_name}** 执行成功！"
        if result.stdout:
            text += f"\n\n输出:\n```\n{result.stdout[:1000]}\n```"
        return text
    else:
        text = f"[X] 任务 **{task_name}** 执行失败"
        if result.stderr:
            text += f"\n\n错误:\n```\n{result.stderr[:1000]}\n```"
        return text


@register("task_pause")
async def handle_task_pause(task_id: int) -> str:
    with get_sync_session() as session:
        repo = TaskRepository(session)
        task = repo.set_task_status(task_id, TaskStatusEnum.PAUSED)
        if not task:
            return f"[X] 任务 #{task_id} 不存在"
        task_name = task.name
    return f"[||] 任务 **{task_name}** 已暂停"


@register("task_resume")
async def handle_task_resume(task_id: int) -> str:
    with get_sync_session() as session:
        repo = TaskRepository(session)
        task = repo.set_task_status(task_id, TaskStatusEnum.ACTIVE)
        if not task:
            return f"[X] 任务 #{task_id} 不存在"
        task_name = task.name
    return f">️ 任务 **{task_name}** 已恢复"


@register("task_delete")
async def handle_task_delete(task_id: int) -> str:
    with get_sync_session() as session:
        repo = TaskRepository(session)
        deleted = repo.delete_task(task_id)
    if not deleted:
        return f"[X] 任务 #{task_id} 不存在"
    return f"[-] 任务 #{task_id} 已删除"


@register("task_logs")
async def handle_task_logs(task_id: int, limit: int = 5) -> str:
    with get_sync_session() as session:
        repo = TaskRepository(session)
        task = repo.get_task(task_id)
        if not task:
            return f"[X] 任务 #{task_id} 不存在"
        task_name = task.name
        runs = repo.get_task_runs(task_id, limit=limit)

        if not runs:
            return f"任务 **{task_name}** 暂无执行记录"

        lines = [f"## {task_name} - 最近 {len(runs)} 条执行记录\n"]
        for r in runs:
            status_icon = {
                RunStatus.SUCCESS: "[OK]", RunStatus.FAILED: "[X]",
                RunStatus.TIMEOUT: "[!]", RunStatus.RUNNING: "[*]",
                RunStatus.PENDING: "[~]", RunStatus.CANCELLED: "[-]",
            }.get(r.status, "❓")
            trigger_label = "manual" if r.trigger == "manual" else "[!] schedule"
            lines.append(f"{status_icon} **#{r.id}** [{r.status.value}] {trigger_label}")
            if r.started_at:
                started = r.started_at.strftime("%Y-%m-%d %H:%M:%S")
                lines.append(f"  开始: {started}")
            if r.duration_ms is not None:
                lines.append(f"  耗时: {r.duration_ms}ms")
            if r.exit_code is not None:
                lines.append(f"  退出码: {r.exit_code}")
            if r.stdout:
                lines.append(f"  输出: {r.stdout[:200].replace(chr(10), ' ')}")
            if r.error_message:
                lines.append(f"  错误: {r.error_message}")
            lines.append("")

    return "\n".join(lines)


@register("daemon_status")
async def handle_daemon_status() -> str:
    from kore.core.scheduler import scheduler

    running = scheduler.is_running
    if running:
        jobs = scheduler.list_jobs()
        return (
            f"[OK] 守护进程运行中\n"
            f"  调度器: 正常\n"
            f"  定时任务数: {len(jobs)}"
        )
    else:
        return "[i] 守护进程未启动（任务可通过 `kore task run <id>` 手动执行）"
