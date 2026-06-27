"use client"

import { useState } from "react"
import { toast } from "sonner"
import type { StrategyRegistryEntry, MultiStrategyDetail, StrategyType } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Settings, Trash2, Loader2, Archive, RotateCcw } from "lucide-react"
import { cn } from "@/lib/utils"
import { fmtSigned, fmtNum, pnlColor } from "@/lib/format"
import { STRATEGY_TYPE_COLOR, STRATEGY_FALLBACK_COLOR, STRATEGY_TYPE_CATEGORY, STRATEGY_CATEGORY_LABEL } from "@/lib/strategy-meta"
import { api } from "@/lib/api"
import useSWR, { mutate as globalMutate } from "swr"

interface Props {
  entry: StrategyRegistryEntry
  instance?: MultiStrategyDetail
  onConfigure: () => void
}

export function StrategyCard({ entry, instance, onConfigure }: Props) {
  const [deleting, setDeleting] = useState(false)
  const { data: statusData, mutate: mutateStatus } = useSWR(
    "strategies-status",
    () => api.getStrategiesStatus(),
    { revalidateOnFocus: false, dedupingInterval: 60_000 }
  )
  const statusEntry = statusData?.[entry.key]
  const isArchived = statusEntry?.status === "archived" || statusEntry?.status === "disabled"
  const archReason = statusEntry?.reason || ""

  const colorClass = entry.key in STRATEGY_TYPE_COLOR
    ? STRATEGY_TYPE_COLOR[entry.key as StrategyType]
    : STRATEGY_FALLBACK_COLOR
  const category = STRATEGY_TYPE_CATEGORY[entry.key as StrategyType]
  const categoryLabel = STRATEGY_CATEGORY_LABEL[category]

  const handleToggleArchive = async () => {
    const newStatus = isArchived ? "active" : "archived"
    const reason = isArchived ? "" : "手动归档"
    try {
      await api.setStrategyStatus(entry.key, newStatus, reason)
      await mutateStatus()
      toast.success(isArchived ? "已恢复为启用" : "已归档")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "操作失败")
    }
  }

  const handleDelete = async () => {
    setDeleting(true)
    try {
      const result = await api.deleteStrategyInstance(entry.key)
      if (result.ok) {
        toast.success(result.message)
        await globalMutate(
          (key) => typeof key === "string" && key.startsWith("strategies"),
          undefined,
          { revalidate: true }
        )
      } else {
        toast.error(result.message || "删除失败")
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "删除失败")
    } finally {
      setDeleting(false)
    }
  }

  return (
    <Card className={cn(isArchived && "opacity-60")}>
      <CardHeader className="flex-row items-start justify-between gap-3 pb-3">
        <div className="flex flex-col gap-1">
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            {entry.name}
            <span className={cn("rounded-md px-1.5 py-0.5 text-[11px] font-semibold leading-none", colorClass)}>
              {entry.key}
            </span>
            <span className="rounded-md border border-border/60 bg-muted/40 px-1.5 py-0.5 text-[10px] font-medium leading-none text-muted-foreground">
              {categoryLabel}
            </span>
            {isArchived && (
              <span
                className="rounded-md border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium leading-none text-amber-600"
                title={archReason || "已归档"}
              >
                归档
              </span>
            )}
          </CardTitle>
          <p className="text-xs text-muted-foreground leading-relaxed">
            {entry.description}
          </p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span
            className={cn(
              "size-2 rounded-full",
              entry.running ? "bg-success" : "bg-muted-foreground/40",
            )}
          />
          <span className="text-xs text-muted-foreground">
            {entry.running ? "运行中" : "未运行"}
          </span>
        </div>
      </CardHeader>

      <CardContent className="flex flex-col gap-3 pt-0">
        {/* 实例数 */}
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>当前实例:</span>
          <span className="font-mono font-medium text-foreground">
            {entry.instances}
          </span>
        </div>

        {/* PnL / 性能数据 */}
        {instance && (
          <div className="grid grid-cols-3 gap-3 rounded-md border border-border/50 bg-muted/25 px-3 py-2">
            <div>
              <p className="text-[10px] text-muted-foreground">累计盈亏</p>
              <p className={`font-mono text-xs tabular-nums ${pnlColor(instance.realizedPnl)}`}>
                {fmtSigned(instance.realizedPnl)}
              </p>
            </div>
            <div className="text-center">
              <p className="text-[10px] text-muted-foreground">交易笔数</p>
              <p className="font-mono text-xs tabular-nums text-foreground">
                {instance.totalTrades}
              </p>
            </div>
            <div className="text-right">
              <p className="text-[10px] text-muted-foreground">胜率</p>
              <p className="font-mono text-xs tabular-nums text-foreground">
                {fmtNum(instance.winRate * 100, 0)}%
              </p>
            </div>
          </div>
        )}

        {/* 操作按钮 */}
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="flex-1 gap-1.5"
            onClick={onConfigure}
          >
            <Settings className="size-3.5" />
            配置参数
          </Button>

          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={handleToggleArchive}
            title={isArchived ? "恢复为启用" : "归档（不删除，可恢复）"}
            aria-label={isArchived ? "恢复为启用" : "归档策略"}
          >
            {isArchived ? (
              <RotateCcw className="size-3.5" />
            ) : (
              <Archive className="size-3.5" />
            )}
          </Button>

          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5 text-destructive hover:text-destructive"
                disabled={deleting || !entry.running}
                aria-label="删除策略实例"
              >
                {deleting ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Trash2 className="size-3.5" />
                )}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>删除策略实例</AlertDialogTitle>
                <AlertDialogDescription>
                  确定要删除运行中的策略实例 "{entry.name}" 吗？
                  此操作会从运行队列中移除该策略并清理其状态文件，但不会删除已保存的参数配置。
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>取消</AlertDialogCancel>
                <AlertDialogAction
                  onClick={handleDelete}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  确认删除
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </CardContent>
    </Card>
  )
}