"""CLI Web 命令"""

from __future__ import annotations

import typer

web_app = typer.Typer(help="Web 管理界面（启动）")


@web_app.command("start")
def web_start(
    host: str = typer.Option("127.0.0.1", "--host", "-H", help="监听地址"),
    port: int = typer.Option(18081, "--port", "-p", help="监听端口"),
    reload: bool = typer.Option(False, "--reload", "-r", help="热重载（开发模式）"),
) -> None:
    """启动 Web 管理界面"""
    import uvicorn

    typer.echo(f"启动 Kore Web 管理界面: http://{host}:{port}")
    typer.echo("按 Ctrl+C 停止")
    typer.echo()

    uvicorn.run(
        "web.app:create_app",
        host=host,
        port=port,
        factory=True,
        reload=reload,
    )
