"""链式任务触发引擎 — 基于 EventBus 的事件驱动"""

from __future__ import annotations

import asyncio
from typing import Any

from kore.core.event_bus import event_bus
from kore.core.executor import execute_task
from kore.storage.db import get_sync_session
from kore.storage.models import RunStatus, TriggerCondition
from kore.storage.repository import TaskRepository
from kore.utils.logger import get_logger

logger = get_logger("trigger")


async def _on_task_completed(
    task_id: int,
    task_name: str,
    run_id: int,
    result: Any,
    **kwargs: Any,
) -> None:
    """任务完成后检查并触发下游链式任务"""
    success = result.success if hasattr(result, "success") else True

    with get_sync_session() as session:
        repo = TaskRepository(session)
        # 查找以当前任务为上游的链式任务
        tasks = repo.list_tasks(limit=500)
        child_tasks = [
            t for t in tasks
            if t.trigger_task_id == task_id and t.trigger_condition is not None
        ]

        for child in child_tasks:
            should_trigger = (
                child.trigger_condition == TriggerCondition.ALWAYS
                or (child.trigger_condition == TriggerCondition.SUCCESS and success)
                or (child.trigger_condition == TriggerCondition.FAILURE and not success)
            )

            if not should_trigger:
                logger.info(
                    "链式任务 %s 跳过（条件不满足: %s, 上游结果: %s）",
                    child.name, child.trigger_condition.value, "success" if success else "failure",
                )
                continue

            logger.info(
                "触发链式任务: %s (上游: %s → 条件: %s)",
                child.name, task_name, child.trigger_condition.value,
            )

            run = repo.create_run(task_id=child.id, trigger="chain")
            child_run_id = run.id

            try:
                child_result = await execute_task(child)

                status = RunStatus.SUCCESS if child_result.success else RunStatus.FAILED
                repo.update_run(
                    child_run_id,
                    status=status,
                    stdout=child_result.stdout or "",
                    stderr=child_result.stderr or "",
                    error_message=child_result.error_message or "",
                    exit_code=child_result.exit_code,
                )

                # 发布下游任务执行事件
                await event_bus.publish(
                    f"task.{'completed' if child_result.success else 'failed'}",
                    task_id=child.id,
                    task_name=child.name,
                    run_id=child_run_id,
                    result=child_result,
                )

                if child_result.success:
                    logger.info("链式任务 %s 执行成功", child.name)
                else:
                    logger.warning("链式任务 %s 执行失败: %s", child.name, child_result.error_message)

            except Exception as e:
                logger.error("链式任务 %s 执行异常: %s", child.name, e)
                repo.update_run(child_run_id, status=RunStatus.FAILED, error_message=str(e))


async def _on_task_failed(
    task_id: int,
    task_name: str,
    run_id: int,
    result: Any,
    **kwargs: Any,
) -> None:
    """任务失败时触发下游（复用 _on_task_completed 逻辑）"""
    await _on_task_completed(task_id, task_name, run_id, result)


def register_trigger_handlers() -> None:
    """注册链式触发事件处理器到 EventBus"""
    event_bus.subscribe("task.completed", _on_task_completed)
    event_bus.subscribe("task.failed", _on_task_completed)
    logger.info("链式触发引擎已注册")

    # 检查是否有循环依赖
    _check_circular_dependencies()


def _check_circular_dependencies() -> None:
    """检查链式任务是否有循环依赖"""
    with get_sync_session() as session:
        repo = TaskRepository(session)
        tasks = repo.list_tasks(limit=1000)

        # 在 session 内构建依赖图
        edges: dict[int, list[int]] = {}
        task_ids: set[int] = set()
        for t in tasks:
            task_ids.add(t.id)
            if t.trigger_task_id and t.trigger_condition:
                parent = t.trigger_task_id
                child = t.id
                edges.setdefault(parent, []).append(child)

    def has_cycle(current: int, visited: set[int], path: set[int]) -> bool:
        if current in path:
            return True
        if current in visited:
            return False
        visited.add(current)
        path.add(current)
        for child in edges.get(current, []):
            if has_cycle(child, visited, path):
                return True
        path.discard(current)
        return False

    visited: set[int] = set()
    for tid in task_ids:
        if tid not in visited:
            if has_cycle(tid, visited, set()):
                logger.warning("检测到链式任务循环依赖！可能导致无限触发")
                break
