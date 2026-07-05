"""Agent CLI 主入口"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from kore.cli.commands.chat import chat_app
from kore.cli.commands.daemon import daemon_app
from kore.cli.commands.task import task_app
from kore.cli.commands.web import web_app
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
app.add_typer(web_app, name="web", help="Web 管理界面（启动）")


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
        # 确保项目根目录在 sys.path 中（kore.exe 直接启动时不含项目目录）
        _project_root = Path(__file__).resolve().parent.parent.parent
        if str(_project_root) not in sys.path:
            sys.path.insert(0, str(_project_root))

        # 在进入 REPL 前自动启动 Web 服务（后台线程）
        from kore.utils.config import settings
        if settings.web_secret_key:
            import threading
            import uvicorn
            from web.app import create_app

            def _start_web() -> None:
                """在后台运行 Web 服务"""
                try:
                    app = create_app()
                    uvicorn.run(
                        app,
                        host=settings.web_host,
                        port=settings.web_port,
                        log_level="warning",
                    )
                except Exception:
                    pass  # Web 启动失败不影响 REPL

            web_thread = threading.Thread(target=_start_web, daemon=True)
            web_thread.start()
            # 给 Web 服务一点时间启动
            import time
            time.sleep(0.5)

        typer.echo(f"  Web 管理界面: http://{settings.web_host}:{settings.web_port}")

        from kore.cli.commands.chat import _repl_loop
        import asyncio
        asyncio.run(_repl_loop())
        raise typer.Exit()


if __name__ == "__main__":
    app()
