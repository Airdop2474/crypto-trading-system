"use client"

import { Bar, BarChart, Cell, CartesianGrid, XAxis, YAxis } from "recharts"
import type { PnlPoint } from "@/lib/types"
import { fmtCompact } from "@/lib/format"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"

const config = {
  pnl: { label: "当日盈亏" },
} satisfies ChartConfig

export function DailyPnl({ data, loading }: { data: PnlPoint[]; loading: boolean }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">每日盈亏分布</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="h-[280px] animate-pulse rounded bg-muted" />
        ) : (
          <ChartContainer config={config} className="h-[280px] w-full">
            <BarChart data={data} margin={{ left: 4, right: 8, top: 8 }}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" tickLine={false} axisLine={false} tickMargin={8} minTickGap={24} className="text-xs" />
              <YAxis tickLine={false} axisLine={false} width={52} tickFormatter={(v) => fmtCompact(v)} className="text-xs" />
              <ChartTooltip content={<ChartTooltipContent formatter={(v) => fmtCompact(Number(v))} />} />
              <Bar dataKey="pnl" radius={[2, 2, 0, 0]}>
                {data.map((d, i) => (
                  <Cell key={i} fill={d.pnl >= 0 ? "var(--success)" : "var(--destructive)"} />
                ))}
              </Bar>
            </BarChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  )
}
