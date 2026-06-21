"use client"

import { useMemo } from "react"
import useSWR from "swr"
import { BarChart3, TrendingUp } from "lucide-react"
import { api } from "@/lib/api"
import { fmtSigned, fmtPct } from "@/lib/format"
import { getStrategyLabelIcon } from "@/lib/strategy-meta"
import type { MultiStrategyDetail, MultiStrategySummary } from "@/lib/types"

export function StrategyPerformanceDashboard() {
  const { data: summary, error: summaryError } = useSWR<MultiStrategySummary>(
    "multi-summary",
    () => api.getMultiSummary(),
    { suspense: false }
  )
  const { data: details, error: detailsError } = useSWR<MultiStrategyDetail[]>(
    "multi-details",
    () => api.getMultiDetails(),
    { suspense: false }
  )

  const isLoading = !summary && !details && !summaryError && !detailsError
  const hasError = summaryError ?? detailsError

  const { sorted, maxAbsPnl } = useMemo(() => {
    if (!details) return { sorted: [], maxAbsPnl: 1 }
    const s = [...details].sort((a, b) => b.realizedPnl - a.realizedPnl)
    const maxAbs = Math.max(...s.map((x) => Math.abs(x.realizedPnl)), 1)
    return { sorted: s, maxAbsPnl: maxAbs }
  }, [details])

  if (isLoading) {
    return (
      <div className="rounded-xl border border-border bg-card p-6 animate-pulse" aria-hidden="true">
        <div className="h-5 w-36 rounded bg-muted/60 mb-4" />
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-12 rounded bg-muted/40" />
          ))}
        </div>
      </div>
    )
  }

  if (hasError || !sorted.length) {
    return (
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-2 mb-2">
          <BarChart3 className="h-5 w-5 text-muted-foreground" />
          <h3 className="font-semibold text-sm">策略跑分</h3>
        </div>
        <p className="text-sm text-muted-foreground">
          {hasError ? "加载策略跑分失败" : "暂无策略数据"}
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-5 w-5 text-primary" />
          <h3 className="font-semibold text-sm">
            策略跑分 · {sorted.length} 个策略
          </h3>
        </div>
        {summary && (
          <span className="text-xs text-muted-foreground">
            总盈亏 {fmtSigned(summary.totalRealizedPnl)}
          </span>
        )}
      </div>

      <div className="space-y-2">
        {sorted.map((s) => {
          const { label, LucideIcon: Icon } = getStrategyLabelIcon(s.strategyId)
          const isPositive = s.realizedPnl >= 0
          const barWidth = Math.max(
            (Math.abs(s.realizedPnl) / maxAbsPnl) * 100,
            3
          )

          return (
            <div
              key={s.strategyId}
              className="group flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors hover:bg-muted/30"
            >
              <Icon className="h-5 w-5 shrink-0 text-muted-foreground" />

              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium truncate">
                    {label}
                  </span>
                  <span
                    className={`text-sm font-mono tabular-nums ${
                      isPositive ? "text-success" : "text-destructive"
                    }`}
                  >
                    {fmtSigned(s.realizedPnl)}
                  </span>
                </div>

                <div className="relative h-2 w-full rounded-full bg-muted/50 overflow-hidden">
                  <div
                    className={`absolute inset-y-0 left-0 rounded-full transition-all duration-500 ${
                      isPositive
                        ? "bg-success/70"
                        : "bg-destructive/70"
                    }`}
                    style={{ width: `${barWidth}%` }}
                  />
                </div>

                <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
                  <span className="flex items-center gap-1">
                    <TrendingUp className="h-3 w-3" />
                    {s.totalTrades} 交易
                  </span>
                  <span>
                    胜率 {fmtPct(s.winRate)}
                  </span>
                  <span>
                    开仓 {s.openLots} · 平仓 {s.closedTrades}
                  </span>
                </div>
              </div>

              <div
                className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
                  s.winRate >= 60
                    ? "bg-success/10 text-success"
                    : s.winRate >= 40
                    ? "bg-warning/10 text-warning"
                    : "bg-destructive/10 text-destructive"
                }`}
              >
                {s.winRate.toFixed(0)}%
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
