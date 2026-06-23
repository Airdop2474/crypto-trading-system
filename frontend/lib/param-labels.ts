// 策略参数字段 → 中文标签映射
// 覆盖全部 12 个策略（grid / rsi / ma / buyhold / donchian /
// structure / supertrend / reversal / priceaction / bollinger / macd / composite）
//
// 同时保留 camelCase 与 snake_case 两种写法，兼容前后端不同命名风格。
export const PARAM_LABELS: Record<string, string> = {
  // ── grid ──
  lowerPrice: "网格下限",
  lower_price: "网格下限",
  upperPrice: "网格上限",
  upper_price: "网格上限",
  gridCount: "网格数量",
  grid_count: "网格数量",
  positionPerGrid: "每格仓位比例",
  position_per_grid: "每格仓位比例",
  enableFilters: "启用过滤器",
  enable_filters: "启用过滤器",

  // ── rsi ──
  rsiPeriod: "RSI 周期",
  rsi_period: "RSI 周期",
  oversold: "超卖阈值",
  overbought: "超买阈值",
  emaPeriod: "EMA 周期",
  ema_period: "EMA 周期",
  enableTrendFilter: "启用趋势过滤",
  enable_trend_filter: "启用趋势过滤",

  // ── ma ──
  short_window: "短期窗口",
  long_window: "长期窗口",

  // ── donchian ──
  trailing_atr_mult: " trailing ATR 倍数",
  atr_period: "ATR 周期",

  // ── structure ──
  // lookback 已定义，Donchian 也用 period

  // ── supertrend ──
  // period, multiplier 已定义

  // ── reversal ──
  pin_threshold: "Pin 阈值",
  stop_atr_mult: "止损 ATR 倍数",

  // ── priceaction ──
  lookback_structure: "结构回溯期",
  lookback_supplydemand: "供需区回溯期",
  lookback_liquidity: "流动性回溯期",
  min_pin_ratio: "最小 Pin 比率",
  confluence_threshold: "共振阈值",

  // ── bollinger ──
  bbPeriod: "布林带周期",
  bb_period: "布林带周期",
  bbStd: "布林带标准差",
  bb_std: "布林带标准差",
  // oversold / overbought 已定义
  positionFraction: "仓位比例",
  position_fraction: "仓位比例",

  // ── macd ──
  fastPeriod: "快线周期",
  fast_period: "快线周期",
  slowPeriod: "慢线周期",
  slow_period: "慢线周期",
  signalPeriod: "信号线周期",
  signal_period: "信号线周期",
  // position_fraction 已定义

  // ── composite ──
  adxPeriod: "ADX 周期",
  adx_period: "ADX 周期",
  adxThreshold: "ADX 阈值",
  adx_threshold: "ADX 阈值",
  enableAdxFilter: "启用 ADX 过滤",
  enable_adx_filter: "启用 ADX 过滤",
  emaFast: "快线 EMA",
  ema_fast: "快线 EMA",
  emaSlow: "慢线 EMA",
  ema_slow: "慢线 EMA",
  macd_fast: "MACD 快线",
  macd_slow: "MACD 慢线",
  macdSignal: "MACD 信号线",
  macd_signal: "MACD 信号线",
  rsiLow: "RSI 下限",
  rsi_low: "RSI 下限",
  rsiHigh: "RSI 上限",
  rsi_high: "RSI 上限",
  // bb_period, bb_std 已定义
  atr_multiplier: "ATR 倍数",
  riskPerTrade: "单笔风险",
  risk_per_trade: "单笔风险",
  time_stop_bars: "时间止损周期",
  adx_sleep_threshold: "ADX 休眠阈值",
  adx_sleep_bars: "ADX 休眠周期",

  // ── 通用 ──
  period: "周期",
  lookback: "回溯期",
  multiplier: "倍数",
  initialCapital: "初始资金",
  initial_capital: "初始资金",
}

export function getParamLabel(key: string): string {
  return PARAM_LABELS[key] ?? key
}
