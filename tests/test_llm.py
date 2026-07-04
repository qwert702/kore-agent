"""AI 对话模块测试"""

from __future__ import annotations

import pytest


class TestToolHandlers:
    """工具处理器测试"""

    @pytest.mark.asyncio
    async def test_call_unknown_tool(self) -> None:
        """测试调用未知工具"""
        from kore.llm.tool_handlers import call_tool

        result = await call_tool("nonexistent_tool", {})
        assert "未知工具" in result

    @pytest.mark.asyncio
    async def test_task_list_no_tasks(self) -> None:
        """测试空任务列表"""
        from kore.llm.tool_handlers import call_tool

        result = await call_tool("task_list", {})
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_task_get_not_found(self) -> None:
        """测试获取不存在的任务"""
        from kore.llm.tool_handlers import call_tool

        result = await call_tool("task_get", {"task_id": 99999})
        assert "不存在" in result

    @pytest.mark.asyncio
    async def test_task_delete_not_found(self) -> None:
        """测试删除不存在的任务"""
        from kore.llm.tool_handlers import call_tool

        result = await call_tool("task_delete", {"task_id": 99999})
        assert "不存在" in result

    @pytest.mark.asyncio
    async def test_daemon_status(self) -> None:
        """测试守护进程状态"""
        from kore.llm.tool_handlers import call_tool

        result = await call_tool("daemon_status", {})
        assert isinstance(result, str)


class TestTools:
    """工具定义测试"""

    def test_tools_list(self) -> None:
        """测试工具定义完整性"""
        from kore.llm.tools import TOOLS

        assert len(TOOLS) > 0
        names = [t["function"]["name"] for t in TOOLS]
        assert "task_list" in names
        assert "task_add" in names
        assert "task_get" in names
        assert "task_run" in names
        assert "task_pause" in names
        assert "task_resume" in names
        assert "task_delete" in names
        assert "task_logs" in names
        assert "daemon_status" in names

    def test_tool_handler_registry(self) -> None:
        """测试所有工具都有对应的处理器"""
        from kore.llm.tools import TOOLS
        from kore.llm.tool_handlers import get_handler

        for t in TOOLS:
            name = t["function"]["name"]
            assert get_handler(name) is not None, f"工具 {name} 缺少处理器"


class TestClient:
    """LLM 客户端测试"""

    def test_client_import(self) -> None:
        """测试客户端模块可导入"""
        from kore.llm.client import get_client, get_model
        # 只要有正确导入就通过，实际初始化需要 API Key
        assert callable(get_client)
        assert callable(get_model)
