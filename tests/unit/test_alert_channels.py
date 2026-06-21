"""告警外部通道单元测试。

用可注入的假发送函数，不触网络/SMTP。
重点验证：级别过滤、派发、通道故障隔离（不影响主流程）。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

from src.monitor.alert_manager import AlertManager, INFO, WARNING, CRITICAL
from src.monitor.alert_channels import (
    AlertChannel, WebhookChannel, EmailChannel,
)


class RecordingChannel(AlertChannel):
    """测试用通道：把收到的告警记下来。"""

    def __init__(self, min_level=WARNING):
        super().__init__(min_level)
        self.received = []

    def send(self, alert):
        self.received.append(alert)


class FailingChannel(AlertChannel):
    """测试用通道：发送时抛异常。"""

    def __init__(self, min_level=INFO):
        super().__init__(min_level)

    def send(self, alert):
        raise RuntimeError("channel down")


class TestLevelFilter:
    def test_should_send_respects_min_level(self):
        ch = RecordingChannel(min_level=WARNING)
        assert ch.should_send(INFO) is False
        assert ch.should_send(WARNING) is True
        assert ch.should_send(CRITICAL) is True

    def test_critical_only_channel(self):
        ch = RecordingChannel(min_level=CRITICAL)
        assert ch.should_send(WARNING) is False
        assert ch.should_send(CRITICAL) is True

    def test_invalid_min_level_rejected(self):
        with pytest.raises(ValueError):
            RecordingChannel(min_level="BOGUS")


class TestDispatch:
    def test_emit_dispatches_to_channel_above_threshold(self):
        ch = RecordingChannel(min_level=WARNING)
        am = AlertManager(channels=[ch])
        am.emit(CRITICAL, "src", "boom")
        assert len(ch.received) == 1
        assert ch.received[0]["message"] == "boom"

    def test_emit_skips_channel_below_threshold(self):
        ch = RecordingChannel(min_level=CRITICAL)
        am = AlertManager(channels=[ch])
        am.emit(WARNING, "src", "minor")
        assert ch.received == []

    def test_multiple_channels_independent_levels(self):
        warn_ch = RecordingChannel(min_level=WARNING)
        crit_ch = RecordingChannel(min_level=CRITICAL)
        am = AlertManager(channels=[warn_ch, crit_ch])
        am.emit(WARNING, "src", "w")
        am.emit(CRITICAL, "src", "c")
        # warn 通道收到两条，crit 通道只收到 critical
        assert len(warn_ch.received) == 2
        assert len(crit_ch.received) == 1
        assert crit_ch.received[0]["message"] == "c"

    def test_no_channels_still_records(self):
        am = AlertManager()  # 无通道
        alert = am.emit(WARNING, "src", "msg")
        assert alert in am.alerts


class TestFailureIsolation:
    def test_channel_failure_does_not_break_emit(self):
        """通道抛异常时 emit 仍正常返回、告警仍被记录。"""
        am = AlertManager(channels=[FailingChannel()])
        alert = am.emit(CRITICAL, "src", "boom")
        assert alert["message"] == "boom"
        assert len(am.alerts) == 1  # 主流程不受影响

    def test_one_failing_channel_does_not_block_others(self):
        good = RecordingChannel(min_level=INFO)
        am = AlertManager(channels=[FailingChannel(), good])
        am.emit(CRITICAL, "src", "boom")
        # 坏通道在前抛异常，好通道仍收到
        assert len(good.received) == 1


class TestWebhookChannel:
    def test_posts_payload_via_injected_fn(self):
        captured = {}

        def fake_post(url, payload, timeout):
            captured["url"] = url
            captured["payload"] = payload
            captured["timeout"] = timeout

        ch = WebhookChannel("http://example/hook", post_fn=fake_post, timeout=3.0)
        alert = {"time": "t", "level": CRITICAL, "source": "s", "message": "m"}
        ch.send(alert)
        assert captured["url"] == "http://example/hook"
        assert captured["payload"] == alert
        assert captured["timeout"] == 3.0


class TestEmailChannel:
    def test_builds_message_via_injected_sender(self):
        captured = {}

        def fake_send(msg, smtp_config):
            captured["msg"] = msg
            captured["config"] = smtp_config

        ch = EmailChannel(
            smtp_config={"host": "smtp.example", "port": 587},
            from_addr="bot@example.com",
            to_addrs=["me@example.com"],
            send_fn=fake_send,
        )
        alert = {"time": "t", "level": CRITICAL, "source": "risk", "message": "stop"}
        ch.send(alert)
        msg = captured["msg"]
        assert msg["From"] == "bot@example.com"
        assert msg["To"] == "me@example.com"
        assert "CRITICAL" in msg["Subject"]
        assert "stop" in msg.get_content()

    def test_email_defaults_to_critical_only(self):
        ch = EmailChannel(
            smtp_config={"host": "h"}, from_addr="a", to_addrs=["b"],
            send_fn=lambda m, c: None,
        )
        assert ch.should_send(WARNING) is False
        assert ch.should_send(CRITICAL) is True


class TestDeliveryEscalation:
    """OPEN-2：通道全部失败时的兜底升级 + 健康检查。

    项目用 loguru（非 stdlib logging），caplog 无效，故用 loguru sink 捕获。
    """

    @staticmethod
    def _capture():
        """返回 (messages, remove_fn)：注册一个 loguru sink 收集 CRITICAL 消息。"""
        from src.utils.logger import logger
        msgs = []
        sink_id = logger.add(lambda m: msgs.append(m.record["message"]), level="CRITICAL")
        return msgs, lambda: logger.remove(sink_id)

    def test_all_channels_fail_logs_critical(self):
        """有通道本应发送但全部失败 → 记一条 CRITICAL 兜底日志。"""
        msgs, remove = self._capture()
        try:
            am = AlertManager(channels=[FailingChannel(), FailingChannel()])
            am.emit(CRITICAL, "src", "boom")
        finally:
            remove()
        assert any("ALERT DELIVERY FAILURE" in m for m in msgs)

    def test_partial_failure_no_escalation(self):
        """只要有一个通道成功，就不算投递失败，不升级。"""
        msgs, remove = self._capture()
        try:
            good = RecordingChannel(min_level=INFO)
            am = AlertManager(channels=[FailingChannel(), good])
            am.emit(CRITICAL, "src", "boom")
        finally:
            remove()
        assert not any("ALERT DELIVERY FAILURE" in m for m in msgs)
        assert len(good.received) == 1

    def test_no_channels_no_escalation(self):
        """无通道时不触发兜底（channels 为空是 no-op）。"""
        msgs, remove = self._capture()
        try:
            am = AlertManager()  # 无通道
            am.emit(CRITICAL, "src", "boom")
        finally:
            remove()
        assert not any("ALERT DELIVERY FAILURE" in m for m in msgs)

    def test_below_threshold_failure_not_counted(self):
        """通道因级别过滤未尝试发送，不算失败、不升级。"""
        msgs, remove = self._capture()
        try:
            crit_only = RecordingChannel(min_level=CRITICAL)
            am = AlertManager(channels=[crit_only])
            am.emit(WARNING, "src", "minor")  # 低于阈值，未尝试
        finally:
            remove()
        assert not any("ALERT DELIVERY FAILURE" in m for m in msgs)

    def test_health_check_all_ok(self):
        good1 = RecordingChannel(min_level=INFO)
        good2 = RecordingChannel(min_level=INFO)
        am = AlertManager(channels=[good1, good2])
        health = am.check_channels_health()
        assert health == {"RecordingChannel": True}  # 同名通道键合并，均成功
        assert len(good1.received) == 1  # 探针已发送

    def test_health_check_all_fail_logs_critical(self):
        msgs, remove = self._capture()
        try:
            am = AlertManager(channels=[FailingChannel()])
            health = am.check_channels_health()
        finally:
            remove()
        assert health == {"FailingChannel": False}
        assert any("ALERT CHANNELS UNHEALTHY" in m for m in msgs)

    def test_health_check_no_channels_empty(self):
        am = AlertManager()
        assert am.check_channels_health() == {}
