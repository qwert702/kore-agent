"""事件总线 - 解耦组件间通信"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Awaitable, Callable

from kore.utils.logger import get_logger

logger = get_logger("event_bus")

EventHandler = Callable[..., Awaitable[None]]


class EventBus:
    """基于主题的异步事件总线"""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._running = False

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        """订阅事件

        Args:
            topic: 事件主题（如 "task.completed"、"task.failed"）
            handler: 异步处理函数
        """
        self._handlers[topic].append(handler)
        logger.debug("订阅事件: %s -> %s", topic, handler.__name__)

    def unsubscribe(self, topic: str, handler: EventHandler) -> None:
        """取消订阅"""
        if topic in self._handlers:
            self._handlers[topic].remove(handler)
            logger.debug("取消订阅: %s -> %s", topic, handler.__name__)

    async def publish(self, topic: str, **data: Any) -> None:
        """发布事件

        Args:
            topic: 事件主题
            data: 事件数据
        """
        handlers = self._handlers.get(topic, [])
        if not handlers:
            return

        logger.debug("发布事件: %s (data=%s, handlers=%d)", topic, data, len(handlers))
        results = await asyncio.gather(
            *[handler(**data) for handler in handlers],
            return_exceptions=True,
        )
        for handler, result in zip(handlers, results):
            if isinstance(result, Exception):
                logger.error(
                    "事件处理器 %s 异常: %s", handler.__name__, result
                )

    def clear(self) -> None:
        """清空所有订阅"""
        self._handlers.clear()
        logger.debug("事件总线已清空")


# 全局单例
event_bus = EventBus()
