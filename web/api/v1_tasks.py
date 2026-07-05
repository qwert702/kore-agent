"""API v1 - 任务管理"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette.responses import JSONResponse

from kore.storage.db import get_sync_session
from kore.storage.models import ScheduleType, TaskStatus, TaskType
from kore.storage.repository import TaskRepository
from web.auth import require_api_token

router = APIRouter(tags=["tasks"])


def _task_json(t: object) -> dict[str, Any]:
    """Task ORM → JSON dict"""
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "task_type": t.task_type.value if hasattr(t.task_type, "value") else t.task_type,
        "config": json.loads(t.config) if isinstance(t.config, str) else t.config,
        "status": t.status.value if hasattr(t.status, "value") else t.status,
        "schedule_type": t.schedule_type.value if t.schedule_type and hasattr(t.schedule_type, "value") else t.schedule_type,
        "schedule_expr": t.schedule_expr or None,
        "schedule_timezone": t.schedule_timezone,
        "timeout": t.timeout,
        "tags": t.tags.split(",") if t.tags else [],
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


@router.get("/tasks", dependencies=[Depends(require_api_token)])
async def api_task_list(
    status: str | None = Query(None),
    task_type: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> JSONResponse:
    """获取任务列表"""
    st = TaskStatus(status) if status and status in ("active", "paused", "disabled") else None
    tt = TaskType(task_type) if task_type and task_type in ("shell", "http", "python", "file_ops", "notify", "workflow") else None

    with get_sync_session() as session:
        repo = TaskRepository(session)
        tasks = repo.list_tasks(status=st, task_type=tt, offset=offset, limit=limit)

    return JSONResponse({"tasks": [_task_json(t) for t in tasks], "total": len(tasks)})


@router.post("/tasks", dependencies=[Depends(require_api_token)])
async def api_task_create(request: Request) -> JSONResponse:
    """创建任务"""
    body = await request.json()
    name = body.get("name", "").strip()
    task_type_str = body.get("task_type", "")

    if not name:
        return JSONResponse({"detail": "Name is required"}, status_code=400)
    if task_type_str not in ("shell", "http", "python"):
        return JSONResponse({"detail": f"Unsupported task type: {task_type_str}"}, status_code=400)

    config = body.get("config", {})
    description = body.get("description", "")
    schedule_type_str = body.get("schedule_type")
    schedule_expr = body.get("schedule_expr")
    timeout = body.get("timeout", 300)
    tags = ",".join(body.get("tags", [])) if isinstance(body.get("tags"), list) else body.get("tags", "")

    st = None
    if schedule_type_str and schedule_type_str in ("cron", "interval", "date"):
        st = ScheduleType(schedule_type_str)

    if not isinstance(timeout, int) or timeout < 1:
        return JSONResponse({"detail": "Timeout must be a positive integer"}, status_code=400)

    with get_sync_session() as session:
        repo = TaskRepository(session)
        task = repo.create_task(
            name=name,
            task_type=TaskType(task_type_str),
            config=config,
            description=description,
            schedule_type=st,
            schedule_expr=schedule_expr,
            timeout=timeout,
            tags=tags,
        )
        task_id = task.id

    return JSONResponse({"task": _task_json(task)}, status_code=201)


@router.get("/tasks/{task_id}", dependencies=[Depends(require_api_token)])
async def api_task_get(task_id: int) -> JSONResponse:
    """获取任务详情"""
    with get_sync_session() as session:
        repo = TaskRepository(session)
        task = repo.get_task(task_id)
        if not task:
            return JSONResponse({"detail": "Task not found"}, status_code=404)

    return JSONResponse({"task": _task_json(task)})


@router.put("/tasks/{task_id}", dependencies=[Depends(require_api_token)])
async def api_task_update(task_id: int, request: Request) -> JSONResponse:
    """更新任务"""
    body = await request.json()
    allowed = {"name", "description", "config", "schedule_type", "schedule_expr",
               "schedule_timezone", "timeout", "tags"}
    kwargs = {k: v for k, v in body.items() if k in allowed}

    if "tags" in kwargs and isinstance(kwargs["tags"], list):
        kwargs["tags"] = ",".join(kwargs["tags"])
    if "config" in kwargs and isinstance(kwargs["config"], dict):
        kwargs["config"] = json.dumps(kwargs["config"], ensure_ascii=False)
    if "schedule_type" in kwargs and kwargs["schedule_type"]:
        kwargs["schedule_type"] = ScheduleType(kwargs["schedule_type"])
    if "timeout" in kwargs:
        kwargs["timeout"] = int(kwargs["timeout"])

    with get_sync_session() as session:
        repo = TaskRepository(session)
        task = repo.update_task(task_id, **kwargs)
        if not task:
            return JSONResponse({"detail": "Task not found"}, status_code=404)

    return JSONResponse({"task": _task_json(task)})


@router.delete("/tasks/{task_id}", dependencies=[Depends(require_api_token)])
async def api_task_delete(task_id: int) -> JSONResponse:
    """删除任务"""
    with get_sync_session() as session:
        repo = TaskRepository(session)
        if not repo.delete_task(task_id):
            return JSONResponse({"detail": "Task not found"}, status_code=404)

    return JSONResponse({"detail": "Deleted"})


@router.post("/tasks/{task_id}/run", dependencies=[Depends(require_api_token)])
async def api_task_run(task_id: int) -> JSONResponse:
    """触发任务执行"""
    import asyncio

    from kore.core.executor import execute_task
    from kore.storage.models import RunStatus

    with get_sync_session() as session:
        repo = TaskRepository(session)
        task = repo.get_task(task_id)
        if not task:
            return JSONResponse({"detail": "Task not found"}, status_code=404)

        run = repo.create_run(task_id=task_id, trigger="api")
        run_id = run.id

    async def _run_and_save():
        try:
            result = await execute_task(task)
            with get_sync_session() as session:
                repo2 = TaskRepository(session)
                repo2.update_run(
                    run_id,
                    status=RunStatus.SUCCESS if result.success else RunStatus.FAILED,
                    stdout=result.stdout or "",
                    stderr=result.stderr or "",
                    error_message=result.error_message or "",
                    exit_code=result.exit_code,
                )
        except Exception as e:
            with get_sync_session() as session:
                repo2 = TaskRepository(session)
                repo2.update_run(run_id, status=RunStatus.FAILED, error_message=str(e))

    asyncio.ensure_future(_run_and_save())
    return JSONResponse({"run_id": run_id, "status": "pending"})
