"use client"

import { Clock, Target, ShieldAlert } from "lucide-react"
import type { Strategy, StrategyStatus } from "@/lib/types"
import { cn } from "@/lib/utils"
import { fmtNum, fmtPct, fmtSigned, fmtUsd, pnlColor } from "@/lib/format"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { StrategyStatusBadge } from "@/components/status-badge"
import { StrategyControls } from "@/components/strategy-controls"

interface Props {
  strategy: Strategy
  onSetStatus: (id: string, status: StrategyStatus) => void
}

function strengthColor(v: number) {
  if (v >= 70) return "text-success"
  if (v >= 50) return "text-primary"
  return "text-muted-foreground"
}

export function PaCard({ strategy, onSetStatus }: Props) {
  const pa = strategy.priceAction!

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold">{strategy.name}</h3>
            <StrategyStatusBadge status={strategy.status} />
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {strategy.symbol} · {pa.timeframe} 周期 · {strategy.runningDays} 天
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
        <div className="flex items-center justify-between rounded-md border border-border/60 bg-secondary/30 px-3 py-2.5">
          <div>
            <p className="text-[11px] text-muted-foreground">当前识别形态</p>
            <p className="text-sm font-medium">{pa.pattern}</p>
          </div>
          <div className="text-right">
            <p className="text-[11px] text-muted-foreground">信号强度</p>
            <p className={cn("font-mono text-sm font-semibold tabular-nums", strengthColor(pa.signalStrength))}>
              {pa.signalStrength}
            </p>
          </div>
        </div>

        {/* 信号强度条 */}
        <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
          <div
            className={cn(
              "h-full rounded-full",
              pa.signalStrength >= 70 ? "bg-success" : pa.signalStrength >= 50 ? "bg-primary" : "bg-muted-foreground",
            )}
            style={{ width: `${pa.signalStrength}%` }}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <InfoRow icon={ShieldAlert} label="止损价" value={fmtNum(pa.stopLoss, pa.stopLoss < 10 ? 3 : 0)} valueClass="text-destructive" />
          <InfoRow icon={Target} label="止盈价" value={fmtNum(pa.takeProfit, pa.takeProfit < 10 ? 3 : 0)} valueClass="text-success" />
          <InfoRow icon={Clock} label="最近信号" value={pa.lastSignalAt.split(" ")[1]} />
          <InfoRow label="投入本金" value={fmtUsd(strategy.investment, 0)} />
        </div>

        <div className="flex items-center justify-end border-t border-border/60 pt-3">
          <StrategyControls strategy={strategy} onSetStatus={onSetStatus} />
        </div>
      </CardContent>
    </Card>
  )
}

function InfoRow({
  icon: Icon,
  label,
  value,
  valueClass,
}: {
  icon?: typeof Clock
  label: string
  value: string
  valueClass?: string
}) {
  return (
    <div className="flex items-center gap-2">
      {Icon ? <Icon className="size-3.5 text-muted-foreground" /> : <span className="size-3.5" />}
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={cn("ml-auto font-mono text-xs tabular-nums", valueClass)}>{value}</span>
    </div>
  )
}
