"use client"

import type { Strategy, StrategyStatus } from "@/lib/types"
import { fmtPct, fmtSigned, fmtUsd, pnlColor } from "@/lib/format"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { StrategyStatusBadge } from "@/components/status-badge"
import { StrategyControls } from "@/components/strategy-controls"
import { GridVisual } from "@/components/grid/grid-visual"

interface Props {
  strategy: Strategy
  onSetStatus: (id: string, status: StrategyStatus) => void
}

export function GridCard({ strategy, onSetStatus }: Props) {
  const g = strategy.grid!
  const fillPct = (g.filledGrids / g.gridCount) * 100

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold">{strategy.name}</h3>
            <StrategyStatusBadge status={strategy.status} />
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {strategy.symbol} · 已运行 {strategy.runningDays} 天
          </p>
        </div>
        <div className="text-right">
          <p className={`font-mono text-lg font-semibold tabular-nums ${pnlColor(strategy.pnl)}`}>
            {fmtSigned(strategy.pnl)}
          </p>
          <p className={`font-mono text-xs tabular-nums ${pnlColor(strategy.pnl)}`}>
            {fmtPct(strategy.pnlPct)}
          </p>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <GridVisual strategy={strategy} />

        <div className="grid grid-cols-3 gap-3 text-center">
          <Metric label="网格数" value={String(g.gridCount)} />
          <Metric label="每格利润" value={`${g.perGridProfit}%`} />
          <Metric label="套利次数" value={g.arbitrageCount.toLocaleString()} />
          <Metric label="投入本金" value={fmtUsd(strategy.investment, 0)} />
          <Metric label="区间宽度" value={`${(((g.upperPrice - g.lowerPrice) / g.lowerPrice) * 100).toFixed(1)}%`} />
          <Metric label="已成交格" value={`${g.filledGrids}/${g.gridCount}`} />
        </div>

        <div>
          <div className="mb-1 flex justify-between text-[11px] text-muted-foreground">
            <span>网格填充度</span>
            <span className="font-mono tabular-nums">{fillPct.toFixed(0)}%</span>
          </div>
          <Progress value={fillPct} className="h-1.5" />
        </div>

        <div className="flex items-center justify-end border-t border-border/60 pt-3">
          <StrategyControls strategy={strategy} onSetStatus={onSetStatus} />
        </div>
      </CardContent>
    </Card>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-secondary/40 px-2 py-1.5">
      <p className="font-mono text-sm font-medium tabular-nums">{value}</p>
      <p className="text-[10px] text-muted-foreground">{label}</p>
    </div>
  )
}
