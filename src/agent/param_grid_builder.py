"""
参数搜索空间自动生成

从策略的 PARAM_SCHEMA 自动推导 walk_forward 所需的 param_grid，
避免手写搜索空间。对价格类无上限参数使用行情数据分位数。
"""

import numpy as np
import pandas as pd
from loguru import logger
from typing import Dict, List, Any, Type


# 不参与进化的参数（风控 / 开关 / 固定常量）
SKIP_PARAMS = frozenset({
    "max_consecutive_losses",
    "max_daily_loss",
    "initial_capital",
    "enable_filters",
    "enable_trend_filter",
})

# 无 max 且无默认分位数的参数 → 用行情数据推导
_PRICE_PARAMS = frozenset({"lower_price", "upper_price"})

# 每个参数的采样点数
_RESOLUTION = 3

# 组合上限：超出后随机采样
MAX_COMBINATIONS = 500

# 参与进化的参数数量上限（超过则只取前 N 个最重要的参数）
MAX_PARAMS = 4


class ParamGridBuilder:
    """根据 PARAM_SCHEMA + 行情数据自动生成搜索空间。"""

    def __init__(self, resolution: int = _RESOLUTION, max_combinations: int = MAX_COMBINATIONS):
        self.resolution = resolution
        self.max_combinations = max_combinations

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def build_grid(
        self,
        strategy_class: Type,
        data: pd.DataFrame | None = None,
    ) -> Dict[str, List]:
        """为指定策略类生成 param_grid。

        参数:
            strategy_class: 策略类（需有 PARAM_SCHEMA 类属性）
            data: 行情 DataFrame（含 close 列），用于价格类参数的分位数推导

        返回:
            param_grid dict，可直接传给 ParameterScanner.walk_forward()
        """
        schema: Dict[str, Dict[str, Any]] = getattr(strategy_class, "PARAM_SCHEMA", {})
        if not schema:
            return {}

        grid: Dict[str, List] = {}

        for name, spec in schema.items():
            if name in SKIP_PARAMS:
                continue

            param_type = spec.get("type", float)
            lo = spec.get("min")
            hi = spec.get("max")

            # 价格类参数：用数据分位数
            if name in _PRICE_PARAMS:
                values = self._from_data_quantiles(data, name, param_type)
                if values:
                    grid[name] = values
                continue

            # bool 参数：不搜索（只有 True/False 两个值，意义不大）
            if param_type is bool:
                continue

            # 无 min 的参数跳过（不应该发生，防御性）
            if lo is None:
                continue

            # 有 min + max → linspace
            if hi is not None:
                values = self._linspace(lo, hi, param_type)
                if values:
                    grid[name] = values
                continue

            # 有 min 但无 max → 用 min 的倍数推导上限
            values = self._open_range(lo, param_type)
            if values:
                grid[name] = values

        # 参数数量限制：超过 MAX_PARAMS 的只保留前 MAX_PARAMS 个
        if len(grid) > MAX_PARAMS:
            # 保留前 MAX_PARAMS 个（PARAM_SCHEMA 中定义顺序靠前的通常更重要）
            keys = list(grid.keys())[:MAX_PARAMS]
            grid = {k: grid[k] for k in keys}
            logger.info(f"参数数量超过 {MAX_PARAMS}，缩减至: {list(grid.keys())}")

        # 组合数检查
        self._cap_combinations(grid)

        return grid

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _linspace(self, lo: float, hi: float, param_type: type) -> List:
        """在 [lo, hi] 间均匀取 resolution 个点。"""
        if lo >= hi:
            return [param_type(lo)]

        raw = np.linspace(lo, hi, self.resolution)

        if param_type is int:
            values = sorted(set(int(round(v)) for v in raw))
        else:
            values = sorted(set(round(float(v), 4) for v in raw))

        return values

    def _open_range(self, lo: float, param_type: type) -> List:
        """只有 min 没有 max 的参数：取 [lo, lo*5] 范围。"""
        hi = max(lo * 5, lo + 10)
        return self._linspace(lo, hi, param_type)

    def _from_data_quantiles(
        self,
        data: pd.DataFrame | None,
        name: str,
        param_type: type,
    ) -> List:
        """用行情 close 列的分位数推导价格参数搜索范围。"""
        if data is None or data.empty or "close" not in data.columns:
            return []

        closes = data["close"].dropna()
        if closes.empty:
            return []

        if name == "lower_price":
            # lower_price: 取 5%~50% 分位
            quantiles = [0.05, 0.15, 0.25, 0.35, 0.50]
        else:
            # upper_price: 取 50%~95% 分位
            quantiles = [0.50, 0.65, 0.75, 0.85, 0.95]

        raw = closes.quantile(quantiles).values

        if param_type is int:
            values = sorted(set(int(round(v)) for v in raw))
        else:
            values = sorted(set(round(float(v), 2) for v in raw))

        return values

    def _cap_combinations(self, grid: Dict[str, List]) -> None:
        """若组合数超限，对维度做缩减至目标值。

        直接计算每个维度应保留的值数（按比例缩减），避免逐个循环。
        """
        if not grid:
            return

        total = 1
        for vals in grid.values():
            total *= len(vals)

        if total <= self.max_combinations:
            return

        logger.warning(
            f"ParamGrid 组合数 {total} 超过上限 {self.max_combinations}，执行缩减"
        )

        # 按比例缩减：每个维度保留 floor(max_combinations^(1/n)) 个值
        # 若仍超限，继续缩减最大维度
        import math
        n_dims = len(grid)
        target_per_dim = max(2, int(self.max_combinations ** (1.0 / n_dims)))

        for key in grid:
            if len(grid[key]) > target_per_dim:
                grid[key] = grid[key][:target_per_dim]

        # 重新计算，若仍超限则继续缩减最大维度
        total = 1
        for vals in grid.values():
            total *= len(vals)

        while total > self.max_combinations and n_dims > 1:
            largest_key = max(grid, key=lambda k: len(grid[k]))
            if len(grid[largest_key]) <= 2:
                break
            grid[largest_key] = grid[largest_key][:-1]
            total = 1
            for vals in grid.values():
                total *= len(vals)

        logger.info(f"缩减后组合数: {total}")
