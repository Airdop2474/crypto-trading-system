// ============================================================================
// 策略元信息（共用映射）
// ----------------------------------------------------------------------------
// 全部 49 种策略的标签、颜色、图标统一定义在此，避免多策略面板与策略跑分
// 两处维护两套不一致的映射（参见 frontend-backend-gap-analysis 报告）。
//
// 策略 ID 约定：`<type>-<symbol-base>-usdt`，例如 `grid-btc-usdt`。
// 类型取自 StrategyType（lib/types.ts），共 49 种。
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

/** 策略类型 → 中文短标签（全部 49 个，与后端 registry.py _STRATEGY_LABELS 一致） */
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
  multilevel: "多级突破",
  squeeze: "持续收缩突破",
  strongmom: "强势收盘动量",
  purekeylvl: "纯关键位反转",
  confluence: "多信号共振",
  closebreak: "收盘突破",
  threesoldiers: "三兵",
  bigbar: "大实体",
  pinsmall: "Pin小实体",
  morningstar: "晨星",
  pullback: "回踩突破",
  ampbreak: "幅度突破",
  wicksweep: "影线扫损",
  confakeout: "连续假突",
  consmomentum: "连续动量",
  accmomentum: "递增动量",
  bullengulfseq: "阳包阴序列",
  shortlongsqz: "短长期收缩",
  insidechain: "内含线链",
  qualitysqz: "质量突破",
  decaykey: "降权关键位",
  multiwinkey: "多窗口关键位",
  weightedvote: "加权投票",
  requiredcat: "必含项",
  masterslave: "主从",
  sessionfilter: "时段过滤",
  dayofweek: "周内效应",
  monthpos: "月内位置",
  closemonotonic: "收盘单调",
  hlexpansion: "高低点扩散",
  closedist: "收盘分布",
  mtfconfluence: "多周期共振",
  dualbreakout: "双窗口突破",
  tfdivergence: "周期背离",
  volbreakout: "放量突破",
  volpricediv: "量价背离",
  takerbuyratio: "主动买盘比",
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

/** 策略类型 → 图标（全部 49 个，新策略复用现有图标） */
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
  // 新增 37 个策略：复用现有图标（按策略语义分组）
  multilevel: Layers,
  squeeze: GitMerge,
  strongmom: TrendingUp,
  purekeylvl: RefreshCw,
  confluence: GitMerge,
  closebreak: BarChart3,
  threesoldiers: TrendingUp,
  bigbar: BarChart3,
  pinsmall: BarChart3,
  morningstar: TrendingUp,
  pullback: TrendingUp,
  ampbreak: Zap,
  wicksweep: RefreshCw,
  confakeout: BarChart3,
  consmomentum: TrendingUp,
  accmomentum: TrendingUp,
  bullengulfseq: TrendingUp,
  shortlongsqz: GitMerge,
  insidechain: BarChart3,
  qualitysqz: GitMerge,
  decaykey: RefreshCw,
  multiwinkey: RefreshCw,
  weightedvote: GitMerge,
  requiredcat: GitMerge,
  masterslave: GitMerge,
  sessionfilter: Activity,
  dayofweek: Activity,
  monthpos: Activity,
  closemonotonic: TrendingUp,
  hlexpansion: Layers,
  closedist: BarChart3,
  mtfconfluence: GitMerge,
  dualbreakout: Layers,
  tfdivergence: Activity,
  volbreakout: Zap,
  volpricediv: Activity,
  takerbuyratio: BarChart3,
}

/** 策略类型 → Tailwind 配色类（全部 49 个，新策略复用现有色系） */
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
  // 新增 37 个策略：复用现有色系（按策略语义分组）
  multilevel: "bg-cyan-500/20 text-cyan-400",
  squeeze: "bg-teal-500/20 text-teal-400",
  strongmom: "bg-purple-500/20 text-purple-400",
  purekeylvl: "bg-orange-500/20 text-orange-400",
  confluence: "bg-teal-500/20 text-teal-400",
  closebreak: "bg-slate-500/20 text-slate-400",
  threesoldiers: "bg-purple-500/20 text-purple-400",
  bigbar: "bg-slate-500/20 text-slate-400",
  pinsmall: "bg-slate-500/20 text-slate-400",
  morningstar: "bg-purple-500/20 text-purple-400",
  pullback: "bg-purple-500/20 text-purple-400",
  ampbreak: "bg-indigo-500/20 text-indigo-400",
  wicksweep: "bg-orange-500/20 text-orange-400",
  confakeout: "bg-slate-500/20 text-slate-400",
  consmomentum: "bg-purple-500/20 text-purple-400",
  accmomentum: "bg-purple-500/20 text-purple-400",
  bullengulfseq: "bg-purple-500/20 text-purple-400",
  shortlongsqz: "bg-teal-500/20 text-teal-400",
  insidechain: "bg-slate-500/20 text-slate-400",
  qualitysqz: "bg-teal-500/20 text-teal-400",
  decaykey: "bg-orange-500/20 text-orange-400",
  multiwinkey: "bg-orange-500/20 text-orange-400",
  weightedvote: "bg-teal-500/20 text-teal-400",
  requiredcat: "bg-teal-500/20 text-teal-400",
  masterslave: "bg-teal-500/20 text-teal-400",
  sessionfilter: "bg-amber-500/20 text-amber-400",
  dayofweek: "bg-amber-500/20 text-amber-400",
  monthpos: "bg-amber-500/20 text-amber-400",
  closemonotonic: "bg-purple-500/20 text-purple-400",
  hlexpansion: "bg-cyan-500/20 text-cyan-400",
  closedist: "bg-slate-500/20 text-slate-400",
  mtfconfluence: "bg-teal-500/20 text-teal-400",
  dualbreakout: "bg-cyan-500/20 text-cyan-400",
  tfdivergence: "bg-amber-500/20 text-amber-400",
  volbreakout: "bg-indigo-500/20 text-indigo-400",
  volpricediv: "bg-amber-500/20 text-amber-400",
  takerbuyratio: "bg-slate-500/20 text-slate-400",
}

/** fallback（未知 strategy_id 时） */
export const STRATEGY_FALLBACK_COLOR = "bg-gray-500/20 text-gray-400"
export const STRATEGY_FALLBACK_ICON = BarChart3

// ============================================================================
// 策略分类（7 类，覆盖全部 49 个策略）
// ----------------------------------------------------------------------------
// 分类依据：策略核心逻辑语义
//   trend     - 趋势跟踪：顺势而为，追涨杀跌
//   reversal  - 均值回归：逆势反转，超买卖出/跌深买入
//   breakout  - 突破：关键位突破入场
//   pattern   - K 线形态：特定 K 线组合
//   confluence- 多因子共振：多信号投票/共振
//   time      - 时间过滤：按时段/周期限制交易
//   baseline  - 基准/网格：基础策略
// ============================================================================

export type StrategyCategory =
  | "trend"
  | "reversal"
  | "breakout"
  | "pattern"
  | "confluence"
  | "time"
  | "baseline"

/** 策略类型 → 分类 */
export const STRATEGY_TYPE_CATEGORY: Record<StrategyType, StrategyCategory> = {
  // 趋势跟踪
  ma: "trend",
  supertrend: "trend",
  macd: "trend",
  composite: "trend",
  strongmom: "trend",
  consmomentum: "trend",
  accmomentum: "trend",
  closemonotonic: "trend",
  hlexpansion: "trend",
  closedist: "trend",
  // 均值回归 / 反转
  rsi: "reversal",
  reversal: "reversal",
  priceaction: "reversal",
  bollinger: "reversal",
  purekeylvl: "reversal",
  wicksweep: "reversal",
  confakeout: "reversal",
  decaykey: "reversal",
  multiwinkey: "reversal",
  tfdivergence: "reversal",
  volpricediv: "reversal",
  // 突破
  donchian: "breakout",
  structure: "breakout",
  multilevel: "breakout",
  squeeze: "breakout",
  closebreak: "breakout",
  pullback: "breakout",
  ampbreak: "breakout",
  shortlongsqz: "breakout",
  insidechain: "breakout",
  qualitysqz: "breakout",
  dualbreakout: "breakout",
  volbreakout: "breakout",
  takerbuyratio: "breakout",
  // K 线形态
  threesoldiers: "pattern",
  bigbar: "pattern",
  pinsmall: "pattern",
  morningstar: "pattern",
  bullengulfseq: "pattern",
  // 多因子共振
  confluence: "confluence",
  weightedvote: "confluence",
  requiredcat: "confluence",
  masterslave: "confluence",
  mtfconfluence: "confluence",
  // 时间过滤
  sessionfilter: "time",
  dayofweek: "time",
  monthpos: "time",
  // 基准 / 网格
  grid: "baseline",
  buyhold: "baseline",
}

/** 分类 → 中文名 + 描述 */
export const STRATEGY_CATEGORY_LABEL: Record<StrategyCategory, string> = {
  trend: "趋势跟踪",
  reversal: "均值回归",
  breakout: "突破",
  pattern: "K线形态",
  confluence: "多因子共振",
  time: "时间过滤",
  baseline: "基准/网格",
}

export const STRATEGY_CATEGORY_DESCRIPTION: Record<StrategyCategory, string> = {
  trend: "顺势而为，追涨杀跌的趋势策略",
  reversal: "逆势反转，超买卖出或跌深买入",
  breakout: "关键位突破入场",
  pattern: "特定 K 线组合形态",
  confluence: "多信号投票或共振确认",
  time: "按时段或周期限制交易",
  baseline: "基础策略（网格/持有）",
}

/** 所有分类，按固定顺序排列（用于下拉/Tab 展示） */
export const STRATEGY_CATEGORIES: StrategyCategory[] = [
  "trend",
  "reversal",
  "breakout",
  "pattern",
  "confluence",
  "time",
  "baseline",
]

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
