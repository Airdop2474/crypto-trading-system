from enum import Enum
from typing import List, Optional

import numpy as np
import pandas as pd


class MarketState(Enum):
    """市场状态枚举"""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"


# 策略推荐映射：每个状态下按优先级排列
RECOMMENDATIONS = {
    MarketState.TRENDING_UP: ["ma", "rsi", "buyhold"],
    MarketState.TRENDING_DOWN: ["buyhold", "ma"],
    MarketState.RANGING: ["grid", "ma", "rsi"],
    MarketState.VOLATILE: ["rsi", "buyhold"],
}

RECOMMENDATION_ACTION = {
    MarketState.TRENDING_UP: "趋势向上 → 推荐趋势跟踪策略",
    MarketState.TRENDING_DOWN: "趋势向下 → 建议轻仓或持有",
    MarketState.RANGING: "横盘震荡 → 推荐网格策略",
    MarketState.VOLATILE: "高波动 → 推荐动量策略，注意风控",
}


def _calc_ema(series: pd.Series, span: int) -> pd.Series:
    """计算 EMA（兼容旧版 pandas）。"""
    return series.ewm(span=span, adjust=False).mean()


def _calc_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    """基于 Wilder 平滑计算 ADX(14)。

    返回最新的 ADX 值，数据不足时返回 0.0。
    """
    n = len(close)
    if n < period + 1:
        return 0.0

    # True Range
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    # Directional Movement
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    # Wilder 平滑（smoothed = prev * (n-1)/n + current * 1/n）
    atr = float(tr.iloc[1:period + 1].mean())
    plus_di_s = float(pd.Series(plus_dm).iloc[1:period + 1].mean())
    minus_di_s = float(pd.Series(minus_dm).iloc[1:period + 1].mean())

    dx_values = []
    for i in range(period + 1, n):
        atr = atr * (period - 1) / period + tr.iloc[i] / period
        plus_di_s = plus_di_s * (period - 1) / period + plus_dm[i] / period
        minus_di_s = minus_di_s * (period - 1) / period + minus_dm[i] / period

        pdi = plus_di_s / atr * 100 if atr > 0 else 0.0
        mdi = minus_di_s / atr * 100 if atr > 0 else 0.0
        denom = pdi + mdi
        dx = abs(pdi - mdi) / denom * 100 if denom > 0 else 0.0
        dx_values.append(dx)

    if not dx_values:
        return 0.0

    # ADX: Wilder 平滑 DX
    adx = dx_values[0]
    for dx in dx_values[1:]:
        adx = adx * (period - 1) / period + dx / period

    return round(adx, 2)


def _calc_bollinger_width(close: pd.Series, period: int = 20, num_std: float = 2.0) -> float:
    """计算布林带宽度（% 中间价）。

    返回：(上轨 - 下轨) / 中间价，数据不足时返回 0.0。
    """
    if len(close) < period:
        return 0.0

    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + num_std * std
    lower = sma - num_std * std
    width_pct = (upper - lower) / sma

    latest = width_pct.iloc[-1]
    return 0.0 if pd.isna(latest) else float(latest)


class MarketClassifier:
    """市场状态分类器，阈值可参数化。

    基于近 20 天 OHLCV 数据，综合 EMA 趋势、ADX 趋势强度、布林带波动率
    三类指标，将市场状态归类为四种模式，并给出策略推荐。

    指标：
    - EMA20 vs EMA50 斜率：趋势方向（上/下/横盘）
    - ADX(14)：趋势强度（>25 有趋势，<20 无趋势）
    - 布林带宽度(20,2)：波动率（宽度/中间价 > 5% 为高波动）

    状态：
    - trending_up:   上升趋势，适合 MA/RSI 趋势策略
    - trending_down: 下降趋势，适合空仓或做空
    - ranging:       横盘震荡，适合网格策略
    - volatile:      高波动，适合动量/突破策略（或暂停）
    """

    # ---- 可参数化阈值 ----
    ADX_TRENDING_THRESHOLD: float = 25.0
    ADX_RANGING_THRESHOLD: float = 20.0
    BB_WIDTH_VOLATILE: float = 0.05
    BB_WIDTH_RANGING: float = 0.02
    EMA_SLOPE_UP: float = 0.002
    EMA_SLOPE_DOWN: float = -0.002

    def __init__(
        self,
        adx_trending: float = 25.0,
        adx_ranging: float = 20.0,
        bb_width_volatile: float = 0.05,
        bb_width_ranging: float = 0.02,
        ema_slope_up: float = 0.002,
        ema_slope_down: float = -0.002,
    ):
        self.adx_trending = adx_trending
        self.adx_ranging = adx_ranging
        self.bb_width_volatile = bb_width_volatile
        self.bb_width_ranging = bb_width_ranging
        self.ema_slope_up = ema_slope_up
        self.ema_slope_down = ema_slope_down

    def classify_market(self, df: pd.DataFrame, lookback: int = 20) -> str:
        """基于近 lookback 天数据分类当前市场状态。

        参数：
            df: OHLCV DataFrame，需含 open/high/low/close + timestamp
            lookback: 回看窗口天数（默认 20）

        返回：
            'trending_up' | 'trending_down' | 'ranging' | 'volatile'
        """
        state, _ = self._classify_with_intermediates(df, lookback)
        return state

    def _classify_with_intermediates(
        self, df: pd.DataFrame, lookback: int = 20
    ) -> tuple:
        """分类并返回中间计算结果，避免 classify_and_recommend 重复计算。

        返回：
            (state: str, intermediates: dict)
        """
        if len(df) < lookback:
            return MarketState.RANGING.value, {}

        recent = df.tail(lookback).copy()
        close = recent["close"]
        high = recent["high"]
        low = recent["low"]

        # 1. EMA 趋势方向
        ema20 = _calc_ema(close, 20)
        ema50 = _calc_ema(close, 50)
        ema20_last = float(ema20.iloc[-1])
        ema50_last = float(ema50.iloc[-1])

        # 斜率（最后 5 根 EMA 的线性回归）
        ema20_slope = 0.0
        if len(ema20) >= 5:
            tail = ema20.tail(5)
            x = np.arange(5)
            y = tail.values
            if np.std(y) > 0:
                ema20_slope = float(np.polyfit(x, y, 1)[0]) / ema20_last

        # 2. ADX 趋势强度
        adx = _calc_adx(high, low, close, 14)

        # 3. 布林带波动率
        bb_width = _calc_bollinger_width(close, 20, 2.0)

        intermediates = {
            "ema20": round(ema20_last, 2),
            "ema20_slope": ema20_slope,
            "adx": round(adx, 2),
            "bb_width": bb_width,
        }

        # ---- 判定逻辑（使用实例阈值）----
        is_volatile = bb_width > self.bb_width_volatile
        is_trending = adx > self.adx_trending
        is_ranging = adx < self.adx_ranging

        # 高波动 → volatile（最高优先级）
        if is_volatile:
            return MarketState.VOLATILE.value, intermediates

        # 强趋势
        if is_trending:
            if ema20_slope > self.ema_slope_up and ema20_last > ema50_last:
                return MarketState.TRENDING_UP.value, intermediates
            elif ema20_slope < self.ema_slope_down and ema20_last < ema50_last:
                return MarketState.TRENDING_DOWN.value, intermediates
            # 有趋势强度但方向模糊 → 看 EMA 排列
            if ema20_last > ema50_last:
                return MarketState.TRENDING_UP.value, intermediates
            elif ema20_last < ema50_last:
                return MarketState.TRENDING_DOWN.value, intermediates

        # 低趋势强度 → ranging
        if is_ranging:
            return MarketState.RANGING.value, intermediates

        # 中等 → 看波动率
        if bb_width < self.bb_width_ranging:
            return MarketState.RANGING.value, intermediates
        else:
            return MarketState.VOLATILE.value, intermediates


# 默认分类器实例（模块级，向后兼容）
_default_classifier = MarketClassifier()


def classify_market(df: pd.DataFrame, lookback: int = 20) -> str:
    """模块级包装器，委托给默认 MarketClassifier 实例。"""
    return _default_classifier.classify_market(df, lookback)


def get_strategy_recommendation(market_state: str) -> dict:
    """根据市场状态返回策略推荐。

    参数：
        market_state: classify_market() 返回的状态字符串

    返回：
        {"state": str, "strategies": [str], "action": str}
    """
    try:
        state = MarketState(market_state)
    except ValueError:
        state = MarketState.RANGING

    return {
        "state": state.value,
        "strategies": RECOMMENDATIONS.get(state, ["buyhold"]),
        "action": RECOMMENDATION_ACTION.get(state, "未知状态"),
    }


def classify_and_recommend(
    df: pd.DataFrame,
    lookback: int = 20,
    classifier: Optional[MarketClassifier] = None,
) -> dict:
    """一站式：分类 + 推荐（只计一次 ADX/BB/EMA，避免重复计算）。

    参数：
        df: OHLCV DataFrame
        lookback: 回看窗口
        classifier: 可选，可传入定制阈值的 MarketClassifier 实例

    返回：
        {"state": str, "strategies": [str], "action": str,
         "details": {"ema20_slope": float, "adx": float, "bb_width": float}}
    """
    clf = classifier or _default_classifier
    state, intermediates = clf._classify_with_intermediates(df, lookback)
    rec = get_strategy_recommendation(state)
    if intermediates:
        rec["details"] = {
            "ema20": intermediates["ema20"],
            "adx": intermediates["adx"],
            "bb_width": f"{intermediates['bb_width']:.2%}",
        }
    return rec


# 导出
__all__ = [
    "MarketClassifier",
    "MarketState",
    "classify_market",
    "get_strategy_recommendation",
    "classify_and_recommend",
]
