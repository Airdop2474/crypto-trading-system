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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { OrderStatusBadge, SideBadge } from "@/components/status-badge"
import { Search } from "lucide-react"

type Filter = "all" | OrderStatus

const filters: { value: Filter; label: string }[] = [
  { value: "all", label: "全部状态" },
  { value: "filled", label: "已成交" },
  { value: "open", label: "挂单中" },
  { value: "partially_filled", label: "部分成交" },
  { value: "canceled", label: "已撤销" },
]

export function OrdersTable({ orders, loading }: { orders: Order[]; loading: boolean }) {
  const [status, setStatus] = useState<Filter>("all")
  const [query, setQuery] = useState("")

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

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-xs">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索交易对或策略"
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
                  <TableCell className="text-xs text-muted-foreground">{o.strategyName}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
