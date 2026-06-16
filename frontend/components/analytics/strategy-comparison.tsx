"use client"

import { Bar, BarChart, Cell, CartesianGrid, XAxis, YAxis } from "recharts"
import type { StrategyPerformance } from "@/lib/types"
import { fmtCompact, fmtNum, fmtSigned, pnlColor } from "@/lib/format"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Progress } from "@/components/ui/progress"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"

const config = {
  pnl: { label: "盈亏" },
} satisfies ChartConfig

export function StrategyComparison({
  data,
  loading,
}: {
  data: StrategyPerformance[]
  loading: boolean
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">各策略表现对比</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {loading ? (
          <div className="h-[240px] animate-pulse rounded bg-muted" />
        ) : (
          <ChartContainer config={config} className="h-[240px] w-full">
            <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
              <CartesianGrid horizontal={false} strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis type="number" tickLine={false} axisLine={false} tickFormatter={(v) => fmtCompact(v)} className="text-xs" />
              <YAxis
                type="category"
                dataKey="name"
                tickLine={false}
                axisLine={false}
                width={120}
                className="text-xs"
              />
              <ChartTooltip content={<ChartTooltipContent formatter={(v) => fmtCompact(Number(v))} />} />
              <Bar dataKey="pnl" radius={[0, 2, 2, 0]}>
                {data.map((d, i) => (
                  <Cell key={i} fill={d.pnl >= 0 ? "var(--success)" : "var(--destructive)"} />
                ))}
              </Bar>
            </BarChart>
          </ChartContainer>
        )}

        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>策略</TableHead>
                <TableHead className="text-right">盈亏</TableHead>
                <TableHead className="text-right">交易次数</TableHead>
                <TableHead className="w-40">胜率</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading
                ? [0, 1, 2].map((i) => (
                    <TableRow key={i}>
                      <TableCell colSpan={4}>
                        <div className="h-5 w-full animate-pulse rounded bg-muted" />
                      </TableCell>
                    </TableRow>
                  ))
                : data.map((s) => (
                    <TableRow key={s.name}>
                      <TableCell className="font-medium">{s.name}</TableCell>
                      <TableCell className={`text-right font-mono tabular-nums ${pnlColor(s.pnl)}`}>
                        {fmtSigned(s.pnl)}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums text-muted-foreground">
                        {fmtNum(s.trades, 0)}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Progress value={s.winRate} className="h-1.5" />
                          <span className="w-10 shrink-0 text-right font-mono text-xs tabular-nums">
                            {s.winRate.toFixed(0)}%
                          </span>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}
