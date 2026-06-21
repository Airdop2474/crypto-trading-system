"use client"

import useSWR from "swr"
import { api } from "@/lib/api"
import { fmtNum } from "@/lib/format"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ApiError } from "@/components/api-error"
import { cn } from "@/lib/utils"

/**
 * 策略相关性矩阵（热力图，纯 SVG 手写）
 *
 * 数据源：GET /analytics/strategy-correlation
 * Pearson 相关系数 [-1, 1]，颜色从红(-1) → 白(0) → 绿(1)
 */
export function StrategyCorrelationCard() {
  const { data, error, isLoading, mutate } = useSWR(
    "strategy-correlation",
    api.getStrategyCorrelation,
    { revalidateOnFocus: false, refreshInterval: 120_000 },
  )

  const strategies = data?.strategies ?? []
  const labels = data?.labels ?? strategies
  const matrix = data?.matrix ?? []
  const n = strategies.length

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">策略相关性矩阵</CardTitle>
      </CardHeader>
      <CardContent>
        {error ? (
          <ApiError error={error} onRetry={() => mutate()} title="相关性矩阵加载失败" minHeight={280} />
        ) : isLoading ? (
          <div className="h-[280px] animate-pulse rounded bg-muted" />
        ) : n < 2 ? (
          <div className="flex h-[280px] items-center justify-center text-sm text-muted-foreground">
            至少需要 2 个策略才能计算相关性
          </div>
        ) : (
          <CorrelationHeatmap labels={labels} matrix={matrix} />
        )}
        {n >= 2 ? (
          <p className="mt-3 border-t border-border pt-2 text-xs text-muted-foreground">
            Pearson 相关系数，基于各策略日 PnL 聚合。值越接近 1 越正相关（同涨同跌），
            越接近 -1 越负相关（对冲）。低于 0.3 视为低相关，适合分散。
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}

function CorrelationHeatmap({
  labels,
  matrix,
}: {
  labels: string[]
  matrix: number[][]
}) {
  const n = labels.length
  // 每格 36px + 标签列 80px
  const cellSize = 36
  const labelWidth = 80
  const labelHeight = 56
  const svgWidth = labelWidth + n * cellSize + 8
  const svgHeight = labelHeight + n * cellSize + 8

  return (
    <div className="overflow-x-auto">
      <svg
        width={svgWidth}
        height={svgHeight}
        viewBox={`0 0 ${svgWidth} ${svgHeight}`}
        className="block"
      >
        {/* 顶部策略标签 */}
        {labels.map((label, j) => (
          <text
            key={`col-${j}`}
            x={labelWidth + j * cellSize + cellSize / 2}
            y={labelHeight - 8}
            textAnchor="start"
            transform={`rotate(-35 ${labelWidth + j * cellSize + cellSize / 2} ${labelHeight - 8})`}
            className="fill-muted-foreground"
            style={{ fontSize: "10px" }}
          >
            {label}
          </text>
        ))}

        {/* 左侧策略标签 */}
        {labels.map((label, i) => (
          <text
            key={`row-${i}`}
            x={labelWidth - 6}
            y={labelHeight + i * cellSize + cellSize / 2 + 3}
            textAnchor="end"
            className="fill-muted-foreground"
            style={{ fontSize: "10px" }}
          >
            {label}
          </text>
        ))}

        {/* 矩阵格子 */}
        {matrix.map((row, i) =>
          row.map((val, j) => {
            const x = labelWidth + j * cellSize
            const y = labelHeight + i * cellSize
            const fill = correlationColor(val)
            const isDiagonal = i === j
            return (
              <g key={`${i}-${j}`}>
                <rect
                  x={x}
                  y={y}
                  width={cellSize - 1}
                  height={cellSize - 1}
                  fill={fill}
                  stroke="var(--border)"
                  strokeWidth={0.5}
                />
                <text
                  x={x + cellSize / 2}
                  y={y + cellSize / 2 + 3}
                  textAnchor="middle"
                  className={cn(
                    "font-mono tabular-nums",
                    Math.abs(val) > 0.6 ? "fill-white" : "fill-foreground",
                  )}
                  style={{ fontSize: "10px", fontWeight: isDiagonal ? 600 : 400 }}
                >
                  {fmtNum(val, 2)}
                </text>
              </g>
            )
          }),
        )}
      </svg>
    </div>
  )
}

/** 相关系数 → 颜色：-1 红 → 0 中性 → 1 绿 */
function correlationColor(v: number): string {
  // v ∈ [-1, 1]
  if (v >= 0) {
    // 0 → 中性灰，1 → 绿
    const alpha = v * 0.7
    return `rgba(34, 197, 94, ${alpha})`  // success green
  } else {
    const alpha = Math.abs(v) * 0.7
    return `rgba(239, 68, 68, ${alpha})`  // destructive red
  }
}
