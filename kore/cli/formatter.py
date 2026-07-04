"""终端格式化输出

处理 Windows 控制台编码兼容性（GBK 无法显示部分 Unicode 符号）
"""

from __future__ import annotations

import sys
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from rich.panel import Panel
from rich import box

# 检测编码兼容性
_use_ascii = sys.stdout.encoding and sys.stdout.encoding.upper() in (
    "GBK", "GB2312", "GB18030", "CP936"
)

# 替换特殊字符
_CHK = "[green]OK[/green]" if _use_ascii else "[green]✓[/green]"
_ERR = "[red]X[/red]" if _use_ascii else "[red]✗[/red]"
_WARN = "[yellow]![/yellow]" if _use_ascii else "[yellow]⚠[/yellow]"
_INFO = "[cyan]i[/cyan]" if _use_ascii else "[cyan]ℹ[/cyan]"

console = Console()


def print_task_list(tasks: list[dict[str, Any]]) -> None:
    """打印任务列表表格"""
    if not tasks:
        console.print("[yellow]暂无任务[/yellow]")
        return

    table = Table(box=box.ROUNDED, header_style="bold cyan")
    table.add_column("ID", style="dim", width=4)
    table.add_column("名称", width=20)
    table.add_column("类型", width=10)
    table.add_column("调度", width=16)
    table.add_column("状态", width=8)
    table.add_column("最近执行", width=20)

    for t in tasks:
        status_style = {
            "active": "green",
            "paused": "yellow",
            "disabled": "red",
        }.get(t["status"], "white")

        table.add_row(
            str(t["id"]),
            t["name"],
            t["task_type"],
            t.get("schedule_expr", "") or "-",
            f"[{status_style}]{t['status']}[/{status_style}]",
            t.get("last_run", "") or "-",
        )

    console.print(table)


def print_task_detail(task: dict[str, Any], runs: list[dict[str, Any]] | None = None) -> None:
    """打印任务详情"""
    console.print()
    console.print(f"[bold]任务: {task['name']}[/bold]")
    console.print(f"  ID:      {task['id']}")
    console.print(f"  类型:    {task['task_type']}")
    console.print(f"  描述:    {task.get('description', '') or '-'}")
    console.print(f"  调度:    {task.get('schedule_expr', '') or '无'}")
    console.print(f"  超时:    {task.get('timeout', 300)}s")
    console.print(f"  状态:    {task['status']}")

    if task.get("config"):
        console.print()
        console.print(Panel(
            Syntax(str(task["config"]), "json", theme="monokai", word_wrap=True),
            title="配置",
            border_style="dim",
        ))

    if runs:
        console.print()
        table = Table(box=box.SIMPLE, header_style="bold")
        table.add_column("运行ID", width=6)
        table.add_column("状态", width=10)
        table.add_column("触发方式", width=10)
        table.add_column("开始时间", width=20)
        table.add_column("耗时(ms)", width=10)
        table.add_column("退出码", width=8)

        for r in runs:
            status_style = {
                "success": "green",
                "failed": "red",
                "running": "blue",
                "pending": "yellow",
                "timeout": "red",
                "cancelled": "dim",
            }.get(r["status"], "white")

            table.add_row(
                str(r["id"]),
                f"[{status_style}]{r['status']}[/{status_style}]",
                r.get("trigger", ""),
                r.get("started_at", "") or "-",
                str(r.get("duration_ms", "")) or "-",
                str(r.get("exit_code", "")) or "-",
            )

        console.print(table)


def print_run_detail(run: dict[str, Any]) -> None:
    """打印执行记录详情"""
    console.print()
    console.print(f"[bold]运行记录 #{run['id']}[/bold]")
    console.print(f"  任务:    {run.get('task_name', '')} (ID: {run['task_id']})")
    console.print(f"  状态:    {run['status']}")
    console.print(f"  触发:    {run.get('trigger', '')}")
    console.print(f"  开始:    {run.get('started_at', '')}")
    console.print(f"  结束:    {run.get('finished_at', '')}")
    console.print(f"  耗时:    {run.get('duration_ms', '')} ms")
    console.print(f"  退出码:  {run.get('exit_code', '')}")

    if run.get("stdout"):
        console.print()
        console.print(Panel(run["stdout"][:2000], title="stdout", border_style="green"))
    if run.get("stderr"):
        console.print()
        console.print(Panel(run["stderr"][:2000], title="stderr", border_style="red"))
    if run.get("error_message"):
        console.print()
        console.print(f"[red]错误: {run['error_message']}[/red]")


def print_jobs(jobs: list[dict[str, Any]]) -> None:
    """打印已调度的任务列表"""
    if not jobs:
        console.print("[yellow]调度器中没有任务[/yellow]")
        return

    table = Table(box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Job ID", width=16)
    table.add_column("名称", width=20)
    table.add_column("下次执行", width=24)
    table.add_column("触发器", width=20)

    for j in jobs:
        table.add_row(j["id"], j["name"], j["next_run_time"] or "-", j["trigger"])

    console.print(table)


def success(message: str) -> None:
    """打印成功消息"""
    console.print(f"{_CHK} {message}")


def error(message: str) -> None:
    """打印错误消息"""
    console.print(f"{_ERR} {message}")


def warning(message: str) -> None:
    """打印警告消息"""
    console.print(f"{_WARN} {message}")


def info(message: str) -> None:
    """打印信息消息"""
    console.print(f"{_INFO} {message}")
