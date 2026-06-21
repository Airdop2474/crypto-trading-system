"use client"

import useSWR from "swr"
import { api } from "@/lib/api"
import type { AgentAuditLogEntry, AgentTask } from "@/lib/types"
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
import { ApiError } from "@/components/api-error"
import { cn } from "@/lib/utils"

const TASK_LABEL: Record<AgentTask, string> = {
  backtest: "回测解读",
  trade_attribution: "交易归因",
  risk_checklist: "风险清单",
  param_sensitivity: "参数敏感性",
  weekly_review: "周报复盘",
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

export function AuditLogs() {
  const { data, error, isLoading, mutate } = useSWR(
    "agent-audit-logs",
    () => api.getAgentAuditLogs(undefined, 50),
    { revalidateOnFocus: false, refreshInterval: 30_000 },
  )

  const logs = data ?? []

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium">审计日志</CardTitle>
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
            title="审计日志加载失败"
            minHeight={120}
          />
        ) : isLoading ? (
          <div className="h-[200px] animate-pulse rounded bg-muted" />
        ) : logs.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            暂无审计日志（触发一次分析后此处会显示）
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-[140px]">时间</TableHead>
                <TableHead className="w-[100px]">任务</TableHead>
                <TableHead>输出摘要</TableHead>
                <TableHead className="w-[90px] text-right">采纳</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {logs.map((e: AgentAuditLogEntry) => (
                <TableRow key={e.id}>
                  <TableCell className="whitespace-nowrap font-mono text-xs tabular-nums text-muted-foreground">
                    {fmtTime(e.timestamp)}
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary" className="text-[10px]">
                      {TASK_LABEL[e.task] ?? e.task}
                    </Badge>
                  </TableCell>
                  <TableCell className="max-w-[400px]">
                    <p className="truncate text-xs text-foreground/90">
                      {summarize(e.output_summary)}
                    </p>
                  </TableCell>
                  <TableCell className="text-right">
                    {e.human_approved ? (
                      <span className="text-xs font-medium text-success">已采纳</span>
                    ) : (
                      <span className={cn("text-xs text-muted-foreground")}>未采纳</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

function summarize(o: Record<string, unknown>): string {
  if (!o || typeof o !== "object") return ""
  const a = (o as { analysis?: unknown }).analysis
  if (typeof a === "string") return a
  const r = (o as { recommendation?: unknown }).recommendation
  if (typeof r === "string") return r
  return JSON.stringify(o).slice(0, 120)
}
