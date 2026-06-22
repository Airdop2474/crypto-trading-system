"use client"

import type { StrategyRegistryEntry } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Settings } from "lucide-react"
import { cn } from "@/lib/utils"

interface Props {
  entry: StrategyRegistryEntry
  onConfigure: () => void
}

/** 是否为风控类参数（创建时排除，由系统统一管理） */
function isRiskParam(key: string): boolean {
  const riskKeywords = ["stop_loss", "max_drawdown", "risk", "trailing_stop", "max_position"]
  return riskKeywords.some((kw) => key.toLowerCase().includes(kw))
}

export function StrategyCard({ entry, onConfigure }: Props) {
  const userParams = Object.entries(entry.param_schema).filter(
    ([key]) => !isRiskParam(key),
  )

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3 pb-3">
        <div className="flex flex-col gap-1">
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            {entry.name}
            <Badge variant="outline" className="text-[10px] font-mono">
              {entry.key}
            </Badge>
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

        {/* 参数概要 */}
        {userParams.length > 0 && (
          <div className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">参数:</span>
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
          </div>
        )}

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
