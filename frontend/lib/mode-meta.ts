// ============================================================================
// 运行模式元信息（共用映射）
// ----------------------------------------------------------------------------
// 三种运行模式的标签、描述、图标、配色统一定义在此。
// ============================================================================

import {
  FastForward,
  Radio,
  FlaskConical,
  type LucideIcon,
} from "lucide-react"

import type { RunningMode } from "./types"

/** 模式 → 中文短标签 */
export const MODE_LABEL: Record<RunningMode, string> = {
  replay_paper: "回放纸盘",
  live_paper: "实时纸盘",
  testnet_live: "Testnet 实盘",
}

/** 模式 → 描述 */
export const MODE_DESCRIPTION: Record<RunningMode, string> = {
  replay_paper: "使用历史数据加速回放纸盘交易（自动生成数据）",
  live_paper: "实时轮询 Binance 行情，模拟纸盘交易",
  testnet_live: "在 Binance Testnet 上下真实市价单",
}

/** 模式 → 图标 */
export const MODE_ICON: Record<RunningMode, LucideIcon> = {
  replay_paper: FastForward,
  live_paper: Radio,
  testnet_live: FlaskConical,
}

/** 模式 → 配色 (Tailwind class) */
export const MODE_COLOR: Record<RunningMode, string> = {
  replay_paper: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  live_paper: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  testnet_live: "bg-rose-500/20 text-rose-400 border-rose-500/30",
}

/** 模式 → 状态指示灯颜色 */
export const STATUS_DOT_COLOR: Record<string, string> = {
  idle: "bg-muted-foreground/40",
  running: "bg-success animate-pulse",
  stopping: "bg-warning animate-pulse",
  error: "bg-destructive",
}

/** 模式 → 状态中文标签 */
export const STATUS_LABEL: Record<string, string> = {
  idle: "空闲",
  running: "运行中",
  stopping: "停止中",
  error: "异常",
}

/** 交易模式列表（互斥组） */
export const TRADING_MODES: RunningMode[] = ["replay_paper", "live_paper", "testnet_live"]

/** 全部模式列表（有序） */
export const ALL_MODES: RunningMode[] = ["replay_paper", "live_paper", "testnet_live"]

/** 模式 → 可配置参数默认值 */
export const MODE_DEFAULTS: Record<RunningMode, {
  symbol: string
  timeframe: string
  days: number
  initialCapital: number
  pollSeconds: number
  showPollSeconds: boolean
  showReplayCsv: boolean
  showMarketType: boolean
}> = {
  replay_paper: {
    symbol: "BTC/USDT",
    timeframe: "1h",
    days: 20,
    initialCapital: 10000,
    pollSeconds: 60,
    showPollSeconds: false,
    showReplayCsv: true,
    showMarketType: true,
  },
  live_paper: {
    symbol: "BTC/USDT",
    timeframe: "1h",
    days: 20,
    initialCapital: 10000,
    pollSeconds: 60,
    showPollSeconds: true,
    showReplayCsv: false,
    showMarketType: false,
  },
  testnet_live: {
    symbol: "BTC/USDT",
    timeframe: "1h",
    days: 20,
    initialCapital: 10000,
    pollSeconds: 60,
    showPollSeconds: true,
    showReplayCsv: false,
    showMarketType: false,
  },
}