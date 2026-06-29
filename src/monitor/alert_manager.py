"""
告警管理器（Phase 5）

把风控事件与指标阈值越界转成结构化告警。
纯逻辑 + 日志输出，不依赖外部告警服务；可单元测试。
后续可在 emit 处接入邮件/webhook 等外部通道。
"""

import time
from typing import Dict, List, Optional, TYPE_CHECKING
from datetime import datetime

from src.execution.risk_manager import RiskManager
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.monitor.alert_channels import AlertChannel


# 告警级别
INFO = "INFO"
WARNING = "WARNING"
CRITICAL = "CRITICAL"

# 告警限流配置
_MAX_ALERTS = 10000        # 内存中告警列表最大容量
_COOLDOWN_SECONDS = 300     # 相同 (source, message) 的冷却时间（5分钟）
_MAX_PER_SOURCE = 60        # 每个 source 每分钟最多告警数


class AlertManager:
    """告警管理器（含限流防抖）"""

    def __init__(
        self,
        max_drawdown_alert: float = 0.10,
        channels: Optional[List["AlertChannel"]] = None,
        cooldown_seconds: int = _COOLDOWN_SECONDS,
        max_alerts_per_source: int = _MAX_PER_SOURCE,
    ):
        """
        参数：
            max_drawdown_alert: 回撤告警阈值
            channels: 外部告警通道列表
            cooldown_seconds: 相同消息冷却时间（秒）
            max_alerts_per_source: 每 source 每分钟告警上限
        """
        self.max_drawdown_alert = max_drawdown_alert
        self.channels: List["AlertChannel"] = channels or []
        self.alerts: List[dict] = []
        self._seen_event_count = 0

        # 限流状态
        self._cooldown_seconds = cooldown_seconds
        self._max_per_source = max_alerts_per_source
        self._last_emit_time: Dict[str, float] = {}   # source_key -> last emit timestamp
        self._source_counts: Dict[str, List[float]] = {}  # source -> [timestamps in last 60s]

    def _should_throttle(self, level: str, source: str, message: str) -> bool:
        """判断是否应该跳过告警（去重 + 限流）"""
        # 去重：相同 (source, message) 在冷却期内不重复
        dedup_key = f"{source}:{message}"
        now = time.time()
        last = self._last_emit_time.get(dedup_key)
        if last is not None and (now - last) < self._cooldown_seconds:
            return True

        # 限流：每个 source 每分钟不超过 _max_per_source
        if source not in self._source_counts:
            self._source_counts[source] = []
        timestamps = self._source_counts[source]
        # 清理超过 60 秒的记录
        while timestamps and timestamps[0] < now - 60:
            timestamps.pop(0)
        if len(timestamps) >= self._max_per_source:
            return True

        # 更新计数
        timestamps.append(now)
        self._last_emit_time[dedup_key] = now
        return False

    def emit(self, level: str, source: str, message: str) -> dict:
        """产生一条告警（记录 + 日志 + 派发外部通道），含限流防抖"""

        if self._should_throttle(level, source, message):
            return {}  # 被限流，返回空 dict

        alert = {
            "time": datetime.now().isoformat(),
            "level": level,
            "source": source,
            "message": message,
        }

        # 环形缓冲区：超容量时移除最旧告警
        if len(self.alerts) >= _MAX_ALERTS:
            self.alerts.pop(0)
        self.alerts.append(alert)

        log = logger.error if level == CRITICAL else (
            logger.warning if level == WARNING else logger.info
        )
        log(f"ALERT[{level}] {source}: {message}")
        self._dispatch(alert)
        return alert

    def _dispatch(self, alert: dict) -> None:
        """派发到外部通道。单个通道失败被隔离，绝不影响告警主流程。

        若配置了通道、且本应发送该告警的通道全部失败，则记一条 CRITICAL
        兜底日志（escalation）——避免"告警系统自身静默失效"无人察觉。
        无通道时（channels 为空）为 no-op，不触发兜底。
        """
        attempted = 0
        failed = 0
        for ch in self.channels:
            try:
                if ch.should_send(alert["level"]):
                    attempted += 1
                    ch.send(alert)
            except Exception as e:
                # 告警通道挂掉不能拖垮交易/监控，仅记录
                failed += 1
                logger.error(
                    f"Alert channel {type(ch).__name__} failed: {e}"
                )

        # 兜底升级：有通道本应发送但全部失败 → 告警系统自身故障
        if attempted > 0 and failed == attempted:
            logger.critical(
                f"ALERT DELIVERY FAILURE: all {attempted} channel(s) failed to "
                f"deliver alert [{alert['level']}] {alert['source']}: "
                f"{alert['message']}"
            )

    def check_channels_health(self) -> Dict[str, bool]:
        """通道健康自检：对每个通道发送一条 INFO 探针，返回 {通道名: 是否成功}。

        全部失败时记 CRITICAL 兜底日志。无通道时返回空 dict。
        探针不进 self.alerts，也不受限流影响（直接调通道）。
        """
        probe = {
            "time": datetime.now().isoformat(),
            "level": INFO,
            "source": "healthcheck",
            "message": "channel health probe",
        }
        health: Dict[str, bool] = {}
        for ch in self.channels:
            name = type(ch).__name__
            try:
                # 探针强制发送，绕过 should_send 级别过滤
                ch.send(probe)
                health[name] = True
            except Exception as e:
                health[name] = False
                logger.error(f"Alert channel {name} health probe failed: {e}")

        if health and not any(health.values()):
            logger.critical(
                f"ALERT CHANNELS UNHEALTHY: all {len(health)} channel(s) "
                f"failed health probe: {list(health.keys())}"
            )
        return health

    def check_risk_events(self, rm: RiskManager) -> List[dict]:
        """
        检查 RiskManager 新增事件并产生告警（增量，避免重复）

        返回：本次新产生的告警列表
        """
        # 增量消费：用 len() 对比上次已消费数量，只取新增部分
        # 避免 list(rm.events) 每根 bar 复制整个 deque（上限 10000，O(n)）
        current_len = len(rm.events)
        if current_len <= self._seen_event_count:
            # deque 被 maxlen 截断后重置计数（避免索引错位）
            if current_len < self._seen_event_count:
                self._seen_event_count = 0
            return []
        # deque 支持切片（Python 3.5+），直接切新增部分
        new_events = list(rm.events)[self._seen_event_count:]
        self._seen_event_count = current_len

        new_alerts = []
        for ev in new_events:
            level = CRITICAL if ev["type"] == "EMERGENCY_STOP" else (
                WARNING if ev["type"] == "PAUSE" else INFO
            )
            new_alerts.append(
                self.emit(level, "risk_manager", f"{ev['type']}: {ev['reason']}")
            )
        return new_alerts

    def check_drawdown(self, total_return: float) -> Optional[dict]:
        """收益率越过回撤阈值则告警"""
        if total_return <= -self.max_drawdown_alert:
            return self.emit(
                CRITICAL, "drawdown",
                f"total_return {total_return:.2%} <= -{self.max_drawdown_alert:.2%}",
            )
        return None

    def critical_alerts(self) -> List[dict]:
        """所有 CRITICAL 告警"""
        return [a for a in self.alerts if a["level"] == CRITICAL]


# 导出
__all__ = ["AlertManager", "INFO", "WARNING", "CRITICAL"]
