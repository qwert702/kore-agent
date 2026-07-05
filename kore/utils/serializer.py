"""任务序列化 — YAML/JSON 导入导出"""

from __future__ import annotations

import json
from typing import Any

import yaml

from kore.storage.repository import TaskRepository


class TaskSerializer:
    """任务序列化工具"""

    EXPORT_FIELDS = [
        "name", "description", "task_type", "config",
        "schedule_type", "schedule_expr", "timeout",
        "tags", "trigger_condition", "trigger_task_id",
    ]

    @staticmethod
    def serialize(data: list[dict[str, Any]], fmt: str = "yaml") -> str:
        """序列化为 YAML 或 JSON"""
        if fmt == "json":
            return json.dumps(data, ensure_ascii=False, indent=2, default=str)
        return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)

    @staticmethod
    def deserialize(content: str, fmt: str = "yaml") -> list[dict[str, Any]]:
        """从 YAML 或 JSON 反序列化"""
        if fmt == "json":
            data = json.loads(content)
        else:
            data = yaml.safe_load(content)
        if isinstance(data, dict):
            data = [data]
        return data

    @staticmethod
    def export_tasks(
        repo: TaskRepository,
        task_ids: list[int] | None = None,
        fmt: str = "yaml",
    ) -> str:
        """导出任务为可移植格式"""
        if task_ids:
            tasks = []
            for tid in task_ids:
                t = repo.get_task(tid)
                if t:
                    tasks.append(t)
        else:
            tasks = repo.list_tasks(limit=5000)

        result = []
        for t in tasks:
            d = {}
            for field in TaskSerializer.EXPORT_FIELDS:
                val = getattr(t, field, None)
                if val is not None and val != "":
                    if field == "config" and isinstance(val, str):
                        try:
                            val = json.loads(val)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    if field == "tags" and isinstance(val, str):
                        val = [tag.strip() for tag in val.split(",") if tag.strip()]
                    d[field] = val

            # Enum → 字符串
            for key in ("task_type", "schedule_type", "trigger_condition"):
                if key in d and hasattr(d[key], "value"):
                    d[key] = d[key].value

            result.append(d)

        return TaskSerializer.serialize(result, fmt)

    @staticmethod
    def import_tasks(
        repo: TaskRepository,
        content: str,
        fmt: str = "yaml",
        override: bool = False,
    ) -> list[str]:
        """从文件导入任务，返回导入的任务名列表"""
        data = TaskSerializer.deserialize(content, fmt)
        imported = []

        for item in data:
            name = item.get("name", "").strip()
            if not name:
                continue

            # 检查重名
            existing = repo.get_task_by_name(name)
            if existing:
                if override:
                    repo.delete_task(existing.id)
                else:
                    continue

            task_type_str = item.get("task_type", "shell")
            config = item.get("config", {})
            description = item.get("description", "")
            schedule_type_str = item.get("schedule_type")
            schedule_expr = item.get("schedule_expr")
            timeout = item.get("timeout", 300)
            tags = item.get("tags", [])
            if isinstance(tags, list):
                tags = ",".join(tags)

            # 调度类型字符串 → Enum
            st = None
            if schedule_type_str and schedule_type_str in ("cron", "interval", "date"):
                from kore.storage.models import ScheduleType
                st = ScheduleType(schedule_type_str)

            repo.create_task(
                name=name,
                task_type=task_type_str,
                config=config if isinstance(config, dict) else {},
                description=description,
                schedule_type=st,
                schedule_expr=schedule_expr,
                timeout=timeout,
                tags=tags,
                trigger_condition=item.get("trigger_condition"),
                trigger_task_id=None,  # 导入时不保留 internal ID
            )
            imported.append(name)

        return imported
