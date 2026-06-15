"""
监控指标采集器（Phase 5）

把运行时状态（账户/风控/交易）快照成结构化指标，供监控展示与告警。
纯数据采集，不依赖外部服务；可单元测试。
"""

from typing import Dict, List, Optional
from datetime import datetime

from src.execution.risk_manager import RiskManager


class MetricsCollector:
    """运行时指标采集器"""

    def __init__(self):
        self.snapshots: List[dict] = []

    def snapshot(
        self,
        runner_result: Dict,
        current_prices: Dict[str, float],
        risk_manager: Optional[RiskManager] = None,
        timestamp: Optional[datetime] = None,
    ) -> dict:
        """
        采集一次指标快照

        参数：
            runner_result: PaperTradingRunner.run() 结果
            current_prices: {symbol: price} 用于持仓市值
            risk_manager: 可选 RiskManager（采集风控状态）
            timestamp: 快照时间（默认 now）

        返回：
            指标快照字典
        """
        stats = runner_result["statistics"]
        initial = stats["initial_balance"]
        cash = stats["current_balance"]
        positions = stats["positions"]

        position_value = sum(
            amt * current_prices.get(sym, 0.0) for sym, amt in positions.items()
        )
        total_value = cash + position_value
        total_return = (total_value - initial) / initial if initial > 0 else 0.0

        snap = {
            "timestamp": (timestamp or datetime.now()).isoformat(),
            "account": {
                "cash": cash,
                "position_value": position_value,
                "total_value": total_value,
                "total_return": total_return,
                "realized_pnl": runner_result.get("realized_pnl", 0.0),
            },
            "trades": {
                "total": stats["total_trades"],
                "total_cost": stats["total_cost"],
                "open_lots": len(runner_result.get("open_lots", {})),
            },
            "risk": self._risk_metrics(risk_manager),
        }
        self.snapshots.append(snap)
        return snap

    @staticmethod
    def _risk_metrics(rm: Optional[RiskManager]) -> dict:
        """采集风控状态指标"""
        if rm is None:
            return {"enabled": False}
        return {
            "enabled": True,
            "state": rm.state,
            "can_trade": rm.can_trade(),
            "daily_pnl": rm.daily_pnl,
            "consecutive_losses": rm.consecutive_losses,
            "api_failures": rm.api_failures,
            "event_count": len(rm.events),
        }

    def latest(self) -> Optional[dict]:
        """最近一次快照"""
        return self.snapshots[-1] if self.snapshots else None

    def to_records(self) -> List[dict]:
        """展平为时序记录（供写入 DB / 导出）"""
        records = []
        for s in self.snapshots:
            records.append({
                "timestamp": s["timestamp"],
                "total_value": s["account"]["total_value"],
                "total_return": s["account"]["total_return"],
                "realized_pnl": s["account"]["realized_pnl"],
                "total_trades": s["trades"]["total"],
                "risk_state": s["risk"].get("state", "N/A"),
                "consecutive_losses": s["risk"].get("consecutive_losses", 0),
            })
        return records


# 导出
__all__ = ["MetricsCollector"]
