"use client"

import { useState } from "react"
import useSWR from "swr"
import { api } from "@/lib/api"
import { fmtPct, pnlColor } from "@/lib/format"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { ApiError } from "@/components/api-error"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ChevronDown, History } from "lucide-react"

const PAGE_SIZE = 20

export function RunHistory() {
  const [limit, setLimit] = useState(PAGE_SIZE)

  const { data, error, isLoading, mutate } = useSWR(
    "strategy-history",
    () => api.getStrategyHistory(undefined, limit, 0),
  )

  const items = data?.items ?? []
  const hasMore = data?.has_more ?? false

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <History className="size-4 text-muted-foreground" />
        <h3 className="text-sm font-medium">运行历史</h3>
        {data && (
          <span className="text-xs text-muted-foreground">
            共 {data.total} 条记录
          </span>
        )}
      </div>

      {error ? (
        <ApiError
          error={error}
          onRetry={() => mutate()}
          title="运行历史加载失败"
          minHeight={120}
        />
      ) : isLoading && items.length === 0 ? (
        <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
          加载中...
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
          <History className="size-6 opacity-40" />
          <span>暂无运行记录</span>
        </div>
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>策略ID</TableHead>
                <TableHead>交易对</TableHead>
                <TableHead>模式</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>开始时间</TableHead>
                <TableHead>结束时间</TableHead>
                <TableHead className="text-right">收益率</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell className="font-mono text-xs max-w-[120px] truncate">
                    {entry.strategy_id}
                  </TableCell>
                  <TableCell>{entry.symbol}</TableCell>
                  <TableCell className="text-xs">{entry.mode}</TableCell>
                  <TableCell>
                    <StatusBadge status={entry.status} />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatTime(entry.started_at)}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {entry.ended_at ? formatTime(entry.ended_at) : "-"}
                  </TableCell>
                  <TableCell className={cn("text-right font-mono text-xs", entry.total_return != null && pnlColor(entry.total_return))}>
                    {entry.total_return != null
                      ? fmtPct(entry.total_return * 100)
                      : "-"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          {hasMore && (
            <div className="flex justify-center pt-2">
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() => setLimit((prev) => prev + PAGE_SIZE)}
              >
                <ChevronDown className="size-3.5" />
                加载更多
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    })
  } catch {
    return iso
  }
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    running: { label: "运行中", cls: "bg-success/10 text-success" },
    completed: { label: "已完成", cls: "bg-primary/10 text-primary" },
    stopped: { label: "已停止", cls: "bg-muted text-muted-foreground" },
    error: { label: "异常", cls: "bg-destructive/10 text-destructive" },
  }
  const info = map[status] ?? { label: status, cls: "bg-muted text-muted-foreground" }
  return (
    <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium", info.cls)}>
      {info.label}
    </span>
  )
}
