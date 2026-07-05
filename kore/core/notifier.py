"""多通道通知器 — 任务执行结果通知"""

from __future__ import annotations

import json
import smtplib
from email.mime.text import MIMEText
from typing import Any

import httpx

from kore.core.event_bus import event_bus
from kore.storage.db import get_sync_session
from kore.storage.models import NotifyChannelType, Notification
from kore.utils.logger import get_logger

logger = get_logger("notifier")

try:
    from plyer import notification as plyer_notification
    HAS_PLYER = True
except ImportError:
    HAS_PLYER = False


def _load_channels(channel_ids: str) -> list[Notification]:
    """加载通知渠道配置"""
    if not channel_ids.strip():
        return []
    ids = []
    for part in channel_ids.split(","):
        part = part.strip()
        try:
            ids.append(int(part))
        except ValueError:
            continue
    if not ids:
        return []

    with get_sync_session() as session:
        from sqlalchemy import select
        stmt = select(Notification).where(Notification.id.in_(ids), Notification.enabled == True)
        return list(session.scalars(stmt).all())


async def _send_webhook(
    url: str,
    method: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> None:
    """发送 Webhook 通知"""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15)) as client:
            resp = await client.request(method=method, url=url, headers=headers, json=payload)
            resp.raise_for_status()
        logger.info("Webhook %s → %s", url, resp.status_code)
    except Exception as e:
        logger.warning("Webhook 发送失败 %s: %s", url, e)


def _send_email(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    email_from: str,
    email_to: str,
    subject: str,
    body: str,
) -> None:
    """发送 Email 通知"""
    if not smtp_host or not email_to:
        return
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = email_from or smtp_user
        msg["To"] = email_to
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            if smtp_user:
                server.login(smtp_user, smtp_password)
            server.send_message(msg)
        logger.info("邮件通知 → %s", email_to)
    except Exception as e:
        logger.warning("邮件发送失败: %s", e)


def _send_desktop(title: str, message: str) -> None:
    """发送桌面通知"""
    if not HAS_PLYER:
        return
    try:
        plyer_notification.notify(title=title, message=message, timeout=5)
    except Exception as e:
        logger.debug("桌面通知失败: %s", e)


async def _notify_handler(
    task_id: int,
    task_name: str,
    run_id: int,
    result: Any,
    **kwargs: Any,
) -> None:
    """事件处理器：任务执行后发送通知"""
    success = result.success if hasattr(result, "success") else True
    status_text = "成功" if success else "失败"

    with get_sync_session() as session:
        from kore.storage.repository import TaskRepository
        repo = TaskRepository(session)
        task = repo.get_task(task_id)
        if not task:
            return

        # 检查是否需要发送通知
        should_notify = (
            (success and task.notify_on_success)
            or (not success and task.notify_on_failure)
        )
        if not should_notify:
            return

        channels = _load_channels(task.notify_channel_ids)
        if not channels:
            return

        # 构建通知内容
        subject = f"[kore] 任务「{task_name}」执行{status_text}"
        body = (
            f"任务: {task_name}\n"
            f"状态: {status_text}\n"
            f"运行 ID: {run_id}\n"
            f"时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        )
        if hasattr(result, "error_message") and result.error_message:
            body += f"错误: {result.error_message}\n"

        payload = {
            "event": "task_run",
            "task_id": task_id,
            "task_name": task_name,
            "run_id": run_id,
            "status": status_text,
        }

        # 按渠道发送
        for ch in channels:
            if ch.channel == NotifyChannelType.WEBHOOK and ch.webhook_url:
                headers = {}
                try:
                    headers = json.loads(ch.webhook_headers) if ch.webhook_headers else {}
                except (json.JSONDecodeError, TypeError):
                    headers = {}
                await _send_webhook(ch.webhook_url, ch.webhook_method, headers, payload)

            elif ch.channel == NotifyChannelType.EMAIL and ch.smtp_host:
                _send_email(
                    ch.smtp_host,
                    ch.smtp_port or 587,
                    ch.smtp_user,
                    ch.smtp_password,
                    ch.email_from or ch.smtp_user,
                    ch.email_to,
                    subject,
                    body,
                )

            elif ch.channel == NotifyChannelType.DESKTOP:
                _send_desktop(subject, body[:200])


def register_notify_handlers() -> None:
    """注册通知事件处理器到 EventBus"""
    event_bus.subscribe("task.completed", _notify_handler)
    event_bus.subscribe("task.failed", _notify_handler)
    logger.info("通知系统已注册")
