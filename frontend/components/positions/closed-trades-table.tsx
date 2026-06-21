"use client"

import useSWR from "swr"
import { fmtNum, fmtSigned, fmtPct, pnlColor } from "@/lib/format"
import { api } from "@/lib/api"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ApiError } from "@/components/api-error"
import type { ClosedTradeHistory } from "@/lib/types"

/**
 * 平仓历史表
 *
 * 数据源：GET /positions/history
 * 展示：平仓时间 / 策略 / 标签 / 盈亏 / 收益率
 */
export function ClosedTradesTable() {
  const { data, error, isLoading, mutate } = useSWR(
    "positions-history",
    () => api.getPositionsHistory(200),
    { revalidateOnFocus: false, refreshInterval: 60_000 },
  )

  const rows: ClosedTradeHistory[] = data ?? []

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium">
          平仓历史
          <Badge variant="secondary" className="ml-2 text-xs">
            {rows.length} 笔
          </Badge>
        </CardTitle>
        <button
          type="button"
          onClick={() => mutate()}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          刷新
        </button>
      </CardHeader>
      <CardContent>
        {error ? (
          <ApiError
            error={error}
            onRetry={() => mutate()}
            title="平仓历史加载失败"
            minHeight={200}
          />
        ) : isLoading ? (
          <div className="h-[200px] animate-pulse rounded bg-muted" />
        ) : rows.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            暂无平仓记录
          </p>
        ) : (
          <div className="max-h-[400px] overflow-auto">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>平仓时间</TableHead>
                  <TableHead>策略</TableHead>
                  <TableHead>标签</TableHead>
                  <TableHead className="text-right">盈亏</TableHead>
                  <TableHead className="text-right">收益率</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">
                      {fmtTime(t.close_time)}
                    </TableCell>
                    <TableCell className="text-xs">{t.strategy_name}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {t.tag || "—"}
                    </TableCell>
                    <TableCell
                      className={`text-right font-mono text-sm tabular-nums ${pnlColor(t.profit)}`}
                    >
                      {fmtSigned(t.profit)}
                    </TableCell>
                    <TableCell
                      className={`text-right font-mono text-xs tabular-nums ${pnlColor(t.profit_pct)}`}
                    >
                      {fmtPct(t.profit_pct).replace("+", "")}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function fmtTime(iso: string): string {
  if (!iso) return "—"
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleString("zh-CN", { hour12: false })
  } catch {
    return iso
  }
}
