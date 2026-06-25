"use client"

import useSWR from "swr"
import { Cpu } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { api } from "@/lib/api"
import { ALL_MODES, TRADING_MODES } from "@/lib/mode-meta"
import { ModeCard } from "./mode-card"
import type { ModeState } from "@/lib/types"

const REFRESH_INTERVAL = 3_000 // 3s 状态轮询

export function ModeControls() {
  const { data: modes, mutate } = useSWR<ModeState[]>(
    "modes",
    api.getModes,
    {
      refreshInterval: REFRESH_INTERVAL,
      revalidateOnFocus: false,
    },
  )

  // 检查是否有交易模式正在运行
  const tradingModeRunning =
    modes?.some(
      (m) => TRADING_MODES.includes(m.mode) && m.status === "running",
    ) ?? false

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Cpu className="size-4 text-primary" />
          运行模式控制
        </CardTitle>
        <Badge variant="outline" className="text-xs">
          {modes?.filter((m) => m.status === "running").length ?? 0} 运行中
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 互斥提示 */}
        {tradingModeRunning && (
          <div className="rounded-md border border-warning/30 bg-warning/5 px-3 py-2 text-xs text-warning">
            当前有交易模式运行中。同一时间只能运行一个交易模式（回放纸盘 / 实时纸盘 / 测试网实盘），数据下载不受限制。
          </div>
        )}

        {/* 2x2 网格 */}
        <div className="grid gap-4 lg:grid-cols-2">
          {ALL_MODES.map((mode) => (
            <ModeCard
              key={mode}
              mode={mode}
              state={modes?.find((m) => m.mode === mode)}
              tradingModeRunning={tradingModeRunning}
              onAction={() => mutate()}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
