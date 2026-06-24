"use client"

import useSWR from "swr"
import { Flame, RefreshCw } from "lucide-react"
import { api } from "@/lib/api"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { ApiError } from "@/components/api-error"
import { cn } from "@/lib/utils"

export function PortfolioHeatCard() {
  const { data, error, isLoading, mutate } = useSWR(
    "portfolio-heat",
    api.getPortfolioHeat,
    { refreshInterval: 10000 }, // 10秒自动刷新
  )

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

  const heat = data ?? { total_heat: 0, max_heat: 0.15, heat_pct: 0, strategies: {}, updated_at: null }
  const heatPct = heat.heat_pct
  const isWarning = heatPct >= 60
  const isDanger = heatPct >= 80
  const strategyEntries = Object.entries(heat.strategies || {})

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

        {/* 各策略热力明细 */}
        {strategyEntries.length > 0 ? (
          <div className="space-y-2">
            <div className="text-xs font-medium text-muted-foreground">各策略热力明细</div>
            <div className="space-y-1.5">
              {strategyEntries.map(([name, info]) => {
                const pct = heat.max_heat > 0 ? (info.heat / heat.max_heat) * 100 : 0
                return (
                  <div key={name} className="flex items-center gap-2 text-sm">
                    <span className="w-20 truncate text-muted-foreground">{name}</span>
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
