"use client"

import useSWR from "swr"
import { Area, AreaChart, CartesianGrid, XAxis, YAxis, ReferenceLine } from "recharts"
import { api } from "@/lib/api"
import type { DrawdownPoint } from "@/lib/types"
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
  drawdown: { label: "回撤 %", color: "var(--chart-3)" },
} satisfies ChartConfig

function fmtDate(iso: string): string {
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" })
  } catch {
    return iso
  }
}

export function DrawdownChart() {
  const { data, error, isLoading, mutate } = useSWR(
    "drawdown-curve",
    api.getDrawdownCurve,
    { revalidateOnFocus: false, refreshInterval: 60_000 },
  )

  const points: DrawdownPoint[] = data ?? []
  const minDD = points.length
    ? Math.min(...points.map((p) => p.drawdown))
    : 0

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium">回撤曲线</CardTitle>
        <span className="font-mono text-xs tabular-nums text-destructive">
          峰值回撤 {fmtNum(minDD, 2)}%
        </span>
      </CardHeader>
      <CardContent>
        {error ? (
          <ApiError
            error={error}
            onRetry={() => mutate()}
            title="回撤曲线加载失败"
            minHeight={280}
          />
        ) : isLoading ? (
          <div className="h-[280px] animate-pulse rounded bg-muted" />
        ) : points.length === 0 ? (
          <div className="flex h-[280px] items-center justify-center text-sm text-muted-foreground">
            暂无回撤数据
          </div>
        ) : (
          <ChartContainer config={config} className="h-[280px] w-full">
            <AreaChart data={points} margin={{ left: 4, right: 8, top: 8 }}>
              <defs>
                <linearGradient id="fillDD" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--color-drawdown)" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="var(--color-drawdown)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis
                dataKey="date"
                tickFormatter={fmtDate}
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                minTickGap={32}
                className="text-xs"
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                width={56}
                tickFormatter={(v: number) => `${fmtNum(Number(v), 1)}%`}
                className="text-xs"
              />
              {/* 0 轴参考线 */}
              <ReferenceLine y={0} stroke="var(--border)" strokeDasharray="4 4" />
              <ChartTooltip
                content={
                  <ChartTooltipContent
                    formatter={(v) => `${fmtNum(Number(v), 2)}%`}
                    labelFormatter={(l) => fmtDate(String(l))}
                  />
                }
              />
              <Area
                dataKey="drawdown"
                type="monotone"
                stroke="var(--color-drawdown)"
                strokeWidth={2}
                fill="url(#fillDD)"
              />
            </AreaChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  )
}
