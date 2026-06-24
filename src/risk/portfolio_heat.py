"""
组合热力 (Portfolio Heat)

计算所有策略持仓的总风险敞口占总资金的比例。
超过阈值时拒绝新开仓。

架构说明：
- daemon 多进程隔离，各策略独立 state 文件
- 通过共享文件 data/portfolio_heat.json 协调
- 每个 daemon 写自己的 position_heat 到 state 文件
- PortfolioHeatManager 聚合所有策略，写入共享文件
- daemon 开仓前检查共享文件

Portfolio Heat = Σ(持仓市值 × ATR%) / 总资金
ATR% = ATR / price（归一化的波动率）

用法：
    from src.risk.portfolio_heat import PortfolioHeatManager

    # daemon 端：记录自己的热力
    phm = PortfolioHeatManager(strategy_name="rsi", state_dir="data")
    phm.update_position_heat(lots, current_price, atr, initial_capital)

    # daemon 端：开仓前检查
    if not phm.can_open_new_position(new_position_risk):
        return None  # 拒绝开仓

    # live_data 端：读取组合热力
    heat = phm.get_portfolio_heat()
"""

import json
import time
import os
from pathlib import Path
from typing import Optional
from datetime import datetime

from src.utils.logger import logger


# 默认阈值
DEFAULT_MAX_HEAT = 0.15  # 15%
# 共享文件更新间隔（秒），避免频繁 IO
UPDATE_INTERVAL = 5
# 共享文件锁超时（秒）
LOCK_TIMEOUT = 10


class PortfolioHeatManager:
    """组合热力管理器

    每个 daemon 实例管理自己的 position_heat，
    通过共享文件协调跨策略的总热力。
    """

    def __init__(
        self,
        strategy_name: str,
        state_dir: str = "data",
        max_heat: float = DEFAULT_MAX_HEAT,
    ):
        self.strategy_name = strategy_name
        self.state_dir = Path(state_dir)
        self.max_heat = max_heat
        self._shared_file = self.state_dir / "portfolio_heat.json"
        self._my_heat: float = 0.0
        self._last_update: float = 0.0

    def update_position_heat(
        self,
        lots: dict,
        current_price: float,
        atr: Optional[float],
        initial_capital: float,
    ) -> float:
        """更新本策略的持仓热力

        参数：
            lots: {tag: {"amount": float, "cost_price": float}}
            current_price: 当前价格
            atr: 当前 ATR 值（None 时用 2% 近似）
            initial_capital: 初始资金

        返回：本策略的热力值（占初始资金比例）
        """
        total_position_value = 0.0
        total_risk = 0.0

        for tag, lot in lots.items():
            amount = float(lot.get("amount", 0))
            if amount <= 0:
                continue
            position_value = amount * current_price
            total_position_value += position_value

            # ATR% = ATR / price，无 ATR 时用 2% 近似
            if atr and current_price > 0:
                atr_pct = atr / current_price
            else:
                atr_pct = 0.02

            # 单仓位风险 = 持仓市值 × ATR%
            position_risk = position_value * atr_pct
            total_risk += position_risk

        # 热力 = 总风险 / 初始资金
        if initial_capital > 0:
            self._my_heat = total_risk / initial_capital
        else:
            self._my_heat = 0.0

        # 写入共享文件
        now = time.time()
        if now - self._last_update > UPDATE_INTERVAL:
            self._write_shared(total_position_value, total_risk)
            self._last_update = now

        return self._my_heat

    def can_open_new_position(
        self,
        new_position_risk: float,
        initial_capital: float,
    ) -> bool:
        """检查是否可以开新仓

        参数：
            new_position_risk: 新仓位的风险（持仓市值 × ATR%）
            initial_capital: 本策略初始资金

        返回：True = 可以开仓，False = 拒绝
        """
        portfolio_heat = self.get_portfolio_heat()
        new_heat = new_position_risk / initial_capital if initial_capital > 0 else 0
        projected_heat = portfolio_heat + new_heat

        if projected_heat > self.max_heat:
            logger.warning(
                f"Portfolio Heat 拒单: 当前 {portfolio_heat:.1%} + 新仓 {new_heat:.1%} "
                f"= {projected_heat:.1%} > 阈值 {self.max_heat:.1%}"
            )
            return False

        return True

    def get_portfolio_heat(self) -> float:
        """读取组合总热力（所有策略之和）"""
        data = self._read_shared()
        if data is None:
            return 0.0

        total_heat = 0.0
        for strat, info in data.get("strategies", {}).items():
            total_heat += float(info.get("heat", 0))

        return total_heat

    def get_portfolio_detail(self) -> dict:
        """获取组合热力详情（用于 API 返回）"""
        data = self._read_shared()
        if data is None:
            return {
                "total_heat": 0.0,
                "max_heat": self.max_heat,
                "strategies": {},
                "updated_at": None,
            }

        strategies = data.get("strategies", {})
        total_heat = sum(float(v.get("heat", 0)) for v in strategies.values())

        return {
            "total_heat": round(total_heat, 4),
            "max_heat": self.max_heat,
            "heat_pct": round(total_heat / self.max_heat * 100, 1) if self.max_heat > 0 else 0,
            "strategies": {
                k: {
                    "heat": round(float(v.get("heat", 0)), 4),
                    "position_value": round(float(v.get("position_value", 0)), 2),
                    "position_risk": round(float(v.get("position_risk", 0)), 2),
                }
                for k, v in strategies.items()
            },
            "updated_at": data.get("updated_at"),
        }

    def _write_shared(self, position_value: float, position_risk: float) -> None:
        """写入共享文件（合并更新）"""
        try:
            data = self._read_shared() or {
                "strategies": {},
                "updated_at": None,
            }

            data["strategies"][self.strategy_name] = {
                "heat": round(self._my_heat, 6),
                "position_value": round(position_value, 2),
                "position_risk": round(position_risk, 2),
                "updated_at": datetime.now().isoformat(),
            }
            data["updated_at"] = datetime.now().isoformat()

            # 原子写入
            tmp_file = self._shared_file.with_suffix(".tmp")
            tmp_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_file.replace(self._shared_file)

        except Exception as e:
            logger.debug(f"PortfolioHeat write failed: {e}")

    def _read_shared(self) -> Optional[dict]:
        """读取共享文件"""
        try:
            if not self._shared_file.exists():
                return None
            return json.loads(
                self._shared_file.read_text(encoding="utf-8")
            )
        except Exception as e:
            logger.debug(f"PortfolioHeat read failed: {e}")
            return None

    def clear(self) -> None:
        """清除本策略的热力记录（平仓后调用）"""
        self._my_heat = 0.0
        try:
            data = self._read_shared() or {"strategies": {}, "updated_at": None}
            if self.strategy_name in data.get("strategies", {}):
                data["strategies"][self.strategy_name] = {
                    "heat": 0.0,
                    "position_value": 0.0,
                    "position_risk": 0.0,
                    "updated_at": datetime.now().isoformat(),
                }
                data["updated_at"] = datetime.now().isoformat()
                tmp_file = self._shared_file.with_suffix(".tmp")
                tmp_file.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                tmp_file.replace(self._shared_file)
        except Exception as e:
            logger.debug(f"PortfolioHeat clear failed: {e}")


__all__ = ["PortfolioHeatManager", "DEFAULT_MAX_HEAT"]
