"use client"

import useSWR from "swr"
import {
  Line,
  LineChart,
  CartesianGrid,
  XAxis,
  YAxis,
  ReferenceLine,
} from "recharts"
import { api } from "@/lib/api"
import { fmtNum } from "@/lib/format"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { ApiError } from "@/components/api-error"

const config = {
  win_rate: { label: "胜率 %", color: "var(--chart-1)" },
} satisfies ChartConfig

/**
 * 滚动胜率趋势
 *
 * 数据源：GET /analytics/win-rate-trend?window=20
 * 每笔平仓后基于最近 20 笔算胜率，折线图展示趋势
 */
export function WinRateTrendCard() {
  const { data, error, isLoading, mutate } = useSWR(
    "win-rate-trend",
    () => api.getWinRateTrend(20),
    { revalidateOnFocus: false, refreshInterval: 60_000 },
  )

  const points = data ?? []
  const latest = points.length ? points[points.length - 1].win_rate : 0
  const avg = points.length
    ? points.reduce((a, p) => a + p.win_rate, 0) / points.length
    : 0

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium">
          胜率趋势
          <span className="ml-2 text-xs font-normal text-muted-foreground">
            滚动 20 笔
          </span>
        </CardTitle>
        {points.length > 0 ? (
          <div className="flex items-center gap-3 text-xs">
            <span className="text-muted-foreground">
              当前 <span className={`font-mono tabular-nums ${latest >= 50 ? "text-success" : "text-warning"}`}>{fmtNum(latest, 1)}%</span>
            </span>
            <span className="text-muted-foreground">
              均值 <span className="font-mono tabular-nums">{fmtNum(avg, 1)}%</span>
            </span>
          </div>
        ) : null}
      </CardHeader>
      <CardContent>
        {error ? (
          <ApiError error={error} onRetry={() => mutate()} title="胜率趋势加载失败" minHeight={280} />
        ) : isLoading ? (
          <div className="h-[280px] animate-pulse rounded bg-muted" />
        ) : points.length === 0 ? (
          <div className="flex h-[280px] items-center justify-center text-sm text-muted-foreground">
            暂无平仓数据
          </div>
        ) : (
          <ChartContainer config={config} className="h-[280px] w-full">
            <LineChart data={points} margin={{ left: 4, right: 8, top: 8 }}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis
                dataKey="index"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                minTickGap={32}
                className="text-xs"
              />
              <YAxis
                domain={[0, 100]}
                tickLine={false}
                axisLine={false}
                width={44}
                tickFormatter={(v: number) => `${v}%`}
                className="text-xs"
              />
              <ReferenceLine y={50} stroke="var(--warning)" strokeDasharray="4 4" />
              <ChartTooltip
                content={
                  <ChartTooltipContent
                    formatter={(v) => `${fmtNum(Number(v), 1)}%`}
                    labelFormatter={(l) => `第 ${l} 笔`}
                  />
                }
              />
              <Line
                dataKey="win_rate"
                type="monotone"
                stroke="var(--color-win_rate)"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  )
}
