"""Agent CLI 主入口"""

from __future__ import annotations

import sys

import typer

from kore.cli.commands.chat import chat_app
from kore.cli.commands.daemon import daemon_app
from kore.cli.commands.task import task_app
from kore.storage.db import init_db

app = typer.Typer(
    name="kore",
    help="kore - 自动化任务编排引擎",
    no_args_is_help=False,  # 不传参数时进入 REPL
    rich_markup_mode="rich",
)

app.add_typer(task_app, name="task", help="任务管理（创建/查看/执行/暂停/删除）")
app.add_typer(daemon_app, name="daemon", help="守护进程管理（启动/停止/状态）")
app.add_typer(chat_app, name="chat", help="AI 对话模式（可传入消息单次对话）")


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细日志输出"),
) -> None:
    """kore - 自动化任务编排引擎"""
    if verbose:
        import logging

        from kore.utils.logger import setup_logger

        setup_logger("agent").setLevel(logging.DEBUG)

    # 自动初始化数据库
    init_db()

    # 无参数 + 非管道输入 → 进入 REPL
    if ctx.invoked_subcommand is None and sys.stdin.isatty():
        from kore.cli.commands.chat import _repl_loop
        import asyncio
        asyncio.run(_repl_loop())
        raise typer.Exit()


if __name__ == "__main__":
    app()
