"use client"

import { Pause, Play, Square } from "lucide-react"
import type { Strategy, StrategyStatus } from "@/lib/types"
import { Button } from "@/components/ui/button"

interface Props {
  strategy: Strategy
  onSetStatus: (id: string, status: StrategyStatus) => void
}

export function StrategyControls({ strategy, onSetStatus }: Props) {
  const { id, status } = strategy

  return (
    <div className="flex items-center gap-1.5">
      {status !== "running" ? (
        <Button
          size="sm"
          variant="outline"
          className="h-7 gap-1 px-2 text-xs"
          onClick={() => onSetStatus(id, "running")}
        >
          <Play className="size-3" />
          启动
        </Button>
      ) : (
        <Button
          size="sm"
          variant="outline"
          className="h-7 gap-1 px-2 text-xs"
          onClick={() => onSetStatus(id, "paused")}
        >
          <Pause className="size-3" />
          暂停
        </Button>
      )}
      <Button
        size="sm"
        variant="ghost"
        className="h-7 gap-1 px-2 text-xs text-muted-foreground hover:text-destructive"
        disabled={status === "stopped"}
        onClick={() => onSetStatus(id, "stopped")}
      >
        <Square className="size-3" />
        停止
      </Button>
    </div>
  )
}
