"use client"

import useSWR from "swr"
import { AlertOctagon, Pause, ShieldCheck, ShieldAlert } from "lucide-react"
import { api } from "@/lib/api"
import type { RiskState, RiskStatus } from "@/lib/types"
import { fmtNum, fmtPct, fmtSigned, pnlColor } from "@/lib/format"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ApiError } from "@/components/api-error"
import { cn } from "@/lib/utils"

const STATE_META: Record<
  RiskState,
  { label: string; icon: typeof ShieldCheck; color: string; bg: string }
> = {
  ACTIVE: {
    label: "正常运行",
    icon: ShieldCheck,
    color: "text-success",
    bg: "border-success/30 bg-success/10",
  },
  PAUSED: {
    label: "熔断暂停",
    icon: Pause,
    color: "text-warning",
    bg: "border-warning/30 bg-warning/10",
  },
  STOPPED: {
    label: "紧急停止",
    icon: AlertOctagon,
    color: "text-destructive",
    bg: "border-destructive/30 bg-destructive/10",
  },
}

export function RiskStatusCard() {
  const { data, error, isLoading, mutate } = useSWR(
    "risk-status",
    api.getRiskStatus,
    { revalidateOnFocus: false, refreshInterval: 30_000 },
  )

  if (error) {
    return (
      <ApiError
        error={error}
        onRetry={() => mutate()}
        title="风控状态加载失败"
        minHeight={200}
      />
    )
  }

  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <ShieldAlert className="size-4 text-primary" />
            风控状态
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-[200px] animate-pulse rounded bg-muted" />
        </CardContent>
      </Card>
    )
  }

  const meta = STATE_META[data.state]
  const StateIcon = meta.icon

  // 日亏已用比例（用于进度条）
  const dailyUsedPct = data.daily_loss_used_pct
  const dailyLimitPct = data.daily_loss_limit_pct
  const dailyUsageRatio = dailyLimitPct > 0
    ? Math.min(100, (Math.max(0, dailyUsedPct) / dailyLimitPct) * 100)
    : 0

  // 总回撤已用比例
  const ddUsedPct = Math.abs(data.total_drawdown_pct)
  const ddLimitPct = data.max_total_drawdown_pct
  const ddUsageRatio = ddLimitPct > 0
    ? Math.min(100, (ddUsedPct / ddLimitPct) * 100)
    : 0

  // 连亏已用比例
  const consecUsageRatio = data.max_consecutive_losses > 0
    ? Math.min(100, (data.consecutive_losses / data.max_consecutive_losses) * 100)
    : 0

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <ShieldAlert className="size-4 text-primary" />
          风控状态
        </CardTitle>
        <Badge variant="outline" className={cn("border", meta.bg, meta.color)}>
          <StateIcon className="mr-1 size-3" />
          {meta.label}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        {data.note ? (
          <p className="rounded-md border border-warning/20 bg-warning/5 px-3 py-2 text-xs text-muted-foreground">
            {data.note}
          </p>
        ) : null}

        {/* 三条熔断线进度条 */}
        <RiskBar
          label="日亏损"
          used={dailyUsedPct}
          limit={dailyLimitPct}
          ratio={dailyUsageRatio}
          format="pct"
        />
        <RiskBar
          label="累计回撤"
          used={ddUsedPct}
          limit={ddLimitPct}
          ratio={ddUsageRatio}
          format="pct"
        />
        <RiskBar
          label="连续亏损"
          used={data.consecutive_losses}
          limit={data.max_consecutive_losses}
          ratio={consecUsageRatio}
          format="int"
        />

        {/* 数值明细 */}
        <div className="grid grid-cols-2 gap-3 border-t border-border pt-3 text-xs">
          <KV label="当日盈亏" value={fmtSigned(data.daily_pnl)} className={pnlColor(data.daily_pnl)} />
          <KV label="累计盈亏" value={fmtSigned(data.cumulative_pnl)} className={pnlColor(data.cumulative_pnl)} />
          <KV label="总仓位上限" value={`${fmtNum(data.limits.max_total_position * 100, 0)}%`} />
          <KV label="最大回撤上限" value={`${fmtNum(data.max_total_drawdown_pct, 1)}%`} />
        </div>

        {/* 风控事件 */}
        {data.events.length > 0 ? (
          <div>
            <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              最近风控事件
            </p>
            <ul className="space-y-1">
              {data.events.slice(-5).reverse().map((e, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 rounded-md border border-border/60 bg-muted/30 px-2.5 py-1.5 text-xs"
                >
                  <Pause className="mt-0.5 size-3 shrink-0 text-warning" />
                  <span className="text-foreground/90">
                    <span className="font-medium">{e.type}</span>
                    {" · "}
                    {e.reason}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}

function RiskBar({
  label,
  used,
  limit,
  ratio,
  format,
}: {
  label: string
  used: number
  limit: number
  ratio: number
  format: "pct" | "int"
}) {
  const ratio_color =
    ratio >= 100
      ? "bg-destructive"
      : ratio >= 80
        ? "bg-warning"
        : "bg-success/70"

  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono tabular-nums">
          <span className={pnlColor(-Math.abs(used))}>
            {format === "pct" ? `${fmtNum(used, 2)}%` : fmtNum(used, 0)}
          </span>
          <span className="text-muted-foreground"> / {format === "pct" ? `${fmtNum(limit, 1)}%` : fmtNum(limit, 0)}</span>
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted/50">
        <div
          className={cn("h-full rounded-full transition-all duration-500", ratio_color)}
          style={{ width: `${Math.max(2, ratio)}%` }}
        />
      </div>
    </div>
  )
}

function KV({
  label,
  value,
  className,
}: {
  label: string
  value: string
  className?: string
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn("font-mono text-sm font-semibold tabular-nums", className)}>
        {value}
      </span>
    </div>
  )
}
