"use client"

import { useState } from "react"
import useSWR from "swr"
import Link from "next/link"
import { useParams } from "next/navigation"
import { toast } from "sonner"
import { ArrowLeft, ExternalLink, Play, Pause, Settings, Shield } from "lucide-react"
import { api } from "@/lib/api"
import { fmtNum, fmtSigned, fmtUsd, pnlColor } from "@/lib/format"
import { getStrategyLabelIcon, parseStrategyType } from "@/lib/strategy-meta"
import { StatCard } from "@/components/stat-card"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
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
import { StrategyParamsDialog } from "@/components/strategies/strategy-params-dialog"
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

  const { data: registry } = useSWR(
    id ? "strategy-registry" : null,
    () => api.getStrategyRegistry(),
  )

  const [pausing, setPausing] = useState(false)
  const [paramsOpen, setParamsOpen] = useState(false)

  const strategyType = parseStrategyType(id)
  const registryEntry = registry?.strategies.find((s) => s.key === strategyType)

  const handlePause = async () => {
    setPausing(true)
    const toastId = toast.loading("正在暂停策略…")
    try {
      await api.updateStrategyStatus(id, "paused")
      toast.success("策略已暂停", { id: toastId })
      mutate()
    } catch (e) {
      const msg = e instanceof Error ? e.message : "未知错误"
      toast.error("暂停失败", { id: toastId, description: msg })
    } finally {
      setPausing(false)
    }
  }

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
  const signals = data.signals ?? []

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
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-xs">
                <ExternalLink className="mr-1 size-3" />
                实时数据
              </Badge>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() => setParamsOpen(true)}
              >
                <Settings className="size-3.5" />
                参数
              </Button>
              <Button
                variant="secondary"
                size="sm"
                className="gap-1.5"
                onClick={handlePause}
                disabled={pausing}
              >
                <Pause className="size-3.5" />
                {pausing ? "暂停中…" : "暂停"}
              </Button>
            </div>
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

      {/* 2.5 止损信息 */}
      {(() => {
        const sl = (data as unknown as Record<string, unknown>).stop_loss_info as Record<string, unknown> | undefined
        if (!sl) return null
        return (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <Shield className="h-4 w-4" />
              止损管理
            </CardTitle>
          </CardHeader>
          <CardContent>
            {(() => {
              if (!(sl.enabled as boolean)) {
                return <p className="py-2 text-center text-sm text-muted-foreground">该策略未启用止损</p>
              }
              const stopTypeLabels: Record<string, string> = {
                atr_trailing: "ATR 追踪止损",
                range_breakout: "区间突破止损",
                time_only: "纯时间止损",
                none: "无止损",
              }
              return (
                <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                  <div className="space-y-0.5">
                    <div className="text-xs text-muted-foreground">止损类型</div>
                    <div className="text-sm font-medium">{stopTypeLabels[sl.stop_type as string] ?? (sl.stop_type as string)}</div>
                  </div>
                  <div className="space-y-0.5">
                    <div className="text-xs text-muted-foreground">持仓状态</div>
                    <div className="text-sm font-medium">
                      {sl.in_position ? (
                        <Badge className="bg-success/20 text-success border-success/30">持仓中</Badge>
                      ) : (
                        <Badge variant="secondary">空仓</Badge>
                      )}
                    </div>
                  </div>
                  {sl.entry_price != null && (
                    <div className="space-y-0.5">
                      <div className="text-xs text-muted-foreground">入场价</div>
                      <div className="font-mono text-sm">{fmtNum(sl.entry_price as number, 2)}</div>
                    </div>
                  )}
                  {sl.current_stop_price != null && (
                    <div className="space-y-0.5">
                      <div className="text-xs text-muted-foreground">当前止损价</div>
                      <div className="font-mono text-sm text-warning">{fmtNum(sl.current_stop_price as number, 2)}</div>
                    </div>
                  )}
                  {sl.highest_price != null && (
                    <div className="space-y-0.5">
                      <div className="text-xs text-muted-foreground">最高价</div>
                      <div className="font-mono text-sm">{fmtNum(sl.highest_price as number, 2)}</div>
                    </div>
                  )}
                  {sl.bars_held != null && (sl.bars_held as number) > 0 && (
                    <div className="space-y-0.5">
                      <div className="text-xs text-muted-foreground">持仓 bar 数</div>
                      <div className="font-mono text-sm">{sl.bars_held as number}</div>
                    </div>
                  )}
                </div>
              )
            })()}
          </CardContent>
        </Card>
        )
      })()}

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

      {/* 6. 信号日志 */}
      {signals.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">
              信号日志
              <Badge variant="secondary" className="ml-2 text-xs">
                {signals.length} 条
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-[300px] overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>时间</TableHead>
                    <TableHead>动作</TableHead>
                    <TableHead>原因</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[...signals].reverse().map((sig, i) => (
                    <TableRow key={i}>
                      <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">
                        {fmtTime(sig.timestamp)}
                      </TableCell>
                      <TableCell>
                        <SideBadge side={sig.action === "hold" ? "buy" : sig.action} />
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {sig.reason ?? "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {registryEntry && (
        <StrategyParamsDialog
          strategyId={id}
          strategyName={label}
          paramSchema={registryEntry.param_schema}
          currentParams={registryEntry.defaults}
          defaultParams={registryEntry.defaults}
          open={paramsOpen}
          onOpenChange={setParamsOpen}
        />
      )}
    </div>
  )
}

function BackLink({ id }: { id: string }) {
  return (
    <Link
      href="/strategies"
      className="inline-flex w-fit items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
    >
      <ArrowLeft className="size-3.5" />
      返回策略总览
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
