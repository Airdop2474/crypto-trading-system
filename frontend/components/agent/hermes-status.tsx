"use client"

import useSWR from "swr"
import { api } from "@/lib/api"
import type { HermesStatus } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Bot, Wifi, WifiOff, FileText } from "lucide-react"

export function HermesStatusCard() {
  const { data } = useSWR<HermesStatus>("getHermesStatus", () => api.getHermesStatus(), {
    revalidateOnFocus: false,
    dedupingInterval: 10_000,
  })

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Bot className="size-4 text-violet-400" />
          Hermes Agent
          {data?.available ? (
            <Wifi className="size-3.5 text-emerald-400 ml-auto" />
          ) : (
            <WifiOff className="size-3.5 text-muted-foreground ml-auto" />
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-3 gap-4 text-center">
        <div>
          <p className="text-lg font-semibold tabular-nums">
            {data?.available ? "在线" : "离线"}
          </p>
          <p className="text-[11px] text-muted-foreground">连接状态</p>
        </div>
        <div>
          <p className="text-lg font-semibold tabular-nums">{data?.pending_events ?? 0}</p>
          <p className="text-[11px] text-muted-foreground">待处理事件</p>
        </div>
        <div>
          <p className="text-lg font-semibold tabular-nums">{data?.completed_analyses ?? 0}</p>
          <p className="text-[11px] text-muted-foreground">已完成分析</p>
        </div>
      </CardContent>
    </Card>
  )
}
