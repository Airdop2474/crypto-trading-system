"use client"

import Link from "next/link"
import { ArrowRight, Clock, BarChart3 } from "lucide-react"
import type { Strategy, StrategyStatus } from "@/lib/types"
import { fmtPct, fmtSigned, fmtUsd, pnlColor } from "@/lib/format"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { StrategyStatusBadge } from "@/components/status-badge"
import { StrategyControls } from "@/components/strategy-controls"

interface Props {
  strategy: Strategy
  onSetStatus: (id: string, status: StrategyStatus) => void
}

// 策略类型展示映射
const TYPE_LABELS: Record<string, string> = {
  donchian: "唐奇安通道 · 趋势突破", structure: "市场结构 · 波动突破",
  supertrend: "SuperTrend · ATR跟踪止损", reversal: "关键位反转 · Pin Bar确认",
}

export function PaCard({ strategy, onSetStatus }: Props) {
  const meta = TYPE_LABELS[strategy.type] ?? strategy.type

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold">{strategy.name}</h3>
            <StrategyStatusBadge status={strategy.status} />
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {strategy.symbol} · {meta} · {strategy.runningDays} 天
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
            <p className="text-[11px] text-muted-foreground">策略类型</p>
            <p className="text-sm font-medium">{meta}</p>
          </div>
          <div className="text-right">
            <p className="text-[11px] text-muted-foreground">交易对</p>
            <p className="font-mono text-sm tabular-nums text-muted-foreground">
              {strategy.symbol}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <InfoRow icon={BarChart3} label="类型" value={strategy.type} />
          <InfoRow icon={Clock} label="运行天数" value={`${strategy.runningDays} 天`} />
          <InfoRow label="交易对" value={strategy.symbol} />
          <InfoRow label="投入本金" value={fmtUsd(strategy.investment, 0)} />
        </div>

        <div className="flex items-center justify-between border-t border-border/60 pt-3">
          <Link
            href={`/strategy/${strategy.id}`}
            className="inline-flex items-center gap-1 text-xs text-primary transition-colors hover:text-primary/80"
          >
            查看详情
            <ArrowRight className="size-3" />
          </Link>
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
}: {
  icon?: typeof Clock
  label: string
  value: string
}) {
  return (
    <div className="flex items-center gap-2">
      {Icon ? <Icon className="size-3.5 text-muted-foreground" /> : <span className="size-3.5" />}
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="ml-auto font-mono text-xs tabular-nums">{value}</span>
    </div>
  )
}
