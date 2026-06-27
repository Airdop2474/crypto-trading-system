"use client"

import { useState, useMemo } from "react"
import useSWR from "swr"
import { Flame, RefreshCw, ChevronDown, ChevronUp } from "lucide-react"
import { api } from "@/lib/api"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { ApiError } from "@/components/api-error"
import { cn } from "@/lib/utils"
import { getStrategyLabelColor } from "@/lib/strategy-meta"

/** 默认显示前 N 个策略（按热力值降序），其余折叠 */
const TOP_N = 5

export function PortfolioHeatCard() {
  const { data, error, isLoading, mutate } = useSWR(
    "portfolio-heat",
    api.getPortfolioHeat,
    { refreshInterval: 10000 }, // 10秒自动刷新
  )
  const [expanded, setExpanded] = useState(false)

  const heat = data ?? { total_heat: 0, max_heat: 0.15, heat_pct: 0, strategies: {}, updated_at: null }

  // 按热力值降序排序（必须在所有条件 return 之前调用，遵守 Hooks 规则）
  const strategyEntries = useMemo(() => {
    const entries = Object.entries(heat.strategies || {})
    return entries.sort((a, b) => (b[1].heat ?? 0) - (a[1].heat ?? 0))
  }, [heat.strategies])

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Flame className="h-4 w-4" />
            组合热力 Portfolio Heat
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-24 animate-pulse rounded bg-muted" />
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Flame className="h-4 w-4" />
            组合热力 Portfolio Heat
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ApiError error={error} onRetry={() => mutate()} title="组合热力加载失败" />
        </CardContent>
      </Card>
    )
  }

  const heatPct = heat.heat_pct
  const isWarning = heatPct >= 60
  const isDanger = heatPct >= 80

  const totalCount = strategyEntries.length
  const visibleEntries = expanded ? strategyEntries : strategyEntries.slice(0, TOP_N)
  const hiddenCount = Math.max(0, totalCount - TOP_N)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Flame className="h-4 w-4" />
            组合热力 Portfolio Heat
          </span>
          <div className="flex items-center gap-2">
            <Badge
              variant={isDanger ? "destructive" : isWarning ? "default" : "secondary"}
              className={cn(isWarning && !isDanger && "bg-warning/20 text-warning border-warning/30")}
            >
              {isDanger ? "危险" : isWarning ? "警告" : "正常"}
            </Badge>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => mutate()}
              aria-label="刷新组合热力"
            >
              <RefreshCw className="h-3 w-3" />
            </Button>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {/* 总热力进度条 */}
        <div className="space-y-1.5">
          <div className="flex items-baseline justify-between text-sm">
            <span className="text-muted-foreground">总热力</span>
            <span className={cn("font-mono font-semibold", isDanger ? "text-destructive" : isWarning ? "text-warning" : "text-success")}>
              {(heat.total_heat * 100).toFixed(2)}%
            </span>
          </div>
          <Progress
            value={Math.min(heatPct, 100)}
            className={cn(
              "h-2.5",
              isDanger && "[&>div]:bg-destructive",
              isWarning && !isDanger && "[&>div]:bg-warning",
            )}
          />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>0%</span>
            <span>阈值: {(heat.max_heat * 100).toFixed(0)}%</span>
          </div>
        </div>

        {/* 各策略热力明细（按热力降序，Top N + 折叠） */}
        {strategyEntries.length > 0 ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="text-xs font-medium text-muted-foreground">
                各策略热力明细
              </div>
              <div className="text-[10px] text-muted-foreground">
                共 {totalCount} 个持仓策略
              </div>
            </div>
            <div className="space-y-1.5">
              {visibleEntries.map(([name, info]) => {
                const pct = heat.max_heat > 0 ? (info.heat / heat.max_heat) * 100 : 0
                const { label, color } = getStrategyLabelColor(name)
                return (
                  <div key={name} className="flex items-center gap-2 text-sm">
                    <span className={cn("inline-block rounded px-1.5 py-0.5 text-xs shrink-0", color)}>{label}</span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded bg-muted">
                      <div
                        className={cn(
                          "h-full rounded",
                          pct >= 80 ? "bg-destructive" : pct >= 60 ? "bg-warning" : "bg-primary",
                        )}
                        style={{ width: `${Math.min(pct, 100)}%` }}
                      />
                    </div>
                    <span className="w-14 text-right font-mono text-xs">
                      {(info.heat * 100).toFixed(2)}%
                    </span>
                  </div>
                )
              })}
            </div>
            {/* 展开/收起按钮 */}
            {hiddenCount > 0 && (
              <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors w-full justify-center pt-1"
              >
                {expanded ? (
                  <>
                    <ChevronUp className="size-3" />
                    收起（隐藏 {hiddenCount} 个低热力策略）
                  </>
                ) : (
                  <>
                    <ChevronDown className="size-3" />
                    展开剩余 {hiddenCount} 个低热力策略
                  </>
                )}
              </button>
            )}
          </div>
        ) : (
          <div className="text-center text-sm text-muted-foreground py-2">
            无活跃持仓（daemon 未运行或无持仓）
          </div>
        )}

        {/* 更新时间 */}
        {heat.updated_at && (
          <div className="text-xs text-muted-foreground text-right">
            更新于 {new Date(heat.updated_at).toLocaleTimeString("zh-CN")}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
