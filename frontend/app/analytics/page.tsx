"use client"

import useSWR from "swr"
import { api } from "@/lib/api"
import { fmtPct, fmtSigned, pnlColor } from "@/lib/format"
import { StatCard } from "@/components/stat-card"
import { CumulativePnl } from "@/components/analytics/cumulative-pnl"
import { DailyPnl } from "@/components/analytics/daily-pnl"
import { StrategyComparison } from "@/components/analytics/strategy-comparison"

export default function AnalyticsPage() {
  const { data: pnl, isLoading: pnlLoading } = useSWR("pnl-history", api.getPnlHistory)
  const { data: perf, isLoading: perfLoading } = useSWR("strategy-performance", api.getStrategyPerformance)

  const points = pnl ?? []
  const totalPnl = points.length ? points[points.length - 1].cumulativePnl : 0
  const winDays = points.filter((p) => p.pnl > 0).length
  const winRate = points.length ? (winDays / points.length) * 100 : 0
  const bestDay = points.reduce((m, p) => (p.pnl > m ? p.pnl : m), 0)
  const worstDay = points.reduce((m, p) => (p.pnl < m ? p.pnl : m), 0)

  return (
    <div className="flex flex-col gap-4 pb-16 md:pb-0">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="区间累计盈亏" value={fmtSigned(totalPnl)} valueClassName={pnlColor(totalPnl)} loading={pnlLoading} />
        <StatCard label="盈利天数占比" value={fmtPct(winRate).replace("+", "")} loading={pnlLoading} />
        <StatCard label="单日最佳" value={fmtSigned(bestDay)} valueClassName="text-success" loading={pnlLoading} />
        <StatCard label="单日最差" value={fmtSigned(worstDay)} valueClassName="text-destructive" loading={pnlLoading} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <CumulativePnl data={points} loading={pnlLoading} />
        <DailyPnl data={points} loading={pnlLoading} />
      </div>

      <StrategyComparison data={perf ?? []} loading={perfLoading} />
    </div>
  )
}
