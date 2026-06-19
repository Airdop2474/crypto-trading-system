"use client"

import useSWR from "swr"
import { api } from "@/lib/api"
import { fmtSigned, fmtPct, pnlColor } from "@/lib/format"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"

const STRATEGY_LABELS: Record<string, { label: string; color: string }> = {
  "grid-btc-usdt": { label: "网格", color: "bg-blue-500/20 text-blue-400" },
  "rsi-btc-usdt": { label: "RSI 动量", color: "bg-purple-500/20 text-purple-400" },
  "sma-btc-usdt": { label: "均线", color: "bg-amber-500/20 text-amber-400" },
}

export function MultiStrategyPanel() {
  const { data: summary, isLoading } = useSWR("multi-summary", api.getMultiSummary)
  const { data: details, isLoading: detailsLoading } = useSWR("multi-details", api.getMultiDetails)

  const loading = isLoading || detailsLoading

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium">多策略并行表现</CardTitle>
        {summary && (
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="text-xs">
              {summary.strategiesCount} 个策略
            </Badge>
            <span className={`font-mono text-sm font-semibold tabular-nums ${pnlColor(summary.totalRealizedPnl)}`}>
              {fmtSigned(summary.totalRealizedPnl)}
            </span>
          </div>
        )}
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="h-[200px] animate-pulse rounded bg-muted" />
        ) : details && details.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>策略</TableHead>
                <TableHead className="text-right">已实现盈亏</TableHead>
                <TableHead className="text-right">交易次数</TableHead>
                <TableHead className="text-right">胜率</TableHead>
                <TableHead className="text-right">开放仓位</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {details.map((d) => {
                const meta = STRATEGY_LABELS[d.strategyId] ?? {
                  label: d.strategyId,
                  color: "bg-gray-500/20 text-gray-400",
                }
                return (
                  <TableRow key={d.strategyId}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span className={`inline-flex rounded px-1.5 py-0.5 text-[10px] font-medium ${meta.color}`}>
                          {meta.label}
                        </span>
                        <span className="text-xs text-muted-foreground">{d.symbol}</span>
                      </div>
                    </TableCell>
                    <TableCell className={`text-right font-mono text-sm font-semibold tabular-nums ${pnlColor(d.realizedPnl)}`}>
                      {fmtSigned(d.realizedPnl)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm tabular-nums text-muted-foreground">
                      {d.totalTrades}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm tabular-nums">
                      {fmtPct(d.winRate).replace("+", "")}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm tabular-nums text-muted-foreground">
                      {d.openLots}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        ) : (
          <p className="py-8 text-center text-sm text-muted-foreground">
            暂无多策略运行数据
          </p>
        )}
      </CardContent>
    </Card>
  )
}
