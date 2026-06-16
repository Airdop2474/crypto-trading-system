"use client"

import { Cell, Pie, PieChart } from "recharts"
import type { AssetBalance } from "@/lib/types"
import { fmtUsd } from "@/lib/format"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"

const palette = ["var(--chart-1)", "var(--chart-2)", "var(--chart-4)", "var(--chart-5)", "var(--chart-3)"]

export function AssetAllocation({ assets, loading }: { assets: AssetBalance[]; loading: boolean }) {
  const config: ChartConfig = Object.fromEntries(
    assets.map((a, i) => [a.asset, { label: a.asset, color: palette[i % palette.length] }]),
  )

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="text-sm font-medium">资产分布</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="h-[200px] animate-pulse rounded bg-muted" />
        ) : (
          <>
            <ChartContainer config={config} className="mx-auto h-[200px]">
              <PieChart>
                <ChartTooltip content={<ChartTooltipContent formatter={(v) => fmtUsd(Number(v))} nameKey="asset" />} />
                <Pie data={assets} dataKey="valueUsdt" nameKey="asset" innerRadius={55} outerRadius={85} strokeWidth={2}>
                  {assets.map((a, i) => (
                    <Cell key={a.asset} fill={palette[i % palette.length]} stroke="var(--card)" />
                  ))}
                </Pie>
              </PieChart>
            </ChartContainer>
            <div className="mt-2 flex flex-col gap-1.5">
              {assets.map((a, i) => (
                <div key={a.asset} className="flex items-center gap-2 text-xs">
                  <span className="size-2.5 rounded-sm" style={{ background: palette[i % palette.length] }} />
                  <span className="font-medium">{a.asset}</span>
                  <span className="ml-auto font-mono tabular-nums text-muted-foreground">{a.allocationPct}%</span>
                  <span className="w-24 text-right font-mono tabular-nums">{fmtUsd(a.valueUsdt)}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
