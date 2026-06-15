"""
告警管理器（Phase 5）

把风控事件与指标阈值越界转成结构化告警。
纯逻辑 + 日志输出，不依赖外部告警服务；可单元测试。
后续可在 emit 处接入邮件/webhook 等外部通道。
"""

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


class AlertManager:
    """告警管理器"""

    def __init__(
        self,
        max_drawdown_alert: float = 0.10,
        channels: Optional[List["AlertChannel"]] = None,
    ):
        """
        参数：
            max_drawdown_alert: 回撤告警阈值（总收益率低于 -阈值 触发 CRITICAL）
            channels: 外部告警通道列表（webhook/邮件等），为空则只记录+日志
        """
        self.max_drawdown_alert = max_drawdown_alert
        self.channels: List["AlertChannel"] = channels or []
        self.alerts: List[dict] = []
        self._seen_event_count = 0

    def emit(self, level: str, source: str, message: str) -> dict:
        """产生一条告警（记录 + 日志 + 派发外部通道）"""
        alert = {
            "time": datetime.now().isoformat(),
            "level": level,
            "source": source,
            "message": message,
        }
        self.alerts.append(alert)
        log = logger.error if level == CRITICAL else (
            logger.warning if level == WARNING else logger.info
        )
        log(f"ALERT[{level}] {source}: {message}")
        self._dispatch(alert)
        return alert

    def _dispatch(self, alert: dict) -> None:
        """派发到外部通道。单个通道失败被隔离，绝不影响告警主流程。"""
        for ch in self.channels:
            try:
                if ch.should_send(alert["level"]):
                    ch.send(alert)
            except Exception as e:
                # 告警通道挂掉不能拖垮交易/监控，仅记录
                logger.error(
                    f"Alert channel {type(ch).__name__} failed: {e}"
                )

    def check_risk_events(self, rm: RiskManager) -> List[dict]:
        """
        检查 RiskManager 新增事件并产生告警（增量，避免重复）

        返回：本次新产生的告警列表
        """
        new_events = rm.events[self._seen_event_count:]
        self._seen_event_count = len(rm.events)

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
