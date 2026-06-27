"""订单级下单护栏（Phase 7 Stage 4）

补齐 RISK_CONTROLS（LIVE_TRADING_CHECKLIST.md）里的订单频率/单笔上限护栏——
exchange 模式真实下单绕过了 PaperBroker 的每单仓位检查，RiskManager 又只管账户级
fill/pnl 熔断，故下单提交层另设一道节流。

只作用于 exchange 模式（由 ExchangeRunnerBroker 调用）。频率主判用 runner 传入的
**bar timestamp**（下单决策周期），同一 bar 触发的多笔 grid lot 视作一次决策、全放行；
单笔上限与日订单数仍逐单生效。
"""

import pandas as pd


class OrderRateGuard:
    """下单前节流：单笔名义额上限 + 最小决策间隔 + 日订单数。"""

    def __init__(self, reference_capital, max_position_per_trade=0.20,
                 min_trade_interval=300, max_trades_per_day=10):
        """
        参数：
            reference_capital: 资金基准（计价货币），算单笔名义额上限
            max_position_per_trade: 单笔名义额占资金基准上限（0.20=20%）
            min_trade_interval: 相邻下单决策周期最小间隔（秒，按 bar ts 判）
            max_trades_per_day: 单日订单数上限（逐单计）
        """
        self.reference_capital = reference_capital
        self.max_position_per_trade = max_position_per_trade
        self.min_trade_interval = min_trade_interval
        self.max_trades_per_day = max_trades_per_day
        self._last_ts = None
        self._day = None
        self._count = 0

    def check(self, notional, ts):
        """下单前校验。返回 (ok, reason)；ok=False 时不应下单。"""
        cap = self.max_position_per_trade * self.reference_capital
        if notional > cap:
            return False, f"单笔名义额 {notional:.2f} > 上限 {cap:.2f}"

        # 间隔按 bar：同一 bar（ts 相等）视作一次决策，不重复判间隔
        if self._last_ts is not None and ts != self._last_ts:
            gap = (pd.Timestamp(ts) - pd.Timestamp(self._last_ts)).total_seconds()
            if gap < self.min_trade_interval:
                return False, f"距上次下单 {gap:.0f}s < 最小间隔 {self.min_trade_interval}s"

        count = self._count if ts is not None and self._same_day(ts) else 0
        if count >= self.max_trades_per_day:
            return False, f"当日订单数 {count} >= 上限 {self.max_trades_per_day}"
        return True, ""

    def record(self, ts):
        """登记一次实际下单（check 通过且已提交后调用）。"""
        if ts is not None and not self._same_day(ts):
            self._day = pd.Timestamp(ts).date()
            self._count = 0
        elif self._day is None and ts is not None:
            self._day = pd.Timestamp(ts).date()
        self._count += 1
        self._last_ts = ts

    def _same_day(self, ts):
        return self._day is not None and pd.Timestamp(ts).date() == self._day

    def state_dict(self) -> dict:
        """序列化运行时状态，用于 checkpoint 持久化。

        不持久化 reference_capital 等配置（构造时已确定），
        只持久化运行时累计的 _last_ts/_day/_count，避免重启后护栏失效。
        """
        return {
            "_last_ts": str(self._last_ts) if self._last_ts is not None else None,
            "_day": str(self._day) if self._day is not None else None,
            "_count": self._count,
        }

    def load_state(self, st: dict) -> None:
        """从 checkpoint 恢复运行时状态。

        _day 从字符串还原为 date 对象；_last_ts 保持字符串（check 时用 pd.Timestamp 解析）。
        """
        if not st:
            return
        self._last_ts = st.get("_last_ts")
        day_str = st.get("_day")
        if day_str:
            try:
                self._day = pd.Timestamp(day_str).date()
            except Exception:
                self._day = None
        self._count = st.get("_count", 0)


__all__ = ["OrderRateGuard"]
