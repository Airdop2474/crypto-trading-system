"use client"

import { useStrategies } from "@/hooks/use-strategies"
import { fmtSigned, fmtUsd, pnlColor } from "@/lib/format"
import { StatCard } from "@/components/stat-card"
import { CreateGridDialog } from "@/components/grid/create-grid-dialog"
import { GridCard } from "@/components/grid/grid-card"
import { ApiError } from "@/components/api-error"
import { ErrorBoundary } from "@/components/error-boundary"

export default function GridPage() {
  const { strategies, isLoading, error, setStatus, mutate } = useStrategies()
  const grids = strategies.filter((s) => s.type === "grid")

  const totalPnl = grids.reduce((a, s) => a + s.pnl, 0)
  const totalInvest = grids.reduce((a, s) => a + s.investment, 0)
  const running = grids.filter((s) => s.status === "running").length
  const totalArb = grids.reduce((a, s) => a + (s.grid?.arbitrageCount ?? 0), 0)

  return (
    <ErrorBoundary>
    <div className="flex flex-col gap-4 pb-16 md:pb-0">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          管理自动化网格策略，监控区间套利表现
        </p>
        <CreateGridDialog />
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="网格总盈亏" value={fmtSigned(totalPnl)} subClassName={pnlColor(totalPnl)} loading={isLoading} />
        <StatCard label="总投入本金" value={fmtUsd(totalInvest, 0)} loading={isLoading} />
        <StatCard label="运行中网格" value={`${running} / ${grids.length}`} loading={isLoading} />
        <StatCard label="累计套利次数" value={totalArb.toLocaleString()} loading={isLoading} />
      </div>

      {error ? (
        <ApiError error={error} onRetry={() => mutate()} title="策略列表加载失败" minHeight={320} />
      ) : isLoading ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-80 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {grids.map((s) => (
            <GridCard key={s.id} strategy={s} onSetStatus={setStatus} />
          ))}
        </div>
      )}
    </div>
    </ErrorBoundary>
  )
}
