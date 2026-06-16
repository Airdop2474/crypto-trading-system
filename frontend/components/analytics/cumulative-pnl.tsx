"use client"

import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts"
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
  cumulativePnl: { label: "累计盈亏", color: "var(--chart-2)" },
} satisfies ChartConfig

export function CumulativePnl({ data, loading }: { data: PnlPoint[]; loading: boolean }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">累计盈亏 · 近 30 天</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="h-[280px] animate-pulse rounded bg-muted" />
        ) : (
          <ChartContainer config={config} className="h-[280px] w-full">
            <AreaChart data={data} margin={{ left: 4, right: 8, top: 8 }}>
              <defs>
                <linearGradient id="fillCum" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--color-cumulativePnl)" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="var(--color-cumulativePnl)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" tickLine={false} axisLine={false} tickMargin={8} minTickGap={24} className="text-xs" />
              <YAxis tickLine={false} axisLine={false} width={52} tickFormatter={(v) => fmtCompact(v)} className="text-xs" />
              <ChartTooltip content={<ChartTooltipContent formatter={(v) => fmtCompact(Number(v))} />} />
              <Area dataKey="cumulativePnl" type="monotone" stroke="var(--color-cumulativePnl)" strokeWidth={2} fill="url(#fillCum)" />
            </AreaChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  )
}
