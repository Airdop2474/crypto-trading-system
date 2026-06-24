"""
Telegram 通知模块

特性：
- 异步发送，不阻塞交易主循环
- 3 级通知：CRITICAL / WARNING / INFO
- 用户可配置接收级别
- 无 Bot Token 时自动降级为纯日志
- 发送失败不重试，避免堆积

用法：
    from src.utils.telegram_notifier import notifier

    # 发送通知
    await notifier.send_critical("止损触发: RSI 策略亏损 -2.5%")
    await notifier.send_warning("日亏损达 1.5%")
    await notifier.send_info("RSI 策略开仓 BTC/USDT")

    # 同步发送（在非 async 上下文中）
    notifier.send_critical_sync("daemon 崩溃")

    # 配置接收级别
    notifier.set_min_level("WARNING")  # 只接收 WARNING 和 CRITICAL
"""

import asyncio
import os
import threading
from enum import IntEnum
from typing import Optional

import httpx
from loguru import logger

from src.utils.config import config as _cfg


class NotificationLevel(IntEnum):
    """通知级别，数值越大优先级越高"""
    INFO = 10
    WARNING = 20
    CRITICAL = 30


# 级别对应的 emoji 前缀
_LEVEL_EMOJI = {
    NotificationLevel.INFO: "ℹ️",
    NotificationLevel.WARNING: "⚠️",
    NotificationLevel.CRITICAL: "🚨",
}

# 级别中文名
_LEVEL_LABEL = {
    NotificationLevel.INFO: "信息",
    NotificationLevel.WARNING: "警告",
    NotificationLevel.CRITICAL: "紧急",
}


class TelegramNotifier:
    """Telegram 通知器

    - 有 TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID 时发送 Telegram 消息
    - 无配置时自动降级为纯日志输出
    - 异步发送，不阻塞调用方
    """

    def __init__(self):
        self._bot_token: Optional[str] = None
        self._chat_id: Optional[str] = None
        self._min_level: NotificationLevel = NotificationLevel.INFO
        self._enabled: bool = False
        self._api_base: str = "https://api.telegram.org"
        self._lock = threading.Lock()
        self._load_config()

    def _load_config(self):
        """从环境变量和 config 单例加载配置"""
        self._bot_token = (
            os.getenv("TELEGRAM_BOT_TOKEN")
            or getattr(_cfg, "TELEGRAM_BOT_TOKEN", None)
            or ""
        )
        self._chat_id = (
            os.getenv("TELEGRAM_CHAT_ID")
            or getattr(_cfg, "TELEGRAM_CHAT_ID", None)
            or ""
        )

        # 从环境变量读取最低通知级别
        level_str = (
            os.getenv("TELEGRAM_MIN_LEVEL")
            or getattr(_cfg, "TELEGRAM_MIN_LEVEL", None)
            or "INFO"
        ).upper()
        try:
            self._min_level = NotificationLevel[level_str]
        except KeyError:
            self._min_level = NotificationLevel.INFO

        self._enabled = bool(self._bot_token and self._chat_id)
        if self._enabled:
            logger.info(
                f"TelegramNotifier 已启用 (chat_id={self._chat_id}, "
                f"min_level={_LEVEL_LABEL[self._min_level]})"
            )
        else:
            logger.info("TelegramNotifier 未配置 Bot Token，降级为纯日志模式")

    def set_min_level(self, level: str):
        """设置最低接收级别

        参数：
            level: "INFO" / "WARNING" / "CRITICAL"
        """
        with self._lock:
            try:
                self._min_level = NotificationLevel[level.upper()]
                logger.info(f"Telegram 最低通知级别设为 {level}")
            except KeyError:
                logger.warning(f"无效的通知级别: {level}")

    def _should_send(self, level: NotificationLevel) -> bool:
        """是否应该发送该级别的通知"""
        return level >= self._min_level

    def _format_message(self, level: NotificationLevel, text: str) -> str:
        """格式化消息"""
        emoji = _LEVEL_EMOJI.get(level, "")
        label = _LEVEL_LABEL.get(level, "")
        return f"{emoji} [{label}] {text}"

    async def send(self, level: NotificationLevel, text: str):
        """异步发送通知

        参数：
            level: 通知级别
            text: 通知内容
        """
        if not self._should_send(level):
            return

        message = self._format_message(level, text)

        if not self._enabled:
            # 降级模式：只写日志
            logger.log(
                "INFO" if level == NotificationLevel.INFO
                else "WARNING" if level == NotificationLevel.WARNING
                else "ERROR",
                f"[Telegram 降级] {message}",
            )
            return

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self._api_base}/bot{self._bot_token}/sendMessage",
                    json={
                        "chat_id": self._chat_id,
                        "text": message,
                        "parse_mode": "HTML",
                    },
                )
                if resp.status_code != 200:
                    logger.warning(
                        f"Telegram 发送失败: HTTP {resp.status_code} - "
                        f"{resp.text[:200]}"
                    )
        except Exception as e:
            # 发送失败不重试，只记录日志
            logger.warning(f"Telegram 发送异常: {e}")

    def send_sync(self, level: NotificationLevel, text: str):
        """同步发送通知（在非 async 上下文中使用）

        参数：
            level: 通知级别
            text: 通知内容

        注意：使用线程执行异步发送，避免 asyncio.run() 污染主线程 event loop。
        """
        try:
            loop = asyncio.get_running_loop()
            # 已在 event loop 中，创建任务
            loop.create_task(self.send(level, text))
        except RuntimeError:
            # 不在 event loop 中，用线程执行避免污染主线程
            def _run():
                try:
                    asyncio.run(self.send(level, text))
                except Exception as e:
                    logger.warning(f"Telegram send_sync 异常: {e}")

            t = threading.Thread(target=_run, daemon=True)
            t.start()
            t.join(timeout=15)  # 等待发送完成（httpx timeout=10s）

    async def send_critical(self, text: str):
        """发送紧急通知（止损触发、熔断、daemon 崩溃）"""
        await self.send(NotificationLevel.CRITICAL, text)

    async def send_warning(self, text: str):
        """发送警告通知（日亏损、资源告警）"""
        await self.send(NotificationLevel.WARNING, text)

    async def send_info(self, text: str):
        """发送信息通知（开仓/平仓、日报）"""
        await self.send(NotificationLevel.INFO, text)

    def send_critical_sync(self, text: str):
        """同步发送紧急通知"""
        self.send_sync(NotificationLevel.CRITICAL, text)

    def send_warning_sync(self, text: str):
        """同步发送警告通知"""
        self.send_sync(NotificationLevel.WARNING, text)

    def send_info_sync(self, text: str):
        """同步发送信息通知"""
        self.send_sync(NotificationLevel.INFO, text)

    @property
    def enabled(self) -> bool:
        """是否启用 Telegram 发送"""
        return self._enabled


# 全局单例
notifier = TelegramNotifier()
