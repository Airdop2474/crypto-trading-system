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
import { getStrategyLabelColor } from "@/lib/strategy-meta"
import type { ClosedTradeHistory } from "@/lib/types"

/**
 * 平仓标签 → 中文 + 样式
 *
 * tag 是策略在 Order 上自带的仓位标记，用于配对买入/卖出。
 * 常见值：_all（默认全仓）、stop_loss（止损触发）、bb/macd/composite（信号退出）、
 * 数字（网格档位索引）。
 */
const TAG_LABEL: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  _all: { label: "全仓", variant: "secondary" },
  stop_loss: { label: "止损", variant: "destructive" },
  bb: { label: "布林信号", variant: "outline" },
  macd: { label: "MACD信号", variant: "outline" },
  composite: { label: "复合信号", variant: "outline" },
}

function formatTag(tag: string): { label: string; variant: "default" | "secondary" | "destructive" | "outline" } {
  if (!tag) return { label: "—", variant: "secondary" }
  // 纯数字 → 网格档位
  if (/^\d+$/.test(tag)) return { label: `网格${tag}`, variant: "outline" }
  return TAG_LABEL[tag] || { label: tag, variant: "secondary" }
}

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
                {rows.map((t) => {
                  const tagInfo = formatTag(t.tag)
                  const strat = getStrategyLabelColor(t.strategy_name)
                  return (
                  <TableRow key={t.id}>
                    <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">
                      {fmtTime(t.close_time)}
                    </TableCell>
                    <TableCell className="text-xs">
                      <span className={`inline-block rounded px-1.5 py-0.5 text-xs ${strat.color}`}>{strat.label}</span>
                    </TableCell>
                    <TableCell>
                      <Badge variant={tagInfo.variant} className="text-xs">{tagInfo.label}</Badge>
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
                  )
                })}
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
