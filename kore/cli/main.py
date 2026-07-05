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
    no_args_is_help=False,
    rich_markup_mode="rich",
)

app.add_typer(task_app, name="task", help="任务管理（创建/查看/执行/暂停/删除）")
app.add_typer(daemon_app, name="daemon", help="守护进程管理（启动/停止/状态）")
app.add_typer(chat_app, name="chat", help="AI 对话模式（可传入消息单次对话）")
app.add_typer(web_app, name="web", help="Web 管理界面（启动）")


def _show_banner(web_url: str = "") -> None:
    """显示酷炫的 ASCII 启动界面"""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box
    from rich.layout import Layout

    console = Console()

    logo_lines = (
        "[bold cyan]"
        ".-----------------------------------------------.\n"
        "|     _  __   ___   ____   _____   _   _  _____  |\n"
        "|    | |/ /  / _ \ |  _ \ | ____| | \ | ||_   _| |\n"
        "|    | ' /  | |_| || |_) ||  _|   |  \| |  | |   |\n"
        "|    | . \  |  __/ |  _ < | |___  | |\  |  | |   |\n"
        "|    |_|\_\ \___| |_| \_\|_____| |_| \_|  |_|   |\n"
        "'-----------------------------------------------'"
        "[/bold cyan]"
    )

    from kore.utils.config import settings
    info_lines = (
        f"  [bold]Version[/]      v0.2.0\n"
        f"  [bold]Database[/]     {settings.data_dir / 'agent.db'}\n"
        f"  [bold]Daemon Port[/]  {settings.daemon_port}\n"
    )
    if web_url:
        info_lines += f"  [bold]Web UI[/]        [green]{web_url}[/green]\n"

    panel = Panel(
        f"{logo_lines}\n\n{info_lines}",
        box=box.ROUNDED,
        border_style="cyan",
        title="[bold]kore[/bold]",
        width=58,
    )
    console.print(panel)


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
        from kore.utils.logger import set_console_silent

        # 静默日志控制台输出
        set_console_silent(True)

        # 确保项目根目录在 sys.path 中
        _project_root = Path(__file__).resolve().parent.parent.parent
        if str(_project_root) not in sys.path:
            sys.path.insert(0, str(_project_root))

        web_url = ""
        from kore.utils.config import settings
        if settings.web_secret_key:
            import threading
            import uvicorn
            from web.app import create_app

            def _start_web() -> None:
                try:
                    app = create_app()
                    uvicorn.run(
                        app,
                        host=settings.web_host,
                        port=settings.web_port,
                        log_level="error",
                    )
                except Exception:
                    pass

            web_thread = threading.Thread(target=_start_web, daemon=True)
            web_thread.start()
            import time
            time.sleep(0.8)
            web_url = f"http://{settings.web_host}:{settings.web_port}"

        # 显示酷炫启动面板
        _show_banner(web_url)

        from kore.cli.commands.chat import _repl_loop
        import asyncio
        asyncio.run(_repl_loop())
        raise typer.Exit()


if __name__ == "__main__":
    app()
