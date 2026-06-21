"use client"

import { useStrategies } from "@/hooks/use-strategies"
import { fmtSigned, pnlColor } from "@/lib/format"
import { StatCard } from "@/components/stat-card"
import { PaCard } from "@/components/price-action/pa-card"
import { ApiError } from "@/components/api-error"

// 价格行为相关策略类型（Donchian / Structure / SuperTrend / Reversal）
const PA_TYPES = ["donchian", "structure", "supertrend", "reversal"] as const

export default function PriceActionPage() {
  const { strategies, isLoading, error, setStatus, mutate } = useStrategies()
  const list = strategies.filter((s) => PA_TYPES.includes(s.type as typeof PA_TYPES[number]))

  const totalPnl = list.reduce((a, s) => a + s.pnl, 0)
  const running = list.filter((s) => s.status === "running").length

  return (
    <div className="flex flex-col gap-4 pb-16 md:pb-0">
      <p className="text-sm text-muted-foreground">
        基于技术指标与价格行为的高胜率趋势策略
      </p>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <StatCard label="策略总盈亏" value={fmtSigned(totalPnl)} subClassName={pnlColor(totalPnl)} loading={isLoading} />
        <StatCard label="运行中策略" value={`${running} / ${list.length}`} loading={isLoading} />
        <StatCard label="活跃策略数" value={String(running)} loading={isLoading} />
      </div>

      {error ? (
        <ApiError error={error} onRetry={() => mutate()} title="策略列表加载失败" minHeight={288} />
      ) : isLoading ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-72 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      ) : list.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <p className="text-lg font-medium">暂无活跃的价格行为策略</p>
          <p className="text-sm mt-1">启动 Donchian、Structure、SuperTrend 或 Reversal 策略后将在此显示</p>
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
