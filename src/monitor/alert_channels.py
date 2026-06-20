"""告警外部通道（Phase 5）。

把 AlertManager 产生的结构化告警派发到外部通道（webhook / 邮件）。

设计要点：
- 通道按级别过滤（min_level），避免低级别刷屏。
- 实际发送函数可注入（post_fn / send_fn），默认用标准库（urllib / smtplib），
  不新增第三方依赖；测试可注入假函数，不触网络/SMTP。
- 通道发送失败由 AlertManager 隔离（见 alert_manager._dispatch），不影响主流程。
"""

import json
import smtplib
import time as _time
import urllib.request
from abc import ABC, abstractmethod
from email.message import EmailMessage
from typing import Callable, List, Optional

from src.monitor.alert_manager import INFO, WARNING, CRITICAL
from src.utils.logger import logger


# 级别排序：用于 min_level 过滤
_LEVEL_ORDER = {INFO: 0, WARNING: 1, CRITICAL: 2}


class AlertChannel(ABC):
    """告警通道基类。"""

    def __init__(self, min_level: str = WARNING):
        """
        参数：
            min_level: 最低发送级别，低于此级别的告警不发送（默认 WARNING）
        """
        if min_level not in _LEVEL_ORDER:
            raise ValueError(f"Invalid min_level: {min_level}")
        self.min_level = min_level

    def should_send(self, level: str) -> bool:
        """级别达到阈值才发送。"""
        return _LEVEL_ORDER.get(level, 0) >= _LEVEL_ORDER[self.min_level]

    @abstractmethod
    def send(self, alert: dict) -> None:
        """发送一条告警（失败应抛异常，由调用方隔离）。"""
        ...


def _default_post(url: str, payload: dict, timeout: float) -> None:
    """默认 webhook 发送：urllib POST JSON，含指数退避重试。"""
    data = json.dumps(payload).encode("utf-8")
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=timeout)
            break
        except Exception as e:
            if attempt < 2:
                _time.sleep(2 ** attempt)
            else:
                logger.error(f"Webhook failed after 3 attempts: {e}")


class WebhookChannel(AlertChannel):
    """Webhook 通道（POST JSON）。可对接 Telegram bot / Slack / 自建 endpoint。"""

    def __init__(
        self,
        url: str,
        min_level: str = WARNING,
        timeout: float = 5.0,
        post_fn: Optional[Callable[[str, dict, float], None]] = None,
    ):
        super().__init__(min_level)
        self.url = url
        self.timeout = timeout
        self._post = post_fn or _default_post

    def send(self, alert: dict) -> None:
        self._post(self.url, alert, self.timeout)


def _default_smtp_send(msg: EmailMessage, smtp_config: dict) -> None:
    """默认邮件发送：smtplib。"""
    host = smtp_config["host"]
    port = smtp_config.get("port", 587)
    with smtplib.SMTP(host, port, timeout=smtp_config.get("timeout", 10)) as smtp:
        if smtp_config.get("use_tls", True):
            smtp.starttls()
        user = smtp_config.get("username")
        password = smtp_config.get("password")
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)


class EmailChannel(AlertChannel):
    """邮件通道。默认只发 CRITICAL（邮件不适合刷屏）。"""

    def __init__(
        self,
        smtp_config: dict,
        from_addr: str,
        to_addrs: List[str],
        min_level: str = CRITICAL,
        send_fn: Optional[Callable[[EmailMessage, dict], None]] = None,
    ):
        """
        参数：
            smtp_config: {host, port, username, password, use_tls, timeout}
            from_addr: 发件地址
            to_addrs: 收件地址列表
            min_level: 默认 CRITICAL
            send_fn: 可注入发送函数（测试用），默认 smtplib
        """
        super().__init__(min_level)
        self.smtp_config = smtp_config
        self.from_addr = from_addr
        self.to_addrs = to_addrs
        self._send = send_fn or _default_smtp_send

    def send(self, alert: dict) -> None:
        msg = EmailMessage()
        msg["Subject"] = f"[{alert['level']}] {alert['source']}"
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(self.to_addrs)
        msg.set_content(
            f"Time: {alert['time']}\n"
            f"Level: {alert['level']}\n"
            f"Source: {alert['source']}\n"
            f"Message: {alert['message']}\n"
        )
        self._send(msg, self.smtp_config)


__all__ = ["AlertChannel", "WebhookChannel", "EmailChannel"]
