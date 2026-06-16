"use client"

import type { Strategy } from "@/lib/types"
import { cn } from "@/lib/utils"
import { fmtNum } from "@/lib/format"

// 简单的网格区间可视化：在上下限之间均匀绘制价格线，
// 当前价位置高亮，已成交区间用主色填充。
export function GridVisual({ strategy }: { strategy: Strategy }) {
  const g = strategy.grid
  if (!g) return null

  const lines = 12
  const range = g.upperPrice - g.lowerPrice
  // 用已成交比例推算当前价位置
  const currentRatio = g.filledGrids / g.gridCount
  const currentPrice = g.lowerPrice + range * currentRatio

  return (
    <div className="flex items-stretch gap-3">
      <div className="relative flex-1">
        <div className="flex h-40 flex-col-reverse justify-between">
          {Array.from({ length: lines }).map((_, i) => {
            const ratio = i / (lines - 1)
            const filled = ratio <= currentRatio
            return (
              <div key={i} className="flex items-center gap-2">
                <div
                  className={cn(
                    "h-px flex-1",
                    filled ? "bg-primary/50" : "bg-border",
                  )}
                />
              </div>
            )
          })}
        </div>
        {/* 当前价标记 */}
        <div
          className="absolute inset-x-0 flex items-center gap-2"
          style={{ bottom: `${currentRatio * 100}%` }}
        >
          <div className="h-px flex-1 bg-success" />
          <span className="rounded bg-success/15 px-1.5 py-0.5 font-mono text-[10px] tabular-nums text-success">
            {fmtNum(currentPrice, currentPrice < 10 ? 3 : 1)}
          </span>
        </div>
      </div>
      <div className="flex flex-col justify-between py-0.5 text-right font-mono text-[11px] tabular-nums text-muted-foreground">
        <span>{fmtNum(g.upperPrice, g.upperPrice < 10 ? 3 : 0)}</span>
        <span>上限</span>
        <span className="mt-auto">下限</span>
        <span>{fmtNum(g.lowerPrice, g.lowerPrice < 10 ? 3 : 0)}</span>
      </div>
    </div>
  )
}
