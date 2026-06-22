"use client"

import useSWR from "swr"
import { api } from "@/lib/api"
import type { EvolutionStats } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { TrendingUp } from "lucide-react"

export function EvolutionStatsCard() {
  const { data } = useSWR<EvolutionStats>("getEvolutionStats", () => api.getEvolutionStats(), {
    revalidateOnFocus: false,
    dedupingInterval: 30_000,
  })

  if (!data) return null

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <TrendingUp className="size-4 text-emerald-400" />
          进化统计
        </CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-3 gap-4 text-center">
        <div>
          <p className="text-lg font-semibold tabular-nums">{data.total_evolutions}</p>
          <p className="text-[11px] text-muted-foreground">总进化次数</p>
        </div>
        <div>
          <p className="text-lg font-semibold tabular-nums">{data.applied_count}</p>
          <p className="text-[11px] text-muted-foreground">已应用</p>
        </div>
        <div>
          <p className="text-lg font-semibold tabular-nums text-emerald-400">
            {(data.avg_sharpe_improvement * 100).toFixed(1)}%
          </p>
          <p className="text-[11px] text-muted-foreground">平均 Sharpe 提升</p>
        </div>
      </CardContent>
    </Card>
  )
}
