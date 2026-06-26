"use client"

import { useState, useCallback } from "react"
import useSWR from "swr"
import { toast } from "sonner"
import {
  AlertOctagon,
  Pause,
  Play,
  RotateCcw,
  ShieldCheck,
  ShieldAlert,
  Loader2,
} from "lucide-react"
import { api } from "@/lib/api"
import type { RiskState, RiskStatus } from "@/lib/types"
import { fmtNum, fmtSigned, pnlColor } from "@/lib/format"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ApiError } from "@/components/api-error"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
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

type ControlAction = "resume" | "pause" | "emergency_stop" | "reset"

function actionLabel(action: ControlAction): string {
  switch (action) {
    case "resume":
      return "恢复交易"
    case "pause":
      return "暂停交易"
    case "emergency_stop":
      return "紧急停止"
    case "reset":
      return "重置状态"
  }
}

export function RiskStatusCard() {
  const { data, error, isLoading, mutate } = useSWR<RiskStatus>(
    "risk-status",
    api.getRiskStatus,
    { revalidateOnFocus: false, refreshInterval: 30_000 },
  )
  const [pendingAction, setPendingAction] = useState<ControlAction | null>(null)
  const [confirmAction, setConfirmAction] = useState<ControlAction | null>(null)

  const handleControl = useCallback(
    async (action: ControlAction) => {
      setPendingAction(action)
      setConfirmAction(null)
      try {
        const result = await api.controlRiskStatus(action)

        // 乐观更新：根据 action 立即推算新状态并更新 UI，
        // 不等 daemon 消费信号文件（可能要等 1-4 小时到下一根 K 线）
        const optimisticState: RiskState =
          action === "pause"
            ? "PAUSED"
            : action === "emergency_stop"
              ? "STOPPED"
              : "ACTIVE" // resume / reset -> ACTIVE

        const optimisticData: RiskStatus = {
          ...(result.current_state ?? data!),
          state: optimisticState,
          can_trade: optimisticState === "ACTIVE",
          // resume / reset 清零瞬时熔断计数
          consecutive_losses:
            action === "resume" || action === "reset" ? 0 : data!.consecutive_losses,
          daily_pnl:
            action === "reset" ? 0 : data!.daily_pnl,
        }
        await mutate(optimisticData, { revalidate: false })

        // 提示用户：UI 已更新，daemon 正在异步生效
        if (result.immediate_applied) {
          toast.success(`已${actionLabel(action)}，状态已立即生效`)
        } else {
          toast.success(
            `已${actionLabel(action)}（界面已更新，daemon 将在下一根 K 线真正生效）`,
          )
        }
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "风控控制失败")
      } finally {
        setPendingAction(null)
      }
    },
    [mutate, data],
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

  // 根据当前状态决定可用的控制按钮
  const isBusy = pendingAction !== null
  const isDaemonMode = data.note?.includes("Paper Trading 模式") !== true

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

        {/* 手动控制区 */}
        <div className="space-y-2 border-t border-border pt-3">
          <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            手动控制
          </p>
          <div className="flex flex-wrap gap-2">
            {/* ACTIVE 状态：可暂停 / 紧急停止 */}
            {data.state === "ACTIVE" && (
              <>
                <ControlButton
                  action="pause"
                  label="暂停交易"
                  icon={Pause}
                  variant="outline"
                  disabled={isBusy}
                  loading={pendingAction === "pause"}
                  onClick={() => handleControl("pause")}
                />
                <ControlButton
                  action="emergency_stop"
                  label="紧急停止"
                  icon={AlertOctagon}
                  variant="destructive"
                  disabled={isBusy}
                  loading={pendingAction === "emergency_stop"}
                  onClick={() => setConfirmAction("emergency_stop")}
                />
              </>
            )}

            {/* PAUSED 状态：可恢复 / 重置 / 紧急停止 */}
            {data.state === "PAUSED" && (
              <>
                <ControlButton
                  action="resume"
                  label="恢复交易"
                  icon={Play}
                  variant="default"
                  disabled={isBusy}
                  loading={pendingAction === "resume"}
                  onClick={() => handleControl("resume")}
                />
                <ControlButton
                  action="reset"
                  label="重置状态"
                  icon={RotateCcw}
                  variant="outline"
                  disabled={isBusy}
                  loading={pendingAction === "reset"}
                  onClick={() => setConfirmAction("reset")}
                />
                <ControlButton
                  action="emergency_stop"
                  label="紧急停止"
                  icon={AlertOctagon}
                  variant="destructive"
                  disabled={isBusy}
                  loading={pendingAction === "emergency_stop"}
                  onClick={() => setConfirmAction("emergency_stop")}
                />
              </>
            )}

            {/* STOPPED 状态：仅可重置（唯一恢复路径） */}
            {data.state === "STOPPED" && (
              <ControlButton
                action="reset"
                label="重置并恢复"
                icon={RotateCcw}
                variant="default"
                disabled={isBusy}
                loading={pendingAction === "reset"}
                onClick={() => setConfirmAction("reset")}
              />
            )}
          </div>
          {isDaemonMode ? (
            <p className="text-[10px] text-muted-foreground">
              界面立即更新，daemon 在下一根 K 线（1-4 小时）真正生效
            </p>
          ) : (
            <p className="text-[10px] text-muted-foreground">
              预跑模式：操作立即生效
            </p>
          )}
        </div>
      </CardContent>

      {/* 二次确认对话框：紧急停止 / 重置 */}
      <AlertDialog
        open={confirmAction !== null}
        onOpenChange={(open) => !open && setConfirmAction(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirmAction === "emergency_stop" ? "确认紧急停止" : "确认重置风控状态"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirmAction === "emergency_stop"
                ? "紧急停止将立即冻结所有交易（最强保护）。停止后需要通过「重置」才能恢复，且重置受 5 分钟冷却期和 1 小时 3 次上限保护。"
                : "重置将清空所有熔断计数器并恢复到 ACTIVE。重置受防抖保护：5 分钟冷却期 + 1 小时最多 3 次。回撤跟踪（peak_equity / cumulative_pnl）不会被清零，防止绕过年化回撤熔断线。"}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isBusy}>取消</AlertDialogCancel>
            <AlertDialogAction
              disabled={isBusy}
              className={cn(
                confirmAction === "emergency_stop" &&
                  "bg-destructive text-destructive-foreground hover:bg-destructive/90",
              )}
              onClick={(e) => {
                e.preventDefault()
                if (confirmAction) handleControl(confirmAction)
              }}
            >
              {pendingAction === confirmAction ? (
                <>
                  <Loader2 className="mr-1 size-3 animate-spin" />
                  执行中
                </>
              ) : (
                "确认执行"
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}

function ControlButton({
  label,
  icon: Icon,
  variant,
  disabled,
  loading,
  onClick,
}: {
  action: ControlAction
  label: string
  icon: typeof Pause
  variant: "default" | "outline" | "destructive"
  disabled?: boolean
  loading?: boolean
  onClick: () => void
}) {
  return (
    <Button
      size="sm"
      variant={variant}
      disabled={disabled}
      onClick={onClick}
    >
      {loading ? (
        <Loader2 className="size-3.5 animate-spin" />
      ) : (
        <Icon className="size-3.5" />
      )}
      {label}
    </Button>
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
