// ============================================================================
// 策略元信息（共用映射）
// ----------------------------------------------------------------------------
// 全部 12 种策略的标签、颜色、图标统一定义在此，避免多策略面板与策略跑分
// 两处维护两套不一致的映射（参见 frontend-backend-gap-analysis 报告）。
//
// 策略 ID 约定：`<type>-<symbol-base>-usdt`，例如 `grid-btc-usdt`。
// 类型取自 StrategyType（lib/types.ts），共 12 种。
// ============================================================================

import {
  Activity,
  BarChart3,
  Building2,
  Gem,
  Grid3x3,
  Layers,
  RefreshCw,
  TrendingUp,
  Zap,
  GitMerge,
  LineChart,
  TrendingDown,
  type LucideIcon,
} from "lucide-react"

import type { StrategyType } from "./types"

/** 策略类型 → 中文短标签（全部 12 个） */
export const STRATEGY_TYPE_LABEL: Record<StrategyType, string> = {
  grid: "网格",
  rsi: "RSI 动量",
  ma: "均线",
  buyhold: "买入持有",
  donchian: "唐奇安通道",
  structure: "市场结构",
  supertrend: "超级趋势",
  reversal: "关键位反转",
  priceaction: "价格行为学",
  bollinger: "布林带均值回归",
  macd: "MACD 趋势跟踪",
  composite: "复合趋势",
}

/** 策略参数名 → 中文标签 */
export const PARAM_LABEL: Record<string, string> = {
  // 网格
  lower_price: "价格下限",
  upper_price: "价格上限",
  grid_count: "网格数量",
  position_per_grid: "每格仓位",
  enable_filters: "启用过滤",
  // RSI
  rsi_period: "RSI 周期",
  oversold: "超卖阈值",
  overbought: "超买阈值",
  ema_period: "EMA 周期",
  enable_trend_filter: "趋势过滤",
  // 均线
  short_window: "短期窗口",
  long_window: "长期窗口",
  // 唐奇安 / SuperTrend
  period: "周期",
  trailing_atr_mult: "ATR 止损倍数",
  atr_period: "ATR 周期",
  multiplier: "乘数",
  // 关键位反转
  lookback: "回溯长度",
  pin_threshold: "针形阈值",
  stop_atr_mult: "止损 ATR 倍数",
  // 价格行为
  lookback_structure: "结构回溯",
  lookback_supplydemand: "供需回溯",
  lookback_liquidity: "流动性回溯",
  min_pin_ratio: "最小针形比",
  confluence_threshold: "汇合阈值",
  // 布林带
  bb_period: "布林周期",
  bb_std: "标准差倍数",
  position_fraction: "仓位比例",
  // MACD
  fast_period: "快线周期",
  slow_period: "慢线周期",
  signal_period: "信号线周期",
  // 复合趋势
  adx_period: "ADX 周期",
  adx_threshold: "ADX 阈值",
  ema_fast: "快 EMA",
  ema_slow: "慢 EMA",
  macd_fast: "MACD 快线",
  macd_slow: "MACD 慢线",
  macd_signal: "MACD 信号线",
  rsi_low: "RSI 下限",
  rsi_high: "RSI 上限",
  atr_multiplier: "ATR 乘数",
  risk_per_trade: "单笔风险",
  time_stop_bars: "时间止损根数",
  adx_sleep_threshold: "ADX 休眠阈值",
  adx_sleep_bars: "ADX 休眠根数",
}

/** 获取参数中文标签，未知参数回退英文原名 */
export function getParamLabel(key: string): string {
  return PARAM_LABEL[key] || key
}

/** 策略类型 → 图标（全部 12 个） */
export const STRATEGY_TYPE_ICON: Record<StrategyType, LucideIcon> = {
  grid: Grid3x3,
  rsi: TrendingUp,
  ma: Activity,
  buyhold: Gem,
  donchian: Layers,
  structure: Building2,
  supertrend: Zap,
  reversal: RefreshCw,
  priceaction: BarChart3,
  bollinger: LineChart,
  macd: TrendingDown,
  composite: GitMerge,
}

/** 策略类型 → Tailwind 配色类（全部 12 个） */
export const STRATEGY_TYPE_COLOR: Record<StrategyType, string> = {
  grid: "bg-blue-500/20 text-blue-400",
  rsi: "bg-purple-500/20 text-purple-400",
  ma: "bg-amber-500/20 text-amber-400",
  buyhold: "bg-emerald-500/20 text-emerald-400",
  donchian: "bg-cyan-500/20 text-cyan-400",
  structure: "bg-rose-500/20 text-rose-400",
  supertrend: "bg-indigo-500/20 text-indigo-400",
  reversal: "bg-orange-500/20 text-orange-400",
  priceaction: "bg-slate-500/20 text-slate-400",
  bollinger: "bg-sky-500/20 text-sky-400",
  macd: "bg-violet-500/20 text-violet-400",
  composite: "bg-teal-500/20 text-teal-400",
}

/** fallback（未知 strategy_id 时） */
export const STRATEGY_FALLBACK_COLOR = "bg-gray-500/20 text-gray-400"
export const STRATEGY_FALLBACK_ICON = BarChart3

/**
 * 从 strategy_id（如 `grid-btc-usdt`）解析出 StrategyType。
 * 解析失败返回 null。
 */
export function parseStrategyType(strategyId: string): StrategyType | null {
  // strategy_id 形如 `<type>-<symbol-base>-usdt`，取第一段
  const head = strategyId.split("-")[0]
  if (head in STRATEGY_TYPE_LABEL) {
    return head as StrategyType
  }
  return null
}

/** 综合获取标签 + 颜色（用于 MultiStrategyPanel 等表格式展示） */
export function getStrategyLabelColor(strategyId: string): { label: string; color: string } {
  const type = parseStrategyType(strategyId)
  if (!type) {
    return { label: strategyId, color: STRATEGY_FALLBACK_COLOR }
  }
  return { label: STRATEGY_TYPE_LABEL[type], color: STRATEGY_TYPE_COLOR[type] }
}

/** 综合获取标签 + 图标（用于 StrategyPerformanceDashboard 等卡片式展示） */
export function getStrategyLabelIcon(strategyId: string): { label: string; LucideIcon: LucideIcon } {
  const type = parseStrategyType(strategyId)
  if (!type) {
    return { label: strategyId, LucideIcon: STRATEGY_FALLBACK_ICON }
  }
  return { label: STRATEGY_TYPE_LABEL[type], LucideIcon: STRATEGY_TYPE_ICON[type] }
}
