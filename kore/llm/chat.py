"""对话循环引擎 - REPL 交互 + 工具调用 + 流式输出"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from typing import Any


def _safe_print(text: str) -> None:
    """安全打印，兼容 Windows GBK 控制台"""
    try:
        print(text, end="", flush=True)
    except UnicodeEncodeError:
        safe = text.encode("gbk", errors="replace").decode("gbk", errors="replace")
        print(safe, end="", flush=True)


def _safe_println(text: str) -> None:
    """安全换行打印"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        safe = text.encode("gbk", errors="replace").decode("gbk", errors="replace")
        print(safe, flush=True)


class SpiderSpinner:
    """蜘蛛加载动画 - 在另一个线程中运行的跳动蜘蛛

    使用 GBK 兼容的 ASCII 字符，帧动画让蜘蛛在"织网"。
    启动后会在终端显示：  [o O o O]  蜘蛛思考中...
    """

    def __init__(self, text: str = " 蜘蛛思考中") -> None:
        self._text = text
        self._running = False
        self._thread: threading.Thread | None = None
        # GBK 安全的动画帧：蜘蛛八条腿交替
        self._frames = [
            r"  [\/] ",
            r"  [O]  ",
            r"  [/\] ",
            r"  [o]  ",
        ]
        self._idx = 0

    def _animate(self) -> None:
        """后台动画循环"""
        while self._running:
            frame = self._frames[self._idx % len(self._frames)]
            line = f"\r{frame} {self._text}"
            # GBK 安全写入
            try:
                print(line, end="", flush=True)
            except UnicodeEncodeError:
                safe = line.encode("gbk", errors="replace").decode("gbk", errors="replace")
                print(safe, end="", flush=True)
            self._idx += 1
            time.sleep(0.25)

    def start(self) -> None:
        """启动动画"""
        self._running = True
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止动画并清除行"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.5)
        # 清除当前行
        print("\r" + " " * 50 + "\r", end="", flush=True)

from openai.types.chat import ChatCompletionMessageToolCall

from kore.llm.client import get_client, get_model, check_available
from kore.llm.tool_handlers import call_tool
from kore.llm.tools import TOOLS
from kore.utils.config import settings
from kore.utils.logger import get_logger

logger = get_logger("chat")


# ── 身份问题硬拦截 ──────────────────────────────────────────
_KORE_IDENTITY = (
    "我是 **kore**，你的自动化任务 AI 助手，由 CBN 开发。\n\n"
    "我可以帮你管理自动化任务：创建定时任务、执行 Shell 脚本、HTTP 请求、Python 脚本……"
    "直接告诉我你想做什么就行！"
)

_IDENTITY_KEYWORDS = [
    "你是谁", "你叫什么", "你是什么", "介绍你自己",
    "who are you", "what are you", "what's your name",
    "tell me about yourself",
]


def _is_identity_question(text: str) -> bool:
    """检测是否为身份相关问题"""
    t = text.strip().lower().translate(str.maketrans("", "", "!?，。？、；：""''"))
    return any(kw in t for kw in _IDENTITY_KEYWORDS)


def _replace_identity(text: str) -> str:
    """后处理：替换回答中泄露的底层模型身份"""
    text = text.replace("DeepSeek", "kore")
    text = text.replace("deepseek", "kore")
    text = text.replace("深度求索", "CBN")
    text = text.replace("深度求索公司", "CBN")
    text = text.replace("由深度求索公司创造", "由 CBN 开发")
    text = text.replace("免费使用", "免费使用")
    return text


# System prompt
SYSTEM_PROMPT = """你叫 kore，是一个强大的自动化任务 AI 助手。

## 你的能力

你可以通过自然语言帮助用户管理自动化任务。用户的终端上运行着 kore 引擎，你可以调用内置工具来执行操作。

## 可用工具

- **task_list** - 列出所有任务（可按状态/类型筛选）
- **task_add** - 创建新任务（shell/HTTP/Python）
- **task_get** - 查看任务详情
- **task_run** - 立即执行任务
- **task_pause/resume** - 暂停/恢复定时任务
- **task_delete** - 删除任务
- **task_logs** - 查看执行日志
- **daemon_status** - 查看守护进程状态

## 行为准则

1. **自然语言优先**：用清晰的中文回复，不要列出 raw JSON
2. **工具调用优先**：用户需要操作时，主动调用工具而非给指令
3. **确认关键操作**：删除任务前请确认用户意图；有多个任务 ID 时确认是哪个
4. **解释结果**：执行完任务后，用一句话总结做了什么
5. **保持简洁**：不要啰嗦，用 Markdown 格式清晰呈现
6. **失败处理**：工具调用失败时，给用户可以理解的错误提示
"""


async def run_chat(
    user_input: str,
    history: list[dict[str, Any]] | None = None,
    single_shot: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    """执行一次对话（可能是多轮工具调用）

    Returns:
        (最终回复文本, 更新后的历史消息)
    """
    if history is None:
        history = [{"role": "system", "content": SYSTEM_PROMPT}]

    # ── 身份问题硬拦截 ──
    if _is_identity_question(user_input):
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": _KORE_IDENTITY})
        return _KORE_IDENTITY, history

    history.append({"role": "user", "content": user_input})

    # 裁剪历史（保留 system 消息）
    max_history = settings.llm_max_history
    if len(history) > max_history + 1:  # +1 是 system
        history = [history[0]] + history[-(max_history):]

    client = get_client()
    model = get_model()

    # 第一轮：可能返回工具调用
    response = client.chat.completions.create(
        model=model,
        messages=history,
        tools=TOOLS,
        tool_choice="auto",
        temperature=0.3,
        max_tokens=2048,
    )

    message = response.choices[0].message

    if message.tool_calls:
        # --- 处理工具调用 ---
        history.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ],
        })

        # 逐个执行工具
        for tc in message.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            result_text = await call_tool(name, args)

            history.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_text,
            })

        # 第二轮：把工具结果交给 LLM 生成自然语言回复
        final_response = client.chat.completions.create(
            model=model,
            messages=history,
            temperature=0.3,
            max_tokens=2048,
        )

        final_message = final_response.choices[0].message
        reply = _replace_identity(final_message.content or "")
        history.append({"role": "assistant", "content": reply})

        return reply, history

    else:
        # 纯文本回复
        reply = _replace_identity(message.content or "")
        history.append({"role": "assistant", "content": reply})
        return reply, history


async def run_chat_stream(
    user_input: str,
    history: list[dict[str, Any]] | None = None,
    single_shot: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    """流式对话 - 逐字输出回复，支持工具调用

    Returns:
        (完整回复文本, 更新后的历史消息)
    """
    if history is None:
        history = [{"role": "system", "content": SYSTEM_PROMPT}]

    # ── 身份问题硬拦截 ──
    if _is_identity_question(user_input):
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": _KORE_IDENTITY})
        # 保持对话风格缩进
        _safe_print("\n  ")
        _safe_print(_KORE_IDENTITY.replace("\n", "\n  "))
        print()
        return _KORE_IDENTITY, history

    history.append({"role": "user", "content": user_input})

    # 裁剪历史
    max_history = settings.llm_max_history
    if len(history) > max_history + 1:
        history = [history[0]] + history[-(max_history):]

    client = get_client()
    model = get_model()

    # 启动蜘蛛加载动画
    spinner = SpiderSpinner()
    spinner.start()

    # --- 非流式第一轮（工具调用必须用非流式）---
    try:
        response = client.chat.completions.create(
            model=model,
            messages=history,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.3,
            max_tokens=2048,
        )
    finally:
        spinner.stop()

    message = response.choices[0].message

    # --- 流式输出辅助函数 ---
    async def _stream_response(messages: list[dict]) -> str:
        """流式输出并返回完整文本"""
        spinner = SpiderSpinner(" 蜘蛛打字中...")
        spinner.start()
        try:
            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.3,
                max_tokens=2048,
                stream=True,
            )

            full_text = ""
            first_chunk = True
            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    content = delta.content
                    # 第一个字符时关闭动画并添加缩进
                    if first_chunk:
                        spinner.stop()
                        first_chunk = False
                        _safe_print("  ")
                    full_text += content
                    # 换行时自动续上缩进（对话风格）
                    _safe_print(content.replace("\n", "\n  "))

            # 如果全空也关闭
            if first_chunk:
                spinner.stop()
            return full_text
        except Exception:
            spinner.stop()
            raise

    if message.tool_calls:
        # 显示工具调用提示
        for tc in message.tool_calls:
            fn_name = tc.function.name
            fn_desc = {
                "task_list": "获取任务列表",
                "task_add": "创建任务",
                "task_get": "查看任务详情",
                "task_run": "执行任务",
                "task_delete": "删除任务",
                "task_pause": "暂停任务",
                "task_resume": "恢复任务",
                "task_logs": "查看执行日志",
                "daemon_status": "检查守护进程状态",
            }.get(fn_name, fn_name)
            print(f"\n  > {fn_desc}...", flush=True)

        # 保存 assistant 消息（含 tool_calls）
        history.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ],
        })

        # 执行工具
        for tc in message.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            result_text = await call_tool(name, args)

            history.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_text,
            })

        # 流式输出最终回复
        print("\n", flush=True)
        reply = _replace_identity(await _stream_response(history))
        print()
        history.append({"role": "assistant", "content": reply})
        return reply, history

    else:
        # 直接流式输出
        reply = _replace_identity(await _stream_response(history))
        print()
        history.append({"role": "assistant", "content": reply})
        return reply, history
