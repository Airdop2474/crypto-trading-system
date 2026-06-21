"use client"

import useSWR from "swr"
import Link from "next/link"
import { useParams } from "next/navigation"
import { ArrowLeft, ExternalLink } from "lucide-react"
import { api } from "@/lib/api"
import { fmtNum, fmtSigned, fmtUsd, pnlColor } from "@/lib/format"
import { getStrategyLabelIcon } from "@/lib/strategy-meta"
import { StatCard } from "@/components/stat-card"
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
import { SideBadge } from "@/components/status-badge"
import type { BrokerOrder, ClosedTrade } from "@/lib/types"

/**
 * 策略详情页（统一路由 /strategy/[id]）
 *
 * 数据源：GET /multi/strategy/{id}（返回 MultiStrategyResult）
 * 覆盖所有 8 种策略：grid / rsi / ma / buyhold / donchian / structure / supertrend / reversal
 *
 * 布局：
 *   1. 返回链接 + 策略标题
 *   2. 5 张统计卡（已实现盈亏 / 总成交 / 持仓数 / 平仓数 / 累计手续费）
 *   3. 当前持仓表（open_lots）
 *   4. 已平仓交易表（closed_trades）—— 含每笔盈亏
 *   5. 成交流水表（trade_history）—— 完整订单流水
 */
export default function StrategyDetailPage() {
  const params = useParams<{ id: string }>()
  const id = params?.id ?? ""

  const { data, error, isLoading, mutate } = useSWR(
    id ? `multi-strategy-${id}` : null,
    () => api.getMultiStrategy(id),
  )

  if (error) {
    return (
      <div className="flex flex-col gap-4 pb-16 md:pb-0">
        <BackLink id={id} />
        <ApiError
          error={error}
          onRetry={() => mutate()}
          title="策略详情加载失败"
        />
      </div>
    )
  }

  if (isLoading || !data) {
    return (
      <div className="flex flex-col gap-4 pb-16 md:pb-0">
        <BackLink id={id} />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
        <div className="h-64 animate-pulse rounded-lg bg-muted" />
      </div>
    )
  }

  const { label, LucideIcon } = getStrategyLabelIcon(id)
  const stats = data.statistics
  const openLotsEntries = Object.entries(data.open_lots).filter(([, v]) => v > 0)
  const closedTrades: ClosedTrade[] = data.closed_trades
  const tradeHistory: BrokerOrder[] = data.trade_history

  // 累计手续费（statistics 已有）
  const totalFee = stats.total_commission + stats.total_slippage

  // 平仓盈亏统计
  const wins = closedTrades.filter((t) => t.profit > 0).length
  const winRate = closedTrades.length > 0 ? (wins / closedTrades.length) * 100 : 0

  return (
    <div className="flex flex-col gap-4 pb-16 md:pb-0">
      {/* 1. 顶部返回 + 标题 */}
      <BackLink id={id} />

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <LucideIcon className="size-5" />
              </div>
              <div>
                <h1 className="text-base font-semibold">{label}</h1>
                <p className="text-xs text-muted-foreground">
                  {data.symbol} · 策略 ID <code className="font-mono">{id}</code>
                </p>
              </div>
            </div>
            <Badge variant="outline" className="text-xs">
              <ExternalLink className="mr-1 size-3" />
              实时数据
            </Badge>
          </div>
        </CardHeader>
      </Card>

      {/* 2. 5 张统计卡 */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <StatCard
          label="已实现盈亏"
          value={fmtSigned(data.realized_pnl)}
          valueClassName={pnlColor(data.realized_pnl)}
        />
        <StatCard
          label="总成交笔数"
          value={fmtNum(stats.total_trades, 0)}
        />
        <StatCard
          label="持仓数"
          value={fmtNum(openLotsEntries.length, 0)}
        />
        <StatCard
          label="平仓笔数"
          value={fmtNum(closedTrades.length, 0)}
          sub={`胜率 ${winRate.toFixed(0)}%`}
          subClassName={winRate >= 50 ? "text-success" : "text-warning"}
        />
        <StatCard
          label="累计成本"
          value={fmtUsd(totalFee)}
          sub={`手续费 ${fmtUsd(stats.total_commission)} · 滑点 ${fmtUsd(stats.total_slippage)}`}
        />
      </div>

      {/* 3. 当前持仓 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">
            当前持仓
            <Badge variant="secondary" className="ml-2 text-xs">
              {openLotsEntries.length} 个
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {openLotsEntries.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              当前无持仓
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>标签</TableHead>
                  <TableHead className="text-right">数量</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {openLotsEntries.map(([tag, amount]) => (
                  <TableRow key={tag}>
                    <TableCell className="font-mono text-xs">{tag}</TableCell>
                    <TableCell className="text-right font-mono text-sm tabular-nums">
                      {fmtNum(amount, 6)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* 4. 已平仓交易 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">
            已平仓交易
            <Badge variant="secondary" className="ml-2 text-xs">
              {closedTrades.length} 笔
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {closedTrades.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              暂无平仓记录
            </p>
          ) : (
            <div className="max-h-[400px] overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>标签</TableHead>
                    <TableHead>时间</TableHead>
                    <TableHead className="text-right">盈亏</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[...closedTrades].reverse().map((t, i) => (
                    <TableRow key={`${t.tag}-${i}`}>
                      <TableCell className="font-mono text-xs">{t.tag}</TableCell>
                      <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">
                        {fmtTime(t.time)}
                      </TableCell>
                      <TableCell
                        className={`text-right font-mono text-sm tabular-nums ${pnlColor(t.profit)}`}
                      >
                        {fmtSigned(t.profit)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 5. 成交流水 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">
            成交流水
            <Badge variant="secondary" className="ml-2 text-xs">
              {tradeHistory.length} 笔
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {tradeHistory.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              暂无成交流水
            </p>
          ) : (
            <div className="max-h-[500px] overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>订单ID</TableHead>
                    <TableHead>时间</TableHead>
                    <TableHead>方向</TableHead>
                    <TableHead>类型</TableHead>
                    <TableHead className="text-right">价格</TableHead>
                    <TableHead className="text-right">数量</TableHead>
                    <TableHead className="text-right">手续费</TableHead>
                    <TableHead>标签</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[...tradeHistory].reverse().map((o) => (
                    <TableRow key={o.order_id}>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {o.order_id}
                      </TableCell>
                      <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">
                        {fmtTime(o.timestamp)}
                      </TableCell>
                      <TableCell>
                        <SideBadge side={o.side} />
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {o.order_type === "limit" ? "限价" : "市价"}
                      </TableCell>
                      <TableCell className="text-right font-mono text-sm tabular-nums">
                        {fmtNum(o.price, o.price < 10 ? 4 : 2)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-sm tabular-nums">
                        {fmtNum(o.amount, 6)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs tabular-nums text-muted-foreground">
                        {fmtNum(o.commission, 4)}
                      </TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {o.tag ?? "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function BackLink({ id }: { id: string }) {
  // 根据策略类型推断返回的目标列表页
  const backHref = id.startsWith("grid-") ? "/grid" : "/price-action"
  const backLabel = id.startsWith("grid-") ? "网格交易" : "价格行为策略"
  return (
    <Link
      href={backHref}
      className="inline-flex w-fit items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
    >
      <ArrowLeft className="size-3.5" />
      返回{backLabel}
    </Link>
  )
}

function fmtTime(iso: string): string {
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleString("zh-CN", { hour12: false })
  } catch {
    return iso
  }
}
