"use client"

import { useStrategies } from "@/hooks/use-strategies"
import { fmtSigned, pnlColor } from "@/lib/format"
import { StatCard } from "@/components/stat-card"
import { PaCard } from "@/components/price-action/pa-card"

export default function PriceActionPage() {
  const { strategies, isLoading, setStatus } = useStrategies()
  const list = strategies.filter((s) => s.type === "price-action")

  const totalPnl = list.reduce((a, s) => a + s.pnl, 0)
  const running = list.filter((s) => s.status === "running").length
  const avgStrength =
    list.length > 0
      ? Math.round(list.reduce((a, s) => a + (s.priceAction?.signalStrength ?? 0), 0) / list.length)
      : 0
  const strongSignals = list.filter((s) => (s.priceAction?.signalStrength ?? 0) >= 70).length

  return (
    <div className="flex flex-col gap-4 pb-16 md:pb-0">
      <p className="text-sm text-muted-foreground">
        基于 K 线形态与价格行为信号的趋势捕捉策略
      </p>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="策略总盈亏" value={fmtSigned(totalPnl)} subClassName={pnlColor(totalPnl)} loading={isLoading} />
        <StatCard label="运行中策略" value={`${running} / ${list.length}`} loading={isLoading} />
        <StatCard label="平均信号强度" value={String(avgStrength)} loading={isLoading} />
        <StatCard label="强信号数量" value={String(strongSignals)} sub="强度 ≥ 70" subClassName="text-muted-foreground" loading={isLoading} />
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-72 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {list.map((s) => (
            <PaCard key={s.id} strategy={s} onSetStatus={setStatus} />
          ))}
        </div>
      )}
    </div>
  )
}
