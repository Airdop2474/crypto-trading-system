"use client"

import { useState } from "react"
import useSWR from "swr"
import Link from "next/link"
import {
  TrendingUp,
  TrendingDown,
  Minus,
  RefreshCw,
  ExternalLink,
  AlertCircle,
  Inbox,
  Activity,
  Wallet,
  Target,
  Percent,
  Clock,
  ShieldAlert,
} from "lucide-react"
import { api } from "@/lib/api"
import { fmtNum, fmtSigned, fmtPct, pnlColor } from "@/lib/format"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ApiError } from "@/components/api-error"
import { cn } from "@/lib/utils"
import {
  ALL_MODES,
  MODE_LABEL,
  MODE_ICON,
  MODE_COLOR,
  STATUS_LABEL,
  STATUS_DOT_COLOR,
} from "@/lib/mode-meta"
import { STRATEGY_TYPE_LABEL, parseStrategyType } from "@/lib/strategy-meta"
import type { RunningMode, ModeResult, ModeResultTrade } from "@/lib/types"

const REFRESH_INTERVAL = 5_000

/** 根据 mode_status / exit_code / risk_state 推断运行结果状态 */
function inferStatus(r: ModeResult): { label: string; className: string } {
  if (r.mode_status === "running") {
    return { label: "运行中", className: "border-success/30 text-success bg-success/10" }
  }
  if (r.mode_status === "stopping") {
    return { label: "停止中", className: "border-warning/30 text-warning bg-warning/10" }
  }
  if (r.mode_status === "error" || (r.exit_code != null && r.exit_code !== 0)) {
    return { label: "异常退出", className: "border-destructive/30 text-destructive bg-destructive/10" }
  }
  if (r.risk_state === "STOPPED") {
    return { label: "风控停止", className: "border-warning/30 text-warning bg-warning/10" }
  }
  if (r.risk_state === "PAUSED" || r.strategy_paused) {
    return { label: "已暂停", className: "border-warning/30 text-warning bg-warning/10" }
  }
  return { label: "已完成", className: "border-success/30 text-success bg-success/10" }
}

export default function PaperPage() {
  const [selectedMode, setSelectedMode] = useState<RunningMode>("replay_paper")

  const { data: result, error, isLoading, mutate } = useSWR<ModeResult>(
    ["mode-result-page", selectedMode],
    () => api.getModeResult(selectedMode),
    { refreshInterval: REFRESH_INTERVAL, revalidateOnFocus: false },
  )

  const { data: modes } = useSWR(
    "modes-page",
    api.getModes,
    { refreshInterval: 3_000, revalidateOnFocus: false },
  )
  const modeState = modes?.find((m) => m.mode === selectedMode)

  return (
    <div className="flex flex-col gap-4 pb-16 md:pb-0">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Paper 交易结果</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            回放纸盘 / 实时纸盘 / Testnet 实盘的运行结果与收益详情
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link href="/system">
            <Button variant="outline" size="sm" className="h-8 gap-1.5 text-xs">
              <ExternalLink className="size-3" />
              前往运行控制
            </Button>
          </Link>
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 text-xs"
            onClick={() => mutate()}
            disabled={isLoading}
          >
            <RefreshCw className={cn("size-3", isLoading && "animate-spin")} />
            刷新
          </Button>
        </div>
      </div>

      {/* 模式切换 */}
      <div className="flex gap-2">
        {ALL_MODES.map((mode) => {
          const Icon = MODE_ICON[mode]
          const active = mode === selectedMode
          const st = modes?.find((m) => m.mode === mode)
          return (
            <button
              key={mode}
              onClick={() => setSelectedMode(mode)}
              className={cn(
                "flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm transition-colors",
                active
                  ? "border-primary bg-primary/10 text-foreground"
                  : "border-border bg-card text-muted-foreground hover:bg-secondary/50",
              )}
            >
              <div className={cn("flex size-6 items-center justify-center rounded border", MODE_COLOR[mode])}>
                <Icon className="size-3" />
              </div>
              <span className="font-medium">{MODE_LABEL[mode]}</span>
              {st && (
                <div className={cn("size-1.5 rounded-full", STATUS_DOT_COLOR[st.status])} />
              )}
            </button>
          )
        })}
      </div>

      {/* 内容区 */}
      {error ? (
        <ApiError error={error} onRetry={() => mutate()} title="结果加载失败" minHeight={300} />
      ) : isLoading || !result ? (
        <Card>
          <CardContent className="flex items-center justify-center py-20">
            <RefreshCw className="size-5 animate-spin text-muted-foreground" />
            <span className="ml-2 text-sm text-muted-foreground">加载中…</span>
          </CardContent>
        </Card>
      ) : !result.available ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-20 gap-3">
            <Inbox className="size-10 text-muted-foreground/50" />
            <div className="text-center">
              <p className="text-sm font-medium">暂无运行结果</p>
              <p className="text-xs text-muted-foreground mt-1">
                {MODE_LABEL[selectedMode]} 尚未产生检查点数据。请先在
                <Link href="/system" className="text-primary underline mx-1">运行控制</Link>
                页面启动该模式。
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <ResultContent result={result} modeStatus={modeState?.status ?? "idle"} uptime={modeState?.uptimeSeconds ?? null} />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// 结果内容
// ---------------------------------------------------------------------------
function ResultContent({
  result: r,
  modeStatus,
  uptime,
}: {
  result: ModeResult
  modeStatus: string
  uptime: number | null
}) {
  const status = inferStatus(r)
  const pnlIcon = r.realized_pnl > 0 ? TrendingUp : r.realized_pnl < 0 ? TrendingDown : Minus

  return (
    <>
      {/* 状态条 */}
      <Card>
        <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-2 p-4">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className={cn("text-xs h-6", status.className)}>
              {status.label}
            </Badge>
            {r.exit_code != null && modeStatus !== "running" && (
              <span className="text-xs text-muted-foreground">exit code: {r.exit_code}</span>
            )}
          </div>
          {modeStatus === "running" && uptime != null && (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Clock className="size-3" />
              已运行 {formatUptime(uptime)}
            </div>
          )}
          {r.last_bar_ts && (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Activity className="size-3" />
              数据截至 {String(r.last_bar_ts).slice(0, 19)}
            </div>
          )}
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <ShieldAlert className="size-3" />
            风控状态: <span className="font-mono text-foreground">{r.risk_state}</span>
          </div>
          {r.strategy_paused && (
            <Badge variant="outline" className="text-[10px] h-5 border-warning/30 text-warning">
              策略已暂停
            </Badge>
          )}
        </CardContent>
      </Card>

      {/* 总览指标 */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <OverviewCard
          title="总已实现盈亏"
          icon={pnlIcon}
          value={fmtSigned(r.realized_pnl)}
          valueClass={pnlColor(r.realized_pnl)}
          sub={`初始 ${fmtNum(r.initial_capital)}`}
        />
        <OverviewCard
          title="总收益率"
          icon={Percent}
          value={fmtPct(r.total_return_pct)}
          valueClass={pnlColor(r.total_return_pct)}
          sub={`最终权益 ${fmtNum(r.final_balance)}`}
        />
        <OverviewCard
          title="总交易笔数"
          icon={Target}
          value={String(r.total_trades)}
          sub={`${r.win_count} 胜 / ${r.loss_count} 负`}
        />
        <OverviewCard
          title="综合胜率"
          icon={Activity}
          value={r.total_trades > 0 ? `${fmtNum(r.win_rate, 1)}%` : "—"}
          sub={`运行 ${r.day_count} 天 · ${r.strategies.length} 策略`}
        />
      </div>

      {/* 按策略分卡显示 */}
      {r.strategies.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Wallet className="size-4 text-primary" />
            <h2 className="text-sm font-medium">策略结果明细</h2>
            <Badge variant="outline" className="text-[10px] h-5">
              {r.strategies.length} 个策略
            </Badge>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            {r.strategies.map((s) => {
              const retPct = s.return_pct
              const sPnlIcon = s.realized_pnl > 0 ? TrendingUp : s.realized_pnl < 0 ? TrendingDown : Minus
              // 该策略的最近交易
              const sTrades = r.recent_trades.filter((t) => t.strategy === s.strategy)
              return (
                <StrategyCard
                  key={s.strategy}
                  name={s.strategy}
                  realizedPnl={s.realized_pnl}
                  retPct={retPct}
                  totalTrades={s.total_trades}
                  winCount={s.win_count}
                  lossCount={s.loss_count}
                  winRate={s.win_rate}
                  finalBalance={s.final_balance}
                  dayCount={s.day_count}
                  riskState={s.risk_state}
                  strategyPaused={s.strategy_paused}
                  lastBarTs={s.last_bar_ts}
                  pnlIcon={sPnlIcon}
                  trades={sTrades}
                />
              )
            })}
          </div>
        </div>
      )}

      {/* 0 交易提示 */}
      {r.total_trades === 0 && r.risk_state === "STOPPED" && (
        <Card className="border-warning/30 bg-warning/5">
          <CardContent className="flex items-start gap-3 p-4">
            <AlertCircle className="mt-0.5 size-5 shrink-0 text-warning" />
            <div className="space-y-1.5">
              <p className="text-sm font-medium text-warning">风控已停止，无交易产生</p>
              <p className="text-xs text-muted-foreground">
                运行中某时刻风控被紧急停止（STOPPED），此后 <code className="font-mono">can_trade()</code> 一直返回 False，
                所有交易信号被阻止。常见触发原因：点击了「全局急停」按钮、API 发出急停信号、或持仓漂移熔断。
              </p>
              <p className="text-xs text-muted-foreground">
                STOPPED 不可自动恢复。恢复方式：前往
                <Link href="/system" className="text-primary underline mx-1">运行控制</Link>
                停止该模式，勾选「忽略旧检查点，全新启动」后重新启动即可；或点击「全面重置」清空全部数据后重启。
              </p>
            </div>
          </CardContent>
        </Card>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// 策略结果卡
// ---------------------------------------------------------------------------
function StrategyCard({
  name,
  realizedPnl,
  retPct,
  totalTrades,
  winCount,
  lossCount,
  winRate,
  finalBalance,
  dayCount,
  riskState,
  strategyPaused,
  lastBarTs,
  pnlIcon: PnlIcon,
  trades,
}: {
  name: string
  realizedPnl: number
  retPct: number
  totalTrades: number
  winCount: number
  lossCount: number
  winRate: number
  finalBalance: number
  dayCount: number
  riskState: string
  strategyPaused: boolean
  lastBarTs: string | null
  pnlIcon: typeof TrendingUp
  trades: ModeResultTrade[]
}) {
  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <span className="rounded bg-primary/10 px-2 py-0.5 font-mono text-xs text-primary">
              {(() => { const t = parseStrategyType(name); return t ? STRATEGY_TYPE_LABEL[t] : name; })()}
            </span>
          </CardTitle>
          <div className="flex items-center gap-1.5">
            <Badge
              variant="outline"
              className={cn(
                "text-[10px] h-5",
                riskState === "ACTIVE" && "border-success/30 text-success",
                riskState === "PAUSED" && "border-warning/30 text-warning",
                riskState === "STOPPED" && "border-destructive/30 text-destructive",
              )}
            >
              {riskState}
            </Badge>
            {strategyPaused && (
              <Badge variant="outline" className="text-[10px] h-5 border-warning/30 text-warning">
                暂停
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-3">
        {/* 策略指标 */}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-0.5">
            <p className="text-[10px] text-muted-foreground">已实现盈亏</p>
            <p className={cn("flex items-center gap-1 font-mono text-base font-semibold tabular-nums", pnlColor(realizedPnl))}>
              <PnlIcon className="size-3" />
              {fmtSigned(realizedPnl)}
            </p>
          </div>
          <div className="space-y-0.5">
            <p className="text-[10px] text-muted-foreground">收益率</p>
            <p className={cn("font-mono text-base font-semibold tabular-nums", pnlColor(retPct))}>
              {fmtPct(retPct)}
            </p>
          </div>
          <div className="space-y-0.5">
            <p className="text-[10px] text-muted-foreground">交易笔数</p>
            <p className="font-mono text-sm font-semibold tabular-nums">
              {totalTrades}
              <span className="ml-1 text-[10px] font-normal text-muted-foreground">
                ({winCount}胜/{lossCount}负)
              </span>
            </p>
          </div>
          <div className="space-y-0.5">
            <p className="text-[10px] text-muted-foreground">胜率</p>
            <p className="font-mono text-sm font-semibold tabular-nums">
              {totalTrades > 0 ? `${fmtNum(winRate, 1)}%` : "—"}
            </p>
          </div>
        </div>

        {/* 次要信息 */}
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-muted-foreground">
          <span>权益 <span className="font-mono text-foreground">{fmtNum(finalBalance)}</span></span>
          <span>运行 <span className="font-mono text-foreground">{dayCount}</span> 天</span>
          {lastBarTs && <span>截至 {String(lastBarTs).slice(0, 10)}</span>}
        </div>

        {/* 该策略最近交易 */}
        <div className="mt-auto border-t border-border/40 pt-2">
          <p className="mb-1.5 text-[10px] font-medium text-muted-foreground">
            最近交易 {trades.length > 0 && `(${trades.length})`}
          </p>
          {trades.length === 0 ? (
            <p className="py-2 text-center text-[10px] text-muted-foreground/60">无交易记录</p>
          ) : (
            <div className="space-y-0.5">
              {trades.slice(0, 5).map((t, i) => (
                <div key={i} className="flex items-center justify-between text-[11px]">
                  <span className="text-muted-foreground">
                    <span className="font-mono">{t.tag || "—"}</span>
                    <span className="ml-2">{String(t.time).slice(5, 16)}</span>
                  </span>
                  <span className={cn("font-mono tabular-nums", pnlColor(t.profit))}>
                    {fmtSigned(t.profit)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// 子组件
// ---------------------------------------------------------------------------
function OverviewCard({
  title,
  icon: Icon,
  value,
  sub,
  valueClass,
}: {
  title: string
  icon: typeof TrendingUp
  value: string
  sub?: string
  valueClass?: string
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-2 p-4">
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Icon className="size-3.5" />
          {title}
        </span>
        <p className={cn("font-mono text-xl font-semibold tabular-nums", valueClass)}>
          {value}
        </p>
        {sub && <p className="text-[11px] text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  )
}

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}
