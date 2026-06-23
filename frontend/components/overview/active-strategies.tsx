"use client"

import useSWR from "swr"
import Link from "next/link"
import { ArrowUpRight } from "lucide-react"
import { api } from "@/lib/api"
import { fmtPct, fmtSigned, pnlColor } from "@/lib/format"
import {
  parseStrategyType,
  STRATEGY_TYPE_ICON,
  STRATEGY_FALLBACK_ICON,
} from "@/lib/strategy-meta"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { StrategyStatusBadge } from "@/components/status-badge"

export function ActiveStrategies() {
  const { data } = useSWR("strategies", api.getStrategies)
  const top = (data ?? []).filter((s) => s.status === "running")

  return (
    <Card className="h-full">
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium">运行中策略</CardTitle>
        <Link
          href="/strategies"
          className="flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground"
        >
          查看全部 <ArrowUpRight className="size-3" />
        </Link>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {top.map((s) => {
          const type = parseStrategyType(s.id)
          const Icon = type ? STRATEGY_TYPE_ICON[type] : STRATEGY_FALLBACK_ICON
          return (
            <Link
              key={s.id}
              href={`/strategy/${s.id}`}
              className="flex items-center justify-between rounded-md border border-border/60 bg-secondary/30 px-3 py-2.5 hover:bg-secondary/60 transition-colors"
            >
              <div className="flex items-center gap-3">
                <div className="flex size-8 items-center justify-center rounded-md bg-secondary text-muted-foreground">
                  <Icon className="size-4" />
                </div>
                <div>
                  <p className="text-sm font-medium">{s.name}</p>
                  <p className="text-xs text-muted-foreground">{s.symbol}</p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div className="text-right">
                  <p className={`font-mono text-sm tabular-nums ${pnlColor(s.pnl)}`}>
                    {fmtSigned(s.pnl)}
                  </p>
                  <p className={`font-mono text-xs tabular-nums ${pnlColor(s.pnl)}`}>
                    {fmtPct(s.pnlPct)}
                  </p>
                </div>
                <StrategyStatusBadge status={s.status} />
              </div>
            </Link>
          )
        })}
      </CardContent>
    </Card>
  )
}
