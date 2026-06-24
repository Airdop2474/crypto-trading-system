"""
TelegramNotifier + TelegramChannel 单元测试。

覆盖：
  - 无 Token 降级为纯日志（不报错）
  - 有 Token 时异步发送（mock httpx）
  - 级别过滤（min_level）
  - send_sync 在非 async 上下文中工作
  - TelegramChannel 桥接 AlertManager 告警
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.utils.telegram_notifier import (
    TelegramNotifier,
    NotificationLevel,
    notifier,
)


def _run_async(coro):
    """安全执行 async 协程，不污染主线程 event loop"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestTelegramNotifierDegraded:
    """无 Token 降级模式测试"""

    def test_no_token_degrades_to_log(self):
        """无 Bot Token 时 _enabled=False，send 不报错"""
        n = TelegramNotifier()
        n._bot_token = None
        n._chat_id = None
        n._enabled = False

        # 不应抛异常
        n.send_sync(NotificationLevel.CRITICAL, "test degraded")
        assert n.enabled is False

    def test_should_send_respects_min_level(self):
        """min_level 过滤：WARNING 级别不发送 INFO"""
        n = TelegramNotifier()
        n._min_level = NotificationLevel.WARNING

        assert n._should_send(NotificationLevel.CRITICAL) is True
        assert n._should_send(NotificationLevel.WARNING) is True
        assert n._should_send(NotificationLevel.INFO) is False

    def test_set_min_level(self):
        """set_min_level 正确更新"""
        n = TelegramNotifier()
        n.set_min_level("CRITICAL")
        assert n._min_level == NotificationLevel.CRITICAL
        assert n._should_send(NotificationLevel.WARNING) is False

    def test_format_message(self):
        """消息格式化包含 emoji 和级别标签"""
        n = TelegramNotifier()
        msg = n._format_message(NotificationLevel.CRITICAL, "test message")
        assert "🚨" in msg
        assert "紧急" in msg
        assert "test message" in msg

        msg_w = n._format_message(NotificationLevel.WARNING, "warn text")
        assert "⚠️" in msg_w
        assert "警告" in msg_w

        msg_i = n._format_message(NotificationLevel.INFO, "info text")
        assert "ℹ️" in msg_i
        assert "信息" in msg_i


class TestTelegramNotifierEnabled:
    """有 Token 时发送测试（mock httpx）"""

    def test_send_critical_with_mock(self):
        """有 Token 时异步发送 CRITICAL（mock httpx）"""
        n = TelegramNotifier()
        n._bot_token = "fake_token"
        n._chat_id = "fake_chat"
        n._enabled = True

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            _run_async(n.send_critical("critical test"))

            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert "fake_token" in call_args.args[0]
            assert call_args.kwargs["json"]["chat_id"] == "fake_chat"
            assert "🚨" in call_args.kwargs["json"]["text"]

    def test_send_failure_does_not_raise(self):
        """发送失败不抛异常（只记日志）"""
        n = TelegramNotifier()
        n._bot_token = "fake_token"
        n._chat_id = "fake_chat"
        n._enabled = True

        with patch("httpx.AsyncClient", side_effect=Exception("network error")):
            # 不应抛异常
            _run_async(n.send_warning("warning test"))

    def test_send_http_error_does_not_raise(self):
        """HTTP 非 200 不抛异常"""
        n = TelegramNotifier()
        n._bot_token = "fake_token"
        n._chat_id = "fake_chat"
        n._enabled = True

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Too Many Requests"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            _run_async(n.send_info("info test"))  # 不应抛异常


class TestTelegramChannel:
    """TelegramChannel 适配器测试"""

    def test_channel_send_degraded(self):
        """TelegramChannel.send 在降级模式下不报错"""
        from src.monitor.alert_channels import TelegramChannel

        ch = TelegramChannel()
        alert = {
            "level": "WARNING",
            "source": "RiskManager",
            "message": "daily loss 2%",
            "time": "2026-06-25 10:00:00",
        }
        # 降级模式（无 Token），不应抛异常
        ch.send(alert)

    def test_channel_level_mapping(self):
        """AlertManager 级别正确映射到 NotificationLevel"""
        from src.monitor.alert_channels import TelegramChannel

        ch = TelegramChannel()
        assert ch._LEVEL_MAP["INFO"] == "INFO"
        assert ch._LEVEL_MAP["WARNING"] == "WARNING"
        assert ch._LEVEL_MAP["CRITICAL"] == "CRITICAL"

    def test_channel_should_send(self):
        """TelegramChannel 级别过滤"""
        from src.monitor.alert_channels import TelegramChannel
        from src.monitor.alert_manager import INFO, WARNING, CRITICAL

        ch_warning = TelegramChannel(min_level=WARNING)
        assert ch_warning.should_send(CRITICAL) is True
        assert ch_warning.should_send(WARNING) is True
        assert ch_warning.should_send(INFO) is False

        ch_critical = TelegramChannel(min_level=CRITICAL)
        assert ch_critical.should_send(CRITICAL) is True
        assert ch_critical.should_send(WARNING) is False

    def test_channel_send_with_mock_notifier(self):
        """TelegramChannel.send 调用 notifier.send_sync"""
        from src.monitor.alert_channels import TelegramChannel

        ch = TelegramChannel()
        alert = {
            "level": "CRITICAL",
            "source": "FlashCrash",
            "message": "BTC dropped 12%",
            "time": "2026-06-25 10:00:00",
        }

        with patch("src.utils.telegram_notifier.notifier.send_sync") as mock_send:
            ch.send(alert)
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            level_arg = call_args.args[0]
            text_arg = call_args.args[1]
            assert level_arg == NotificationLevel.CRITICAL
            assert "FlashCrash" in text_arg
            assert "BTC dropped 12%" in text_arg


class TestGlobalNotifier:
    """全局单例测试"""

    def test_global_notifier_exists(self):
        """全局 notifier 单例存在且可用"""
        assert notifier is not None
        assert isinstance(notifier, TelegramNotifier)

    def test_global_notifier_send_sync_no_crash(self):
        """全局 notifier.send_sync 在任何环境下不崩溃"""
        notifier.send_sync(NotificationLevel.INFO, "unit test probe")
