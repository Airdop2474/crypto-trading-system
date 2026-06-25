"use client"

import useSWR from "swr"
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts"
import { api } from "@/lib/api"
import { fmtCompact } from "@/lib/format"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { ApiError } from "@/components/api-error"

const config = {
  equity: { label: "账户权益", color: "var(--chart-1)" },
} satisfies ChartConfig

export function EquityChart() {
  const { data, isLoading, error, mutate } = useSWR("pnl-history", api.getPnlHistory, {
    refreshInterval: 30_000,
  })

  if (error && !data) {
    return <ApiError error={error} onRetry={() => mutate()} />
  }

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="text-sm font-medium">账户权益曲线 · 近 30 天</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading || !data ? (
          <div className="h-[260px] animate-pulse rounded bg-muted" />
        ) : (
          <ChartContainer config={config} className="h-[260px] w-full">
            <AreaChart data={data} margin={{ left: 4, right: 8, top: 8 }}>
              <defs>
                <linearGradient id="fillEquity" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--color-equity)" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="var(--color-equity)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis
                dataKey="date"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                minTickGap={24}
                className="text-xs"
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                width={52}
                tickFormatter={(v) => fmtCompact(v)}
                domain={["dataMin - 2000", "dataMax + 2000"]}
                className="text-xs"
              />
              <ChartTooltip
                content={<ChartTooltipContent formatter={(v) => fmtCompact(Number(v))} />}
              />
              <Area
                dataKey="equity"
                type="monotone"
                stroke="var(--color-equity)"
                strokeWidth={2}
                fill="url(#fillEquity)"
              />
            </AreaChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  )
}
