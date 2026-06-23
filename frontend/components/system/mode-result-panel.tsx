"use client"

import useSWR from "swr"
import { useState } from "react"
import Link from "next/link"
import { ChevronDown, ChevronUp, TrendingUp, TrendingDown, Minus, ExternalLink } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { api } from "@/lib/api"
import { fmtNum, fmtSigned, fmtPct, pnlColor } from "@/lib/format"
import type { ModeResult, RunningMode, ModeStatusValue } from "@/lib/types"

interface ModeResultPanelProps {
  mode: RunningMode
  modeStatus: ModeStatusValue
}

/** 根据 mode_status / exit_code / risk_state 推断运行结果状态 */
function inferStatus(r: ModeResult): { label: string; className: string } {
  if (r.mode_status === "running") {
    return { label: "运行中", className: "border-success/30 text-success bg-success/10" }
  }
  if (r.mode_status === "stopping") {
    return { label: "停止中", className: "border-warning/30 text-warning bg-warning/10" }
  }
  if (r.mode_status === "error" || (r.exit_code != null && r.exit_code !== 0)) {
    return { label: "异常退出", className: "border-destructive/30 text-destructive bg-destructive/10" }
  }
  // idle
  if (r.risk_state === "STOPPED") {
    return { label: "风控停止", className: "border-warning/30 text-warning bg-warning/10" }
  }
  if (r.risk_state === "PAUSED" || r.strategy_paused) {
    return { label: "已暂停", className: "border-warning/30 text-warning bg-warning/10" }
  }
  return { label: "已完成", className: "border-success/30 text-success bg-success/10" }
}

export function ModeResultPanel({ mode, modeStatus }: ModeResultPanelProps) {
  // key 含 modeStatus：状态切换（running→idle）时自动重取一次最终结果
  const { data: r } = useSWR(
    ["mode-result", mode, modeStatus],
    () => api.getModeResult(mode),
    {
      revalidateOnFocus: false,
      refreshInterval: modeStatus === "running" ? 3_000 : 0,
      dedupingInterval: 2_000,
    },
  )

  const [showTrades, setShowTrades] = useState(false)

  if (!r || !r.available) return null

  const status = inferStatus(r)
  const pnlIcon = r.realized_pnl > 0 ? TrendingUp : r.realized_pnl < 0 ? TrendingDown : Minus

  return (
    <div className="rounded-md border border-border/60 bg-secondary/20 p-3 space-y-2.5">
      {/* 标题行 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-medium text-foreground">运行结果</span>
          <Badge variant="outline" className={cn("text-[10px] h-5", status.className)}>
            {status.label}
          </Badge>
          {r.exit_code != null && r.mode_status !== "running" && (
            <span className="text-[10px] text-muted-foreground">exit {r.exit_code}</span>
          )}
          <Link
            href="/paper"
            className="ml-1 flex items-center gap-0.5 text-[10px] text-primary hover:underline"
          >
            详情
            <ExternalLink className="size-2.5" />
          </Link>
        </div>
        {r.last_bar_ts && (
          <span className="text-[10px] text-muted-foreground">
            数据截至 {String(r.last_bar_ts).slice(0, 19)}
          </span>
        )}
      </div>

      {/* 核心指标网格 */}
      <div className="grid grid-cols-4 gap-2">
        <Metric
          label="已实现盈亏"
          value={fmtSigned(r.realized_pnl)}
          valueClass={pnlColor(r.realized_pnl)}
          icon={pnlIcon}
        />
        <Metric
          label="收益率"
          value={fmtPct(r.total_return_pct)}
          valueClass={pnlColor(r.total_return_pct)}
        />
        <Metric
          label="交易笔数"
          value={String(r.total_trades)}
          sub={`${r.win_count}胜 / ${r.loss_count}负`}
        />
        <Metric
          label="胜率"
          value={r.total_trades > 0 ? `${fmtNum(r.win_rate, 1)}%` : "—"}
        />
      </div>

      {/* 次要信息 */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        <span>最终权益 <span className="font-mono text-foreground">{fmtNum(r.final_balance)}</span></span>
        <span>初始资金 <span className="font-mono text-foreground">{fmtNum(r.initial_capital)}</span></span>
        <span>运行 <span className="font-mono text-foreground">{r.day_count}</span> 天</span>
        <span>风控 <span className="font-mono text-foreground">{r.risk_state}</span></span>
        {r.strategies.length > 1 && (
          <span>策略数 <span className="font-mono text-foreground">{r.strategies.length}</span></span>
        )}
      </div>

      {/* 多策略明细 */}
      {r.strategies.length > 1 && (
        <div className="space-y-1">
          {r.strategies.map((s) => (
            <div
              key={s.strategy}
              className="flex items-center justify-between rounded border border-border/40 bg-background/40 px-2 py-1 text-[11px]"
            >
              <span className="font-medium">{s.strategy}</span>
              <div className="flex items-center gap-3 font-mono tabular-nums">
                <span className={pnlColor(s.realized_pnl)}>{fmtSigned(s.realized_pnl)}</span>
                <span className="text-muted-foreground">{s.total_trades} 笔</span>
                <span className="text-muted-foreground">
                  {s.total_trades > 0 ? `${fmtNum(s.win_rate, 0)}%` : "—"}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 最近交易（可展开） */}
      {r.recent_trades.length > 0 && (
        <div>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-[10px] text-muted-foreground px-2"
            onClick={() => setShowTrades(!showTrades)}
          >
            最近交易（{r.recent_trades.length}）
            {showTrades ? <ChevronUp className="size-3 ml-1" /> : <ChevronDown className="size-3 ml-1" />}
          </Button>
          {showTrades && (
            <div className="mt-1 space-y-0.5">
              {r.recent_trades.map((t, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between rounded px-2 py-0.5 text-[11px] hover:bg-background/40"
                >
                  <span className="text-muted-foreground">
                    <span className="font-mono">{t.tag || "—"}</span>
                    {r.strategies.length > 1 && <span className="ml-2 text-[10px]">[{t.strategy}]</span>}
                    <span className="ml-2">{String(t.time).slice(0, 19)}</span>
                  </span>
                  <span className={cn("font-mono tabular-nums", pnlColor(t.profit))}>
                    {fmtSigned(t.profit)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Metric({
  label,
  value,
  sub,
  valueClass,
  icon: Icon,
}: {
  label: string
  value: string
  sub?: string
  valueClass?: string
  icon?: typeof TrendingUp
}) {
  return (
    <div className="space-y-0.5">
      <p className="text-[10px] text-muted-foreground">{label}</p>
      <p className={cn("font-mono text-sm font-semibold tabular-nums flex items-center gap-1", valueClass)}>
        {Icon && <Icon className="size-3" />}
        {value}
      </p>
      {sub && <p className="text-[10px] text-muted-foreground">{sub}</p>}
    </div>
  )
}
