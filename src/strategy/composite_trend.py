"""
复合趋势策略 — 基于 5 位 AI 共识的 V1 状态驱动型趋势策略

共识来源（docs/策略设计方案/）：
  Opus 4.8（基准方案，4/5 AI 选择）
  GPT 5.5（独立方案，工程细节最完整）
  DeepSeek V4 Pro / Opus 4.7 / GLM 5.2（均合并到 Opus 4.8）

设计取舍：
  - 五版方案在"骨架"上高度一致（ADX 总开关 + 多周期 EMA + MACD + RSI + 布林 + 成交量）
  - GPT 5.5 方案对入场条件描述最精确（拐头用差分量化），采纳其实现细节
  - Opus 4.8/GLM 5.2 的"休眠继承"出场规则是亮点，确保震荡市干净了结头寸
  - 单笔风险默认 1%（GPT/Opus 4.8）而非 0.5%（Deepseek 保守值），回测阶段宜用 0.5%
  - 入场精修（H1 回调至 EMA21）因在单周期回测中无法区分 H1/H4，V1 简化为 H4 收盘确认

入场 6 道硬过滤（AND 关系）：
  1. ADX(14) > 20                      → 趋势市确认
  2. EMA_fast > EMA_slow（多头排列）    → 趋势方向确认
  3. MACD 金叉（DIF > DEA）             → 动量确认
  4. RSI(14) ∈ [40, 60] 且拐头向上     → 非超买，健康回调恢复
  5. 价格 ≥ 布林中轨（BB20）             → 回调不破位
  6. 成交量 > 20 周期均量 × 0.8         → 量能支持

出场 6 类规则（优先级从高到低）：
  1. 初始止损  （入场价 - 1.5×ATR）
  2. 信号反转  （MACD 死叉 或 RSI > 75）
  3. ADX 休眠继承（ADX 跌破 15 后 3 根内仍未恢复，干净了结头寸）
  4. 移动止损  （从持仓以来最高收盘价回撤 1.5×ATR）
  5. 保本保护  （浮盈 > 1×ATR 后止损上移至保本）
  6. 时间止损  （开仓后 10 根未达 1×ATR 浮盈）

仓位：固定风险百分比 = 账户权益 × risk_per_trade / ATR止损距离
风控：继承 RiskAwareStrategy（连亏3次/日亏2%/回撤15%）

实现采用增量 O(1) 指标计算，保持与现有策略一致的性能特征。
ADX 缓冲区改为实例变量（避免类级变量共享 bug）。
"""

from typing import Optional, List
from datetime import datetime
import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.strategy.base import Order


class CompositeTrendStrategy(RiskAwareStrategy):
    """
    复合趋势策略 — 6 道硬过滤的趋势跟踪。

    适用环境：趋势市（ADX > 25）。
    不适合：震荡盘整市。
    """

    PARAM_SCHEMA = {
        "adx_period": {"type": int, "min": 7, "max": 30},
        "adx_threshold": {"type": float, "min": 15, "max": 40},
        "ema_fast": {"type": int, "min": 5, "max": 50},
        "ema_slow": {"type": int, "min": 20, "max": 200},
        "macd_fast": {"type": int, "min": 5, "max": 30},
        "macd_slow": {"type": int, "min": 10, "max": 60},
        "macd_signal": {"type": int, "min": 3, "max": 20},
        "rsi_period": {"type": int, "min": 5, "max": 30},
        "rsi_low": {"type": float, "min": 20, "max": 50},
        "rsi_high": {"type": float, "min": 50, "max": 80},
        "bb_period": {"type": int, "min": 10, "max": 50},
        "bb_std": {"type": float, "min": 1.0, "max": 4.0},
        "atr_period": {"type": int, "min": 5, "max": 30},
        "atr_multiplier": {"type": float, "min": 0.5, "max": 3.0},
        "risk_per_trade": {"type": float, "min": 0.002, "max": 0.05},
        "time_stop_bars": {"type": int, "min": 5, "max": 20},
        "adx_sleep_threshold": {"type": float, "min": 10, "max": 25},
        "adx_sleep_bars": {"type": int, "min": 2, "max": 6},
        "rsi_exit_high": {"type": float, "min": 60, "max": 90},
        "vol_period": {"type": int, "min": 5, "max": 50},
        "vol_ratio": {"type": float, "min": 0.5, "max": 2.0},
    }

    def __init__(
        self,
        # ADX 参数
        adx_period: int = 14,
        adx_threshold: float = 20.0,
        adx_sleep_threshold: float = 15.0,  # 休眠继承阈值
        adx_sleep_bars: int = 3,            # 休眠后强制出场 K 线数
        # 趋势 EMA（判断多空排列）
        ema_fast: int = 12,
        ema_slow: int = 26,
        # MACD 参数
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        # RSI 参数
        rsi_period: int = 14,
        rsi_low: float = 40.0,
        rsi_high: float = 60.0,
        rsi_exit_high: float = 75.0,        # RSI > 此值触发出场
        # 布林带
        bb_period: int = 20,
        bb_std: float = 2.0,
        # ATR（止损/仓位）
        atr_period: int = 14,
        atr_multiplier: float = 1.5,        # 初始止损 / 移动止损 / 第一止盈 = ATR × 此值
        # 成交量
        vol_period: int = 20,
        vol_ratio: float = 0.8,             # 当前量 > 均量 × vol_ratio
        # 仓位风控
        risk_per_trade: float = 0.01,       # 单笔最大风险占权益比
        # 时间止损
        time_stop_bars: int = 10,           # 开仓后 N 根 H4 未达 1×ATR 盈利则平仓
        # 熔断参数（传给基类）
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        max_drawdown: float = 0.15,
        initial_capital: float = 10000.0,
    ):
        super().__init__(
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            max_drawdown=max_drawdown,
            initial_capital=initial_capital,
        )
        self.name = "CompositeTrend"

        # 策略参数
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.adx_sleep_threshold = adx_sleep_threshold
        self.adx_sleep_bars = adx_sleep_bars

        self.ema_fast_p = ema_fast
        self.ema_slow_p = ema_slow

        self.macd_fast_p = macd_fast
        self.macd_slow_p = macd_slow
        self.macd_signal_p = macd_signal

        self.rsi_period = rsi_period
        self.rsi_low = rsi_low
        self.rsi_high = rsi_high
        self.rsi_exit_high = rsi_exit_high

        self.bb_period = bb_period
        self.bb_std = bb_std

        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier

        self.vol_period = vol_period
        self.vol_ratio = vol_ratio

        self.risk_per_trade = risk_per_trade
        self.time_stop_bars = time_stop_bars

        self.parameters = {
            "adx_period": adx_period, "adx_threshold": adx_threshold,
            "ema_fast": ema_fast, "ema_slow": ema_slow,
            "macd_fast": macd_fast, "macd_slow": macd_slow, "macd_signal": macd_signal,
            "rsi_period": rsi_period, "rsi_low": rsi_low, "rsi_high": rsi_high,
            "bb_period": bb_period, "bb_std": bb_std,
            "atr_period": atr_period, "atr_multiplier": atr_multiplier,
            "risk_per_trade": risk_per_trade, "time_stop_bars": time_stop_bars,
        }

        # --- 策略运行状态（实例变量，不共享）---
        self._bar_count: int = 0
        self._in_position: bool = False
        self._entry_bar: int = 0
        self._entry_price: float = 0.0
        self._entry_atr: float = 0.0         # 入场时的 ATR（止损/止盈计算基准）
        self._highest_close_since_entry: float = 0.0
        self._first_tp_done: bool = False    # 是否已触发第一止盈
        self._breakeven_activated: bool = False  # 保本保护是否已激活
        self._adx_below_sleep_bars: int = 0  # ADX 低于休眠阈值的连续 K 线数

        # --- 增量指标状态（全部为实例变量）---

        # EMA（用于趋势方向判断）
        self._ema_fast: Optional[float] = None
        self._ema_slow: Optional[float] = None

        # --- MACD（快线/慢线，各自存 prev 用于金叉/死叉检测）---
        self._macd_fast_ema: Optional[float] = None
        self._macd_slow_ema: Optional[float] = None
        self._macd_signal_ema: Optional[float] = None
        self._cur_macd_line: Optional[float] = None   # 当前 MACD Line（更新后）
        self._prev_macd_line: Optional[float] = None  # 上一根 MACD Line
        self._prev_signal_ema: Optional[float] = None  # 上一根 Signal Line
        self._macd_bar_count: int = 0  # 用于跟踪 MACD 预热

        # RSI（Wilder 平滑）
        self._rsi_prev_close: Optional[float] = None
        self._rsi_avg_gain: Optional[float] = None
        self._rsi_avg_loss: Optional[float] = None
        self._rsi_gain_init: List[float] = []
        self._rsi_loss_init: List[float] = []
        self._rsi_value: Optional[float] = None
        self._rsi_prev_value: Optional[float] = None  # 上一根 RSI（拐头判断）

        # 布林带
        self._bb_buffer: List[float] = []

        # ATR（Wilder 平滑）
        self._atr_value: Optional[float] = None
        self._atr_prev_close: Optional[float] = None
        self._atr_init_tr: List[float] = []

        # ADX（实例独立缓冲区，修复父类类变量共享问题）
        self._i_adx_period: int = adx_period
        self._i_adx_high_buf: List[float] = []
        self._i_adx_low_buf: List[float] = []
        self._i_adx_close_buf: List[float] = []
        self._i_adx_value: Optional[float] = None
        self._i_adx_plus_di: Optional[float] = None
        self._i_adx_minus_di: Optional[float] = None
        self._i_adx_initialized: bool = False

        # 成交量
        self._vol_buffer: List[float] = []

        # 预热所需 bar 数
        self._warmup = max(
            adx_period * 2 + 1,
            ema_slow + 1,
            macd_slow + macd_signal + 1,
            rsi_period + 2,
            bb_period + 1,
            atr_period + 2,
        )

    def reset(self) -> None:
        """重置全部状态。"""
        super().reset()
        self._bar_count = 0
        self._in_position = False
        self._entry_bar = 0
        self._entry_price = 0.0
        self._entry_atr = 0.0
        self._highest_close_since_entry = 0.0
        self._first_tp_done = False
        self._breakeven_activated = False
        self._adx_below_sleep_bars = 0

        self._ema_fast = None
        self._ema_slow = None

        self._macd_fast_ema = None
        self._macd_slow_ema = None
        self._macd_signal_ema = None
        self._cur_macd_line = None
        self._prev_macd_line = None
        self._prev_signal_ema = None
        self._macd_bar_count = 0

        self._rsi_prev_close = None
        self._rsi_avg_gain = None
        self._rsi_avg_loss = None
        self._rsi_gain_init.clear()
        self._rsi_loss_init.clear()
        self._rsi_value = None
        self._rsi_prev_value = None

        self._bb_buffer.clear()

        self._atr_value = None
        self._atr_prev_close = None
        self._atr_init_tr.clear()

        self._i_adx_high_buf.clear()
        self._i_adx_low_buf.clear()
        self._i_adx_close_buf.clear()
        self._i_adx_value = None
        self._i_adx_plus_di = None
        self._i_adx_minus_di = None
        self._i_adx_initialized = False

        self._vol_buffer.clear()

    def on_bar(
        self, data: pd.DataFrame, current_time: Optional[datetime] = None
    ) -> Optional[List[Order]]:
        """Bar 回调，返回信号列表或 None。"""
        if self._is_paused(current_time):
            return None

        bar = data.iloc[-1]
        close = float(bar["close"])
        high = float(bar["high"])
        low = float(bar["low"])
        volume = float(bar.get("volume", 0.0))
        self._bar_count += 1

        # --- 1. 更新所有指标 ---
        self._update_i_adx(high, low, close)
        self._update_trend_ema(close)
        self._update_macd(close)
        self._update_rsi(close)
        self._update_bb(close)
        self._update_atr(high, low, close)
        self._vol_buffer.append(volume)
        if len(self._vol_buffer) > self.vol_period * 3:
            self._vol_buffer = self._vol_buffer[-(self.vol_period * 3):]

        # --- 2. 持仓中：检查出场条件 ---
        if self._in_position:
            exit_tag = self._check_exit(close, high, low)
            if exit_tag:
                self._in_position = False
                self._first_tp_done = False
                self._breakeven_activated = False
                self._adx_below_sleep_bars = 0
                return [Order(side="SELL", tag="composite", fraction=1.0)]

        # --- 3. 预热期不入场 ---
        if self._bar_count < self._warmup:
            return None

        # --- 4. 空仓中：检查入场条件 ---
        if not self._in_position:
            entry_ok, _ = self._check_entry(close, volume)
            if entry_ok:
                # 仓位计算：固定风险百分比 / ATR止损距离
                atr = self._atr_value or (close * 0.01)
                stop_dist = atr * self.atr_multiplier
                fraction = (self.risk_per_trade * self.initial_capital) / (stop_dist * close)
                fraction = min(max(fraction, 0.01), 1.0)

                self._in_position = True
                self._entry_bar = self._bar_count
                self._entry_price = close
                self._entry_atr = atr
                self._highest_close_since_entry = close
                self._first_tp_done = False
                self._breakeven_activated = False
                self._adx_below_sleep_bars = 0

                return [Order(side="BUY", tag="composite", fraction=fraction)]

        return None

    # ==================================================================
    # 入场判断：6 道硬过滤
    # ==================================================================
    def _check_entry(self, close: float, volume: float) -> tuple:
        """
        6 道 AND 过滤，全部通过返回 (True, tag)，否则 (False, '')。
        逐层短路，按"最常见失效原因"排序降低计算量。
        """
        # 1. ADX > threshold（趋势市确认）
        adx = self._i_adx_value
        if adx is None or adx <= self.adx_threshold:
            return False, ""

        # 2. EMA 多头排列（fast EMA > slow EMA）
        if self._ema_fast is None or self._ema_slow is None:
            return False, ""
        if self._ema_fast <= self._ema_slow:
            return False, ""

        # 3. MACD 金叉（DIF 上穿 DEA）
        # 上一根：DIF <= DEA；当前根：DIF > DEA
        if (
            self._prev_macd_line is None or self._prev_signal_ema is None
            or self._cur_macd_line is None or self._macd_signal_ema is None
        ):
            return False, ""
        if not (self._prev_macd_line <= self._prev_signal_ema and self._cur_macd_line > self._macd_signal_ema):
            return False, ""

        # 4. RSI ∈ [low, high] 且拐头向上（当前 RSI > 上一根 RSI）
        rsi = self._rsi_value
        if rsi is None:
            return False, ""
        if not (self.rsi_low <= rsi <= self.rsi_high):
            return False, ""
        if self._rsi_prev_value is not None and rsi <= self._rsi_prev_value:
            return False, ""

        # 5. 收盘价站上布林中轨
        bb_mid = self._get_bb_mid()
        if bb_mid is None or close < bb_mid:
            return False, ""

        # 6. 成交量确认
        if len(self._vol_buffer) < self.vol_period:
            return False, ""
        avg_vol = float(np.mean(self._vol_buffer[-self.vol_period:]))
        if avg_vol > 0 and volume < avg_vol * self.vol_ratio:
            return False, ""

        # 构建 tag 便于归因
        tag = f"adx{adx:.0f}_rsi{rsi:.0f}"
        return True, tag

    # ==================================================================
    # 出场判断：6 类出场规则
    # ==================================================================
    def _check_exit(self, close: float, high: float, low: float) -> Optional[str]:
        """
        按优先级检查出场规则，返回 tag 字符串或 None。
        在 on_bar() 中只有返回非 None 时才平仓。
        """
        bars_held = self._bar_count - self._entry_bar
        entry_price = self._entry_price
        entry_atr = self._entry_atr or (entry_price * 0.01)

        # 更新持仓以来最高收盘价（移动止损基准）
        self._highest_close_since_entry = max(self._highest_close_since_entry, close)

        # --- 规则 1: 初始止损 ---
        initial_stop = entry_price - self.atr_multiplier * entry_atr
        if close <= initial_stop:
            return "initial_stop"

        # --- 规则 2: 信号反转（MACD 死叉 或 RSI 超买）---
        if (
            self._prev_macd_line is not None
            and self._prev_signal_ema is not None
            and self._cur_macd_line is not None
            and self._macd_signal_ema is not None
        ):
            # 死叉：上一根 DIF >= DEA，当前根 DIF < DEA
            if self._prev_macd_line >= self._prev_signal_ema and self._cur_macd_line < self._macd_signal_ema:
                return "signal_reversal_macd"
        rsi = self._rsi_value
        if rsi is not None and rsi > self.rsi_exit_high:
            return "signal_reversal_rsi"

        # --- 规则 3: ADX 休眠继承（ADX 跌破 sleep_threshold 超过 sleep_bars 根）---
        adx = self._i_adx_value
        if adx is not None:
            if adx < self.adx_sleep_threshold:
                self._adx_below_sleep_bars += 1
            else:
                self._adx_below_sleep_bars = 0

            if self._adx_below_sleep_bars >= self.adx_sleep_bars:
                # 收紧止损到保本价附近，触发休眠出场
                if close <= entry_price:
                    return "adx_sleep_inherit"
                # 若仍有浮盈，允许再等一根以更好价格出场；下一根强制
                if self._adx_below_sleep_bars >= self.adx_sleep_bars + 1:
                    return "adx_sleep_inherit_forced"

        # --- 规则 4: 移动止损（最高收盘价 - 1.5×ATR）---
        trailing_stop = self._highest_close_since_entry - self.atr_multiplier * entry_atr
        if close <= trailing_stop and self._highest_close_since_entry > entry_price:
            return "trailing_stop"

        # --- 规则 5: 保本保护激活后，价格跌回入场价以下 ---
        float_pnl_atr = (close - entry_price) / entry_atr if entry_atr > 0 else 0

        if float_pnl_atr >= 1.0 and not self._breakeven_activated:
            self._breakeven_activated = True
        if self._breakeven_activated and close <= entry_price:
            return "breakeven_stop"

        # --- 规则 6: 时间止损 ---
        if bars_held >= self.time_stop_bars and float_pnl_atr < 1.0:
            return "time_stop"

        return None

    # ==================================================================
    # 增量指标更新（实例级，无类变量共享问题）
    # ==================================================================

    def _update_i_adx(self, high: float, low: float, close: float) -> None:
        """实例级 ADX 计算（替代父类类变量版本，修复共享 bug）。"""
        n = self._i_adx_period
        self._i_adx_high_buf.append(high)
        self._i_adx_low_buf.append(low)
        self._i_adx_close_buf.append(close)

        if len(self._i_adx_high_buf) < n + 1:
            return

        # 截断保留 2n+1 个（足够计算 Wilder 平滑）
        keep = 2 * n + 1
        if len(self._i_adx_high_buf) > keep:
            self._i_adx_high_buf = self._i_adx_high_buf[-keep:]
            self._i_adx_low_buf = self._i_adx_low_buf[-keep:]
            self._i_adx_close_buf = self._i_adx_close_buf[-keep:]

        h = self._i_adx_high_buf
        lv = self._i_adx_low_buf
        c = self._i_adx_close_buf

        plus_dms, minus_dms, trs = [], [], []
        for i in range(1, len(h)):
            up_move = h[i] - h[i - 1]
            down_move = lv[i - 1] - lv[i]
            plus_dms.append(up_move if up_move > down_move and up_move > 0 else 0)
            minus_dms.append(down_move if down_move > up_move and down_move > 0 else 0)
            trs.append(max(h[i] - lv[i], abs(h[i] - c[i - 1]), abs(lv[i] - c[i - 1])))

        def wilder(vals: List[float]) -> float:
            r = vals[0]
            for v in vals[1:]:
                r = r * (n - 1) / n + v / n
            return r

        smooth_plus = wilder(plus_dms)
        smooth_minus = wilder(minus_dms)
        smooth_tr = wilder(trs)

        plus_di = 100 * smooth_plus / smooth_tr if smooth_tr > 0 else 0
        minus_di = 100 * smooth_minus / smooth_tr if smooth_tr > 0 else 0
        self._i_adx_plus_di = plus_di
        self._i_adx_minus_di = minus_di

        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0

        if self._i_adx_value is None:
            self._i_adx_value = dx
        else:
            self._i_adx_value = (self._i_adx_value * (n - 1) + dx) / n

        self._i_adx_initialized = True

    def _update_trend_ema(self, close: float) -> None:
        """更新用于趋势方向判断的 EMA（fast/slow）。"""
        af = 2.0 / (self.ema_fast_p + 1)
        as_ = 2.0 / (self.ema_slow_p + 1)
        self._ema_fast = close if self._ema_fast is None else self._ema_fast + af * (close - self._ema_fast)
        self._ema_slow = close if self._ema_slow is None else self._ema_slow + as_ * (close - self._ema_slow)

    def _update_macd(self, close: float) -> None:
        """
        更新 MACD。

        更新后状态语义：
          _prev_macd_line   = 上一根 MACD Line（本次 on_bar 开始前的值）
          _cur_macd_line    = 当前根 MACD Line（本次 on_bar 计算后的值）
          _prev_signal_ema  = 上一根 Signal Line
          _macd_signal_ema  = 当前根 Signal Line

        金叉条件：_prev_macd_line <= _prev_signal_ema  AND  _cur_macd_line > _macd_signal_ema
        死叉条件：_prev_macd_line >= _prev_signal_ema  AND  _cur_macd_line < _macd_signal_ema
        """
        af = 2.0 / (self.macd_fast_p + 1)
        as_ = 2.0 / (self.macd_slow_p + 1)
        sg = 2.0 / (self.macd_signal_p + 1)

        self._macd_fast_ema = (
            close if self._macd_fast_ema is None
            else self._macd_fast_ema + af * (close - self._macd_fast_ema)
        )
        self._macd_slow_ema = (
            close if self._macd_slow_ema is None
            else self._macd_slow_ema + as_ * (close - self._macd_slow_ema)
        )

        self._macd_bar_count += 1
        if self._macd_bar_count < self.macd_slow_p:
            return

        new_macd_line = self._macd_fast_ema - self._macd_slow_ema

        if self._macd_signal_ema is None:
            # 初始化：第一次有有效 MACD Line 时
            self._prev_macd_line = new_macd_line
            self._cur_macd_line = new_macd_line
            self._macd_signal_ema = new_macd_line
            self._prev_signal_ema = new_macd_line
        else:
            # 先把当前值存为"上一根"
            self._prev_macd_line = self._cur_macd_line
            self._prev_signal_ema = self._macd_signal_ema
            # 然后更新当前值
            self._cur_macd_line = new_macd_line
            self._macd_signal_ema = self._macd_signal_ema + sg * (new_macd_line - self._macd_signal_ema)

    def _update_rsi(self, close: float) -> None:
        """Wilder 平滑 RSI，同时保存上一根 RSI 用于拐头判断。"""
        if self._rsi_prev_close is None:
            self._rsi_prev_close = close
            return

        change = close - self._rsi_prev_close
        gain = max(change, 0.0)
        loss = abs(min(change, 0.0))
        self._rsi_prev_close = close

        n = self.rsi_period

        if self._rsi_avg_gain is None:
            # 初始化阶段：收集 n 个样本
            self._rsi_gain_init.append(gain)
            self._rsi_loss_init.append(loss)
            if len(self._rsi_gain_init) >= n:
                self._rsi_avg_gain = float(np.mean(self._rsi_gain_init))
                self._rsi_avg_loss = float(np.mean(self._rsi_loss_init))
                self._rsi_gain_init.clear()
                self._rsi_loss_init.clear()
        else:
            # Wilder 平滑
            self._rsi_avg_gain = (self._rsi_avg_gain * (n - 1) + gain) / n
            self._rsi_avg_loss = (self._rsi_avg_loss * (n - 1) + loss) / n

        if self._rsi_avg_gain is not None and self._rsi_avg_loss is not None:
            avg_loss = self._rsi_avg_loss
            self._rsi_prev_value = self._rsi_value  # 保存上一根 RSI
            if avg_loss == 0:
                self._rsi_value = 100.0
            else:
                rs = self._rsi_avg_gain / avg_loss
                self._rsi_value = 100.0 - 100.0 / (1.0 + rs)

    def _update_bb(self, close: float) -> None:
        """更新布林带价格缓冲区。"""
        self._bb_buffer.append(close)
        max_buf = self.bb_period * 3
        if len(self._bb_buffer) > max_buf:
            self._bb_buffer = self._bb_buffer[-max_buf:]

    def _get_bb_mid(self) -> Optional[float]:
        """返回布林带中轨（SMA），样本不足返回 None。"""
        if len(self._bb_buffer) < self.bb_period:
            return None
        return float(np.mean(self._bb_buffer[-self.bb_period:]))

    def get_bb(self) -> Optional[dict]:
        """返回完整布林带值（中轨/上轨/下轨）。"""
        if len(self._bb_buffer) < self.bb_period:
            return None
        recent = self._bb_buffer[-self.bb_period:]
        sma = float(np.mean(recent))
        std = float(np.std(recent, ddof=1))
        return {
            "middle": sma,
            "upper": sma + self.bb_std * std,
            "lower": sma - self.bb_std * std,
        }

    def _update_atr(self, high: float, low: float, close: float) -> None:
        """Wilder 平滑 ATR。"""
        if self._atr_prev_close is None:
            self._atr_prev_close = close
            return

        tr = max(high - low, abs(high - self._atr_prev_close), abs(low - self._atr_prev_close))
        self._atr_prev_close = close
        n = self.atr_period

        if self._atr_value is None:
            self._atr_init_tr.append(tr)
            if len(self._atr_init_tr) >= n:
                self._atr_value = float(np.mean(self._atr_init_tr))
                self._atr_init_tr.clear()
        else:
            self._atr_value = (self._atr_value * (n - 1) + tr) / n

    def get_status(self) -> dict:
        """返回当前指标状态（供前端 / 日志展示）。"""
        bb = self.get_bb()
        return {
            "adx": round(self._i_adx_value or 0, 1),
            "plus_di": round(self._i_adx_plus_di or 0, 1),
            "minus_di": round(self._i_adx_minus_di or 0, 1),
            "ema_fast": round(self._ema_fast or 0, 2),
            "ema_slow": round(self._ema_slow or 0, 2),
            "macd_line": round(self._cur_macd_line or 0, 4),
            "macd_signal": round(self._macd_signal_ema or 0, 4),
            "rsi": round(self._rsi_value or 0, 1),
            "bb_mid": round(bb["middle"], 2) if bb else 0,
            "bb_upper": round(bb["upper"], 2) if bb else 0,
            "bb_lower": round(bb["lower"], 2) if bb else 0,
            "atr": round(self._atr_value or 0, 2),
            "in_position": self._in_position,
            "entry_price": round(self._entry_price, 2),
            "bars_held": self._bar_count - self._entry_bar if self._in_position else 0,
            "highest_close": round(self._highest_close_since_entry, 2),
            "breakeven_activated": self._breakeven_activated,
            "adx_sleep_bars": self._adx_below_sleep_bars,
        }
