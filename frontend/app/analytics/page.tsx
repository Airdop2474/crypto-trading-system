"use client"

import useSWR from "swr"
import { api } from "@/lib/api"
import { fmtPct, fmtSigned, pnlColor } from "@/lib/format"
import { StatCard } from "@/components/stat-card"
import { CumulativePnl } from "@/components/analytics/cumulative-pnl"
import { DailyPnl } from "@/components/analytics/daily-pnl"
import { StrategyComparison } from "@/components/analytics/strategy-comparison"
import { DrawdownCurveCard } from "@/components/analytics/drawdown-curve-card"
import { WinRateTrendCard } from "@/components/analytics/win-rate-trend-card"
import { StrategyCorrelationCard } from "@/components/analytics/strategy-correlation-card"
import { ApiError } from "@/components/api-error"
import { ExportButton } from "@/components/export-button"
import { ErrorBoundary } from "@/components/error-boundary"
import type { CsvColumn } from "@/lib/csv"
import type { PnlPoint } from "@/lib/types"

const pnlColumns: CsvColumn<PnlPoint>[] = [
  { key: "date", label: "日期" },
  { key: "equity", label: "账户权益" },
  { key: "pnl", label: "当日盈亏" },
  { key: "cumulativePnl", label: "累计盈亏" },
]

export default function AnalyticsPage() {
  const { data: pnl, isLoading: pnlLoading, error: pnlError, mutate: reloadPnl } = useSWR("pnl-history", api.getPnlHistory)
  const { data: perf, isLoading: perfLoading, error: perfError, mutate: reloadPerf } = useSWR("strategy-performance", api.getStrategyPerformance)

  const points = pnl ?? []
  const totalPnl = points.length ? points[points.length - 1].cumulativePnl : 0
  const winDays = points.filter((p) => p.pnl > 0).length
  const winRate = points.length ? (winDays / points.length) * 100 : 0
  const bestDay = points.length ? Math.max(...points.map((p) => p.pnl)) : 0
  const worstDay = points.length ? Math.min(...points.map((p) => p.pnl)) : 0

  return (
    <ErrorBoundary>
    <div className="flex flex-col gap-4 pb-16 md:pb-0">
      <div className="flex items-center justify-end">
        <ExportButton
          rows={points}
          columns={pnlColumns}
          filenamePrefix="pnl-history"
          disabled={pnlLoading || points.length === 0}
          label="导出盈亏数据"
        />
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="区间累计盈亏" value={fmtSigned(totalPnl)} valueClassName={pnlColor(totalPnl)} loading={pnlLoading} />
        <StatCard label="盈利天数占比" value={fmtPct(winRate).replace("+", "")} loading={pnlLoading} />
        <StatCard label="单日最佳" value={fmtSigned(bestDay)} valueClassName="text-success" loading={pnlLoading} />
        <StatCard label="单日最差" value={fmtSigned(worstDay)} valueClassName="text-destructive" loading={pnlLoading} />
      </div>

      {pnlError ? (
        <ApiError error={pnlError} onRetry={() => reloadPnl()} title="盈亏曲线加载失败" />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <CumulativePnl data={points} loading={pnlLoading} />
          <DailyPnl data={points} loading={pnlLoading} />
        </div>
      )}

      {/* 新增多维分析图 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <WinRateTrendCard />
        <DrawdownCurveCard />
      </div>

      {perfError ? (
        <ApiError error={perfError} onRetry={() => reloadPerf()} title="策略对比加载失败" />
      ) : (
        <StrategyComparison data={perf ?? []} loading={perfLoading} />
      )}

      <StrategyCorrelationCard />
    </div>
    </ErrorBoundary>
  )
}
