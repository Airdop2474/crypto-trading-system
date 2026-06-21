"use client"

import useSWR from "swr"
import { Bar, BarChart, CartesianGrid, XAxis, YAxis, Cell } from "recharts"
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
  count: { label: "笔数", color: "var(--chart-1)" },
} satisfies ChartConfig

/**
 * 盈亏分布直方图 + 胜率统计
 *
 * 数据源：GET /analytics/pnl-distribution
 */
export function PnlDistributionChart() {
  const { data, error, isLoading, mutate } = useSWR(
    "pnl-distribution",
    () => api.getPnlDistribution(10),
    { revalidateOnFocus: false, refreshInterval: 60_000 },
  )

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">盈亏分布</CardTitle>
        </CardHeader>
        <CardContent>
          <ApiError
            error={error}
            onRetry={() => mutate()}
            title="盈亏分布加载失败"
            minHeight={280}
          />
        </CardContent>
      </Card>
    )
  }

  const stats = data?.stats
  const bins = data?.bins ?? []

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium">盈亏分布</CardTitle>
        {stats ? (
          <div className="flex items-center gap-3 text-xs">
            <span className="text-muted-foreground">
              胜率 <span className={stats.win_rate >= 50 ? "text-success font-mono tabular-nums" : "text-warning font-mono tabular-nums"}>{fmtNum(stats.win_rate, 1)}%</span>
            </span>
            <span className="text-muted-foreground">
              盈亏比 <span className="font-mono tabular-nums">{stats.profit_factor === Infinity ? "∞" : fmtNum(stats.profit_factor, 2)}</span>
            </span>
          </div>
        ) : null}
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="h-[280px] animate-pulse rounded bg-muted" />
        ) : bins.length === 0 ? (
          <div className="flex h-[280px] items-center justify-center text-sm text-muted-foreground">
            暂无数据
          </div>
        ) : (
          <>
            <ChartContainer config={config} className="h-[280px] w-full">
              <BarChart data={bins} margin={{ left: 4, right: 8, top: 8 }}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis
                  dataKey="range"
                  tickLine={false}
                  axisLine={false}
                  tickMargin={8}
                  className="text-[10px]"
                  interval={0}
                  angle={-30}
                  textAnchor="end"
                  height={50}
                />
                <YAxis
                  tickLine={false}
                  axisLine={false}
                  width={36}
                  allowDecimals={false}
                  className="text-xs"
                />
                <ChartTooltip
                  content={
                    <ChartTooltipContent
                      formatter={(v) => `${v} 笔`}
                    />
                  }
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {bins.map((b, i) => (
                    <Cell
                      key={i}
                      fill={b.label === "盈利" ? "var(--success)" : b.label === "亏损" ? "var(--destructive)" : "var(--chart-4)"}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ChartContainer>

            {/* 统计明细 */}
            {stats ? (
              <div className="mt-3 grid grid-cols-4 gap-2 border-t border-border pt-3 text-xs">
                <Stat label="总笔数" value={fmtNum(stats.total, 0)} />
                <Stat label="盈利" value={fmtNum(stats.wins, 0)} className="text-success" />
                <Stat label="亏损" value={fmtNum(stats.losses, 0)} className="text-destructive" />
                <Stat label="最佳" value={fmtNum(stats.best, 2)} className="text-success" />
                <Stat label="平均盈利" value={fmtNum(stats.avg_profit, 2)} className="text-success" />
                <Stat label="平均亏损" value={fmtNum(stats.avg_loss, 2)} className="text-destructive" />
                <Stat label="最差" value={fmtNum(stats.worst, 2)} className="text-destructive" />
                <Stat
                  label="盈亏比"
                  value={stats.profit_factor === Infinity ? "∞" : fmtNum(stats.profit_factor, 2)}
                />
              </div>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  )
}

function Stat({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-muted-foreground">{label}</span>
      <span className={`font-mono text-sm font-semibold tabular-nums ${className ?? ""}`}>
        {value}
      </span>
    </div>
  )
}
