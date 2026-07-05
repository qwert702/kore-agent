"""对话循环引擎 - REPL 交互 + 工具调用 + 流式输出"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Any

from openai.types.chat import ChatCompletionMessageToolCall

from kore.llm.client import get_client, get_model, check_available
from kore.llm.tool_handlers import call_tool
from kore.llm.tools import TOOLS
from kore.utils.config import settings
from kore.utils.logger import get_logger

logger = get_logger("chat")


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
- **file_write** - 在 generated/ 目录下创建代码文件（Python 游戏、Shell 脚本、HTML 页面等）
- **bash_run** - 在终端执行一条命令（适合运行 python game.py、pip install 等）

## 关于代码生成

你可以使用 `file_write` 工具直接生成代码文件到 `generated/` 目录，然后用 `bash_run` 执行它们。例如用户说"做一个 FPS 游戏"：

1. 用 `file_write` 写一个 Python 游戏文件（用 ursina/pygame/pyglet/panda3d 等库）
2. 用 `bash_run` 安装依赖并运行
3. 把游戏文件路径和运行结果告诉用户

**注意**：你不需要预先安装任何东西，直接写代码然后 `pip install` 即可。生成的代码存放在 `generated/` 目录下。

## 行为准则

1. **自然语言优先**：用清晰的中文回复，不要列出 raw JSON
2. **工具调用优先**：用户需要操作时，主动调用工具而非给指令
3. **确认关键操作**：删除任务前请确认用户意图；有多个任务 ID 时确认是哪个
4. **解释结果**：执行完任务后，用一句话总结做了什么
5. **保持简洁**：不要啰嗦，用 Markdown 格式清晰呈现
6. **失败处理**：工具调用失败时，给用户可以理解的错误提示
"""


# ── 工具描述映射（用于终端展示）──
_TOOL_DESCRIPTIONS: dict[str, str] = {
    "task_list": "获取任务列表",
    "task_add": "创建新任务",
    "task_get": "查看任务详情",
    "task_run": "执行任务",
    "task_pause": "暂停任务",
    "task_resume": "恢复任务",
    "task_delete": "删除任务",
    "task_logs": "查看执行日志",
    "daemon_status": "检查守护进程状态",
    "file_write": "创建代码文件",
    "bash_run": "执行命令",
}


def _show_tool_call(name: str, args: dict[str, Any]) -> None:
    """显示工具调用的详细描述（类 Claude Code 风格）"""
    desc = _TOOL_DESCRIPTIONS.get(name, name)

    if name == "file_write":
        filename = args.get("filename", "untitled")
        print(f"\n  > 创建文件: {filename}", flush=True)
    elif name == "bash_run":
        cmd = args.get("command", "")
        print(f"\n  > 执行: {cmd}", flush=True)
    elif name == "task_add":
        task_name = args.get("name", "")
        task_type = args.get("task_type", "")
        print(f"\n  > {desc}: [{task_type}] {task_name}", flush=True)
    elif name == "task_run":
        tid = args.get("task_id", "")
        print(f"\n  > {desc}: #{tid}", flush=True)
    elif name == "task_get":
        tid = args.get("task_id", "")
        print(f"\n  > {desc}: #{tid}", flush=True)
    elif name == "task_logs":
        tid = args.get("task_id", "")
        print(f"\n  > {desc}: #{tid}", flush=True)
    elif name == "task_delete":
        tid = args.get("task_id", "")
        print(f"\n  > {desc}: #{tid}", flush=True)
    else:
        print(f"\n  > {desc}...", flush=True)


def _show_tool_result(name: str, result_text: str) -> None:
    """显示工具执行结果的摘要"""
    # 取第一行作为摘要
    first_line = result_text.split("\n")[0][:80]
    if first_line.startswith("[OK]"):
        print(f"  [OK] {first_line[5:]}", flush=True)
    elif first_line.startswith("[X]"):
        print(f"  [X] {first_line[5:]}", flush=True)
    elif first_line.startswith("[-]") or first_line.startswith("[||]") or first_line.startswith(">"):
        pass  # 这些已经有标记
    else:
        if len(result_text) < 120:
            print(f"  -> {result_text}", flush=True)


def _show_file_preview(filename: str, content: str) -> None:
    """显示文件内容预览（前 8 行）"""
    lines = content.split("\n")
    preview_lines = lines[:8]
    print(f"  │ {'─' * 40}", flush=True)
    for line in preview_lines:
        _safe_print(f"  │ {line}\n")
    if len(lines) > 8:
        print(f"  │ ... ({len(lines)} 行总)", flush=True)
    print(f"  │ {'─' * 40}", flush=True)


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

    # ── 思考阶段 ──
    print("\n   思考中...", flush=True)

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
    except Exception:
        raise

    # 清除思考行
    print("\r" + " " * 50 + "\r", end="", flush=True)

    message = response.choices[0].message

    # --- 流式输出辅助函数 ---
    async def _stream_response(messages: list[dict]) -> str:
        """流式输出并返回完整文本"""
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
                    if first_chunk:
                        first_chunk = False
                        _safe_print("  ")
                    full_text += content
                    _safe_print(content.replace("\n", "\n  "))

            return full_text
        except Exception:
            raise

    if message.tool_calls:
        # ── 执行工具调用 ──
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

            # 显示工具调用（claude code 风格）
            _show_tool_call(name, args)

            # 如果是 file_write，先显示文件内容预览
            if name == "file_write":
                content = args.get("content", "")
                _show_file_preview(args.get("filename", ""), content)

            # 如果是 bash_run，显示命令
            elif name == "bash_run":
                cmd = args.get("command", "")
                print(f"  $ {cmd}", flush=True)

            result_text = await call_tool(name, args)

            # 显示工具结果
            _show_tool_result(name, result_text)

            # bash_run 显示完整输出
            if name == "bash_run":
                # 跳过第一行（摘要），显示详细输出
                lines = result_text.split("\n")
                if len(lines) > 1:
                    for line in lines[1:]:
                        if line.strip():
                            print(f"  {line}", flush=True)

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
