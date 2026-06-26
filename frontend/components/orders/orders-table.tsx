"use client"

import { useMemo, useState } from "react"
import type { Order, OrderStatus } from "@/lib/types"
import { fmtNum } from "@/lib/format"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { OrderStatusBadge, SideBadge } from "@/components/status-badge"
import { getStrategyLabelColor } from "@/lib/strategy-meta"
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Search,
} from "lucide-react"

type Filter = "all" | OrderStatus

const filters: { value: Filter; label: string }[] = [
  { value: "all", label: "全部状态" },
  { value: "filled", label: "已成交" },
  { value: "open", label: "挂单中" },
  { value: "partially_filled", label: "部分成交" },
  { value: "canceled", label: "已撤销" },
]

const PAGE_SIZE_OPTIONS = [20, 50, 100, 200]

interface OrdersTableProps {
  /** 当前页的订单（已经分页过的） */
  orders: Order[]
  /** 全量订单数（后端 total） */
  total: number
  /** 每页条数 */
  pageSize: number
  /** 当前页码（从 1 开始） */
  page: number
  loading: boolean
  /** 切换每页条数（重置到第 1 页） */
  onPageSizeChange: (size: number) => void
  /** 切换页码 */
  onPageChange: (page: number) => void
}

export function OrdersTable({
  orders,
  total,
  pageSize,
  page,
  loading,
  onPageSizeChange,
  onPageChange,
}: OrdersTableProps) {
  const [status, setStatus] = useState<Filter>("all")
  const [query, setQuery] = useState("")

  // 当前页内二次过滤（按状态/搜索词）
  // 注：状态/搜索过滤是当前页内的本地过滤，不触发后端请求。
  // 若需全量过滤，应在后端加 query 参数；当前数据量下页内过滤已够用。
  const rows = useMemo(() => {
    return orders.filter((o) => {
      const matchStatus = status === "all" || o.status === status
      const matchQuery =
        query === "" ||
        o.symbol.toLowerCase().includes(query.toLowerCase()) ||
        o.strategyName.toLowerCase().includes(query.toLowerCase())
      return matchStatus && matchQuery
    })
  }, [orders, status, query])

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const canPrev = page > 1
  const canNext = page < totalPages

  // 起止序号（用于"显示 1-20 / 共 123"）
  const rangeStart = total === 0 ? 0 : (page - 1) * pageSize + 1
  const rangeEnd = Math.min(page * pageSize, total)

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-xs">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索交易对或策略（当前页）"
            className="pl-8"
          />
        </div>
        <Select value={status} onValueChange={(v) => setStatus(v as Filter)}>
          <SelectTrigger className="w-full sm:w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {filters.map((f) => (
              <SelectItem key={f.value} value={f.value}>
                {f.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>时间</TableHead>
              <TableHead>交易对</TableHead>
              <TableHead>方向</TableHead>
              <TableHead>类型</TableHead>
              <TableHead className="text-right">委托价</TableHead>
              <TableHead className="text-right">数量</TableHead>
              <TableHead className="text-right">成交</TableHead>
              <TableHead className="text-right">手续费</TableHead>
              <TableHead>状态</TableHead>
              <TableHead>策略</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              [0, 1, 2, 3, 4].map((i) => (
                <TableRow key={i}>
                  <TableCell colSpan={10}>
                    <div className="h-5 w-full animate-pulse rounded bg-muted" />
                  </TableCell>
                </TableRow>
              ))
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={10} className="h-24 text-center text-sm text-muted-foreground">
                  没有符合条件的订单
                </TableCell>
              </TableRow>
            ) : (
              rows.map((o) => (
                <TableRow key={o.id}>
                  <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">{o.time}</TableCell>
                  <TableCell className="font-medium">{o.symbol}</TableCell>
                  <TableCell>
                    <SideBadge side={o.side} />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{o.type === "limit" ? "限价" : "市价"}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">{fmtNum(o.price, o.price < 10 ? 4 : 2)}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">{fmtNum(o.amount, 4)}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">{fmtNum(o.filled, 4)}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums text-muted-foreground">{fmtNum(o.fee, 2)}</TableCell>
                  <TableCell>
                    <OrderStatusBadge status={o.status} />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {(() => {
                      const { label, color } = getStrategyLabelColor(o.strategyName)
                      return <span className={`inline-block rounded px-1.5 py-0.5 text-xs ${color}`}>{label}</span>
                    })()}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* 分页控件 */}
      <div className="flex flex-col gap-3 border-t border-border pt-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span>
            显示 <span className="font-mono tabular-nums text-foreground">{rangeStart}</span>
            -<span className="font-mono tabular-nums text-foreground">{rangeEnd}</span>
            {" "}/{" "}
            共 <span className="font-mono tabular-nums text-foreground">{total}</span> 条
          </span>
          <div className="flex items-center gap-1.5">
            <span>每页</span>
            <Select value={String(pageSize)} onValueChange={(v) => onPageSizeChange(Number(v))}>
              <SelectTrigger className="h-7 w-[72px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PAGE_SIZE_OPTIONS.map((n) => (
                  <SelectItem key={n} value={String(n)}>
                    {n}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon"
            className="size-8"
            onClick={() => onPageChange(1)}
            disabled={!canPrev || loading}
            aria-label="第一页"
            title="第一页"
          >
            <ChevronsLeft className="size-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="size-8"
            onClick={() => onPageChange(page - 1)}
            disabled={!canPrev || loading}
            aria-label="上一页"
            title="上一页"
          >
            <ChevronLeft className="size-4" />
          </Button>
          <span className="px-2 font-mono text-xs tabular-nums text-muted-foreground">
            {page} / {totalPages}
          </span>
          <Button
            variant="outline"
            size="icon"
            className="size-8"
            onClick={() => onPageChange(page + 1)}
            disabled={!canNext || loading}
            aria-label="下一页"
            title="下一页"
          >
            <ChevronRight className="size-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="size-8"
            onClick={() => onPageChange(totalPages)}
            disabled={!canNext || loading}
            aria-label="最后一页"
            title="最后一页"
          >
            <ChevronsRight className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
