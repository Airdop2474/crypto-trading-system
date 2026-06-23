"use client"

import { cn } from "@/lib/utils"
import { getParamLabel } from "@/lib/param-labels"

interface ParamDiffProps {
  oldParams: Record<string, number>
  newParams: Record<string, number> | null
}

export function ParamDiff({ oldParams, newParams }: ParamDiffProps) {
  if (!newParams) {
    return (
      <div className="text-sm text-muted-foreground italic">
        未找到更优参数
      </div>
    )
  }

  const allKeys = new Set([...Object.keys(oldParams), ...Object.keys(newParams)])
  const rows = Array.from(allKeys).map((key) => {
    const oldVal = oldParams[key]
    const newVal = newParams[key]
    const changed = oldVal !== newVal && oldVal !== undefined && newVal !== undefined
    const pctChange =
      changed && oldVal !== 0 ? ((newVal - oldVal) / Math.abs(oldVal)) * 100 : null

    return { key, oldVal, newVal, changed, pctChange }
  })

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border/50">
            <th className="py-1.5 px-2 text-left font-medium text-muted-foreground">参数</th>
            <th className="py-1.5 px-2 text-right font-medium text-muted-foreground">旧值</th>
            <th className="py-1.5 px-2 text-right font-medium text-muted-foreground">新值</th>
            <th className="py-1.5 px-2 text-right font-medium text-muted-foreground">变化</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ key, oldVal, newVal, changed, pctChange }) => (
            <tr
              key={key}
              className={cn(
                "border-b border-border/30",
                changed && "bg-muted/30"
              )}
            >
              <td className="py-1.5 px-2 font-mono text-xs">{getParamLabel(key)}</td>
              <td className="py-1.5 px-2 text-right tabular-nums">
                {oldVal !== undefined ? formatNum(oldVal) : "—"}
              </td>
              <td className="py-1.5 px-2 text-right tabular-nums">
                {newVal !== undefined ? formatNum(newVal) : "—"}
              </td>
              <td className="py-1.5 px-2 text-right tabular-nums">
                {pctChange !== null ? (
                  <span
                    className={cn(
                      "font-medium",
                      pctChange > 0 && "text-emerald-400",
                      pctChange < 0 && "text-rose-400"
                    )}
                  >
                    {pctChange > 0 ? "+" : ""}
                    {pctChange.toFixed(1)}%
                  </span>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function formatNum(n: number): string {
  if (Number.isInteger(n)) return n.toString()
  if (Math.abs(n) < 0.01) return n.toFixed(4)
  if (Math.abs(n) < 1) return n.toFixed(3)
  return n.toFixed(2)
}
