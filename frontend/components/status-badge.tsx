import { cn } from "@/lib/utils"
import type { StrategyStatus, OrderStatus } from "@/lib/types"

const strategyMap: Record<StrategyStatus, { label: string; cls: string; dot: string }> = {
  running: { label: "运行中", cls: "border-success/30 bg-success/10 text-success", dot: "bg-success" },
  paused: { label: "已暂停", cls: "border-primary/30 bg-primary/10 text-primary", dot: "bg-primary" },
  stopped: { label: "已停止", cls: "border-border bg-muted text-muted-foreground", dot: "bg-muted-foreground" },
}

export function StrategyStatusBadge({ status }: { status: StrategyStatus }) {
  const s = strategyMap[status]
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium", s.cls)}>
      <span className={cn("size-1.5 rounded-full", s.dot, status === "running" && "animate-pulse")} />
      {s.label}
    </span>
  )
}

const orderMap: Record<OrderStatus, { label: string; cls: string }> = {
  filled: { label: "已成交", cls: "border-success/30 bg-success/10 text-success" },
  open: { label: "挂单中", cls: "border-chart-4/30 bg-chart-4/10 text-chart-4" },
  partially_filled: { label: "部分成交", cls: "border-primary/30 bg-primary/10 text-primary" },
  canceled: { label: "已撤销", cls: "border-border bg-muted text-muted-foreground" },
}

export function OrderStatusBadge({ status }: { status: OrderStatus }) {
  const s = orderMap[status]
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium", s.cls)}>
      {s.label}
    </span>
  )
}

export function SideBadge({ side }: { side: "buy" | "sell" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-semibold",
        side === "buy" ? "bg-success/15 text-success" : "bg-destructive/15 text-destructive",
      )}
    >
      {side === "buy" ? "买入" : "卖出"}
    </span>
  )
}
