"""守护进程管理命令"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

import typer

from kore.cli.formatter import error, info, success, warning
from kore.core.scheduler import scheduler
from kore.storage.db import init_db
from kore.utils.config import settings
from kore.utils.logger import logger

daemon_app = typer.Typer(help="守护进程管理（启动/停止/状态）")


@daemon_app.command("start")
def daemon_start(
    detach: bool = typer.Option(False, "--detach", "-d", help="后台运行"),
    port: int = typer.Option(18080, "--port", "-p", help="内部通信端口"),
) -> None:
    """启动 agent 守护进程"""
    if detach:
        warning("Windows 后台模式需要额外配置，当前暂以前台模式运行")
        info("使用 --detach 仅在 Linux/macOS 有效")
        info("Windows 建议使用: start /B kore daemon start")

    info(f"启动 Agent 守护进程 (PID: {os.getpid()})...")

    # 保存 PID
    pid_path = Path(settings.daemon_pid_file)
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()))

    # 初始化数据库
    init_db()
    info("数据库初始化完成")

    # 使用统一的事件循环运行整个守护进程
    async def run_daemon():
        await scheduler.start()
        info(f"Agent 守护进程正在运行 (端口: {port})")
        info("按 Ctrl+C 停止")

        # Windows 上通过 asyncio.Event 等待退出信号
        stop_event = asyncio.Event()

        def _signal_handler():
            asyncio.ensure_future(_shutdown_async(stop_event))

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop = asyncio.get_running_loop()
                loop.add_signal_handler(sig, _signal_handler)
            except NotImplementedError:
                pass

        await stop_event.wait()

    try:
        asyncio.run(run_daemon())
    except KeyboardInterrupt:
        asyncio.run(_shutdown_async(asyncio.Event()))


async def _shutdown_async(stop_event: asyncio.Event) -> None:
    """优雅关闭"""
    info("正在停止守护进程...")
    await scheduler.stop()
    pid_path = Path(settings.daemon_pid_file)
    if pid_path.exists():
        pid_path.unlink()
    success("守护进程已停止")
    stop_event.set()


@daemon_app.command("stop")
def daemon_stop() -> None:
    """停止守护进程"""
    pid_path = Path(settings.daemon_pid_file)
    if not pid_path.exists():
        error("守护进程未运行（PID 文件不存在）")
        raise typer.Exit(1)

    pid = int(pid_path.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        success(f"已发送停止信号给 PID {pid}")
    except ProcessLookupError:
        error(f"PID {pid} 不存在，清理 PID 文件")
        pid_path.unlink()
    except OSError as e:
        error(f"停止失败: {e}")
        raise typer.Exit(1)


@daemon_app.command("status")
def daemon_status() -> None:
    """查看守护进程状态"""
    pid_path = Path(settings.daemon_pid_file)

    if not pid_path.exists():
        warning("守护进程未运行")
        return

    pid = int(pid_path.read_text().strip())

    # 检查进程是否存在
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x0400 | 0x0010, 0, pid)
            if handle:
                kernel32.CloseHandle(handle)
                success(f"守护进程正在运行 (PID: {pid})")
            else:
                error(f"守护进程已停止 (残留 PID 文件: {pid})")
                pid_path.unlink()
        except Exception:
            info(f"PID 文件存在 (PID: {pid})，无法在 Windows 上检查进程状态")
    else:
        try:
            os.kill(pid, 0)
            success(f"守护进程正在运行 (PID: {pid})")
        except OSError:
            error(f"守护进程已停止 (残留 PID 文件: {pid})")
            pid_path.unlink()

    # 显示调度器状态
    if scheduler.is_running:
        jobs = scheduler.list_jobs()
        info(f"调度器: 运行中 | {len(jobs)} 个定时任务")
    else:
        info("调度器: 未启动（APScheduler 未安装或守护进程未运行）")
