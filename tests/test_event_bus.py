"""事件总线测试"""

from __future__ import annotations

import pytest


class TestEventBus:
    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self) -> None:
        """测试订阅和发布"""
        from kore.core.event_bus import EventBus

        bus = EventBus()
        received = []

        async def handler(**data):
            received.append(data)

        bus.subscribe("test.event", handler)
        await bus.publish("test.event", message="hello")

        assert len(received) == 1
        assert received[0]["message"] == "hello"

    @pytest.mark.asyncio
    async def test_multiple_handlers(self) -> None:
        """测试多个处理器"""
        from kore.core.event_bus import EventBus

        bus = EventBus()
        results = []

        async def h1(**data):
            results.append("h1")

        async def h2(**data):
            results.append("h2")

        bus.subscribe("evt", h1)
        bus.subscribe("evt", h2)
        await bus.publish("evt")

        assert len(results) == 2
        assert "h1" in results
        assert "h2" in results

    @pytest.mark.asyncio
    async def test_handler_error_does_not_block(self) -> None:
        """测试处理器异常不会阻止其他处理器"""
        from kore.core.event_bus import EventBus

        bus = EventBus()
        results = []

        async def bad_handler(**data):
            raise ValueError("handler error")

        async def good_handler(**data):
            results.append("ok")

        bus.subscribe("evt", bad_handler)
        bus.subscribe("evt", good_handler)
        await bus.publish("evt")

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe(self) -> None:
        """测试取消订阅"""
        from kore.core.event_bus import EventBus

        bus = EventBus()
        results = []

        async def handler(**data):
            results.append(True)

        bus.subscribe("evt", handler)
        bus.unsubscribe("evt", handler)
        await bus.publish("evt")

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_no_handlers(self) -> None:
        """测试无处理器的主题"""
        from kore.core.event_bus import EventBus

        bus = EventBus()
        await bus.publish("nonexistent")  # 不应抛出异常

    def test_clear(self) -> None:
        """测试清空"""
        from kore.core.event_bus import EventBus

        bus = EventBus()

        async def handler(**data):
            pass

        bus.subscribe("evt", handler)
        bus.clear()
        assert len(bus._handlers) == 0
