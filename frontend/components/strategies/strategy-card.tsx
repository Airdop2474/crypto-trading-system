"use client"

import type { StrategyRegistryEntry, MultiStrategyDetail, StrategyType } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Settings } from "lucide-react"
import { cn } from "@/lib/utils"
import { fmtSigned, fmtNum, pnlColor } from "@/lib/format"
import { STRATEGY_TYPE_COLOR, STRATEGY_FALLBACK_COLOR } from "@/lib/strategy-meta"

interface Props {
  entry: StrategyRegistryEntry
  instance?: MultiStrategyDetail
  onConfigure: () => void
}

export function StrategyCard({ entry, instance, onConfigure }: Props) {
  const userParams = Object.entries(entry.param_schema)
  const colorClass = entry.key in STRATEGY_TYPE_COLOR
    ? STRATEGY_TYPE_COLOR[entry.key as StrategyType]
    : STRATEGY_FALLBACK_COLOR

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3 pb-3">
        <div className="flex flex-col gap-1">
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            {entry.name}
            <span className={cn("rounded-md px-1.5 py-0.5 text-[11px] font-semibold leading-none", colorClass)}>
              {entry.key}
            </span>
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

        {/* 参数概要 */}
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">参数:</span>
          {userParams.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {userParams.map(([key, constraint]) => (
                <Badge
                  key={key}
                  variant="secondary"
                  className="text-[10px] font-mono"
                >
                  {key}
                  {constraint.min != null && constraint.max != null
                    ? ` [${constraint.min}~${constraint.max}]`
                    : constraint.min != null
                      ? ` [>=${constraint.min}]`
                      : constraint.max != null
                        ? ` [<=${constraint.max}]`
                        : ""}
                </Badge>
              ))}
            </div>
          ) : (
            <span className="text-[10px] text-muted-foreground/60 italic leading-5">无参数</span>
          )}
        </div>

        {/* 配置按钮 */}
        <Button
          variant="outline"
          size="sm"
          className="w-full gap-1.5"
          onClick={onConfigure}
        >
          <Settings className="size-3.5" />
          配置参数
        </Button>
      </CardContent>
    </Card>
  )
}