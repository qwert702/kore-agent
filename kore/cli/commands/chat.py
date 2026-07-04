"""Chat 命令 - 交互式对话 + 单次对话"""

from __future__ import annotations

import asyncio
import sys
from typing import Optional

import typer

from kore.cli.formatter import error, info, success, warning
from kore.llm.chat import run_chat_stream
from kore.utils.logger import get_logger

logger = get_logger("cli.chat")

chat_app = typer.Typer(
    name="chat",
    help="与 kore AI 助手对话（输入 kore 无参数进入 REPL）",
    no_args_is_help=False,
)


@chat_app.callback(invoke_without_command=True)
def chat_callback(
    ctx: typer.Context,
    message: Optional[str] = typer.Argument(
        None, help="单次对话消息。不传则进入交互式 REPL"
    ),
) -> None:
    """与 kore AI 助手对话"""
    if message:
        # 单次模式
        asyncio.run(_single_chat(message))
    elif not sys.stdin.isatty():
        # 管道输入模式
        pipe_input = sys.stdin.read().strip()
        if pipe_input:
            asyncio.run(_single_chat(pipe_input))
        else:
            _show_help()
    else:
        # REPL 模式
        asyncio.run(_repl_loop())


def _show_help() -> None:
    """显示 REPL 帮助信息"""
    help_text = """
kore - AI 助手模式

可用命令:
  /help    显示此帮助
  /exit    退出 (或 Ctrl+C, 或输入 exit/quit)
  /clear   清屏
  /tools   列出可用工具
  /status  查看系统状态

直接输入问题与我对话，例如:
  "列出所有任务"
  "帮我创建一个每天备份的 shell 任务"
  "查看任务 1 的执行日志"
"""
    print(help_text)


async def _single_chat(message: str) -> None:
    """单次对话"""
    try:
        reply, _ = await run_chat_stream(message, single_shot=True)
    except Exception as e:
        error(f"对话失败: {e}")
        logger.error("Chat error: %s", e)


async def _repl_loop() -> None:
    """交互式 REPL 循环"""
    history: list = []
    _started = False

    print("\n* kore AI 助手已启动！输入 /help 查看帮助，/exit 退出。\n")

    while True:
        try:
            # 输入
            if sys.platform == "win32" and sys.stdout.encoding.upper() in (
                "GBK", "GB2312", "GB18030", "CP936"
            ):
                user_input = input("kore> ")
            else:
                user_input = input("kore> ")

            if not user_input.strip():
                continue

            cmd = user_input.strip().lower()

            # 内部命令
            if cmd in ("/exit", "/quit", "exit", "quit"):
                print("再见！\n")
                break
            elif cmd == "/help":
                _show_help()
                continue
            elif cmd == "/clear":
                import os
                os.system("cls" if sys.platform == "win32" else "clear")
                continue
            elif cmd == "/tools":
                from kore.llm.tools import TOOLS
                print("\n可用工具:")
                for t in TOOLS:
                    fn = t["function"]
                    print(f"  • {fn['name']} - {fn['description']}")
                print()
                continue
            elif cmd == "/status":
                from kore.llm.tool_handlers import call_tool
                result = await call_tool("daemon_status", {})
                print(f"\n{result}\n")
                continue

            # AI 对话
            try:
                reply, history = await run_chat_stream(user_input, history=history)
                # 流式输出已在 run_chat_stream 中完成，这里不再打印
            except UnicodeEncodeError:
                reply, history = await run_chat_stream(user_input, history=history)
            except Exception as e:
                error(f"对话错误: {e}")
                logger.error("REPL error: %s", e, exc_info=True)
                continue

        except KeyboardInterrupt:
            print("\n\n再见！\n")
            break
        except Exception as e:
            error(f"对话错误: {e}")
            logger.error("REPL error: %s", e, exc_info=True)
            continue
