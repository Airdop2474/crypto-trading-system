// ============================================================================
// 策略元信息（共用映射）
// ----------------------------------------------------------------------------
// 全部 8 种策略的标签、颜色、图标统一定义在此，避免多策略面板与策略跑分
// 两处维护两套不一致的映射（参见 frontend-backend-gap-analysis 报告）。
//
// 策略 ID 约定：`<type>-<symbol-base>-usdt`，例如 `grid-btc-usdt`。
// 类型取自 StrategyType（lib/types.ts），共 8 种。
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
  type LucideIcon,
} from "lucide-react"

import type { StrategyType } from "./types"

/** 策略类型 → 中文短标签 */
export const STRATEGY_TYPE_LABEL: Record<StrategyType, string> = {
  grid: "网格",
  rsi: "RSI 动量",
  ma: "均线",
  buyhold: "买入持有",
  donchian: "唐奇安通道",
  structure: "市场结构",
  supertrend: "SuperTrend",
  reversal: "关键位反转",
  priceaction: "价格行为学",
}

/** 策略类型 → 图标 */
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
}

/** 策略类型 → Tailwind 配色类（用于 Badge / 标签底色） */
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
