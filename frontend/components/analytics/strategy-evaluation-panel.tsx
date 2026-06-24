"use client"

import { useState } from "react"
import { CheckCircle, AlertTriangle, XCircle, Loader2, Play, Award } from "lucide-react"
import { api } from "@/lib/api"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ApiError } from "@/components/api-error"
import { cn } from "@/lib/utils"
import type { StrategyEvaluation } from "@/lib/types"

const VERDICT_META = {
  KEEP: { label: "保留", icon: CheckCircle, color: "text-success", bg: "bg-success/10 border-success/30" },
  WARN: { label: "警告", icon: AlertTriangle, color: "text-warning", bg: "bg-warning/10 border-warning/30" },
  ELIMINATE: { label: "淘汰", icon: XCircle, color: "text-destructive", bg: "bg-destructive/10 border-destructive/30" },
} as const

export function StrategyEvaluationPanel() {
  const [results, setResults] = useState<StrategyEvaluation[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const handleRun = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.runStrategyEvaluation({ days: 180, n_mc_simulations: 1000 })
      setResults(res)
    } catch (e) {
      setError(e instanceof Error ? e : new Error("未知错误"))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Award className="h-4 w-4" />
            策略评估与淘汰
          </span>
          <Button onClick={handleRun} disabled={loading} size="sm">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            运行评估
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {error && <ApiError error={error} onRetry={handleRun} title="策略评估失败" />}

        {results && !error && (
          <>
            {/* 汇总 */}
            <div className="flex gap-3">
              {(["KEEP", "WARN", "ELIMINATE"] as const).map((v) => {
                const count = results.filter((r) => r.verdict === v).length
                const meta = VERDICT_META[v]
                const Icon = meta.icon
                return (
                  <div key={v} className={cn("flex-1 rounded-lg border p-3 text-center", meta.bg)}>
                    <Icon className={cn("mx-auto h-5 w-5", meta.color)} />
                    <div className="mt-1 text-2xl font-bold">{count}</div>
                    <div className="text-xs text-muted-foreground">{meta.label}</div>
                  </div>
                )
              })}
            </div>

            {/* 策略表格 */}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-xs text-muted-foreground">
                    <th className="py-2 pr-3 text-left">策略</th>
                    <th className="px-3 text-right">总分</th>
                    <th className="px-3 text-right">Sharpe</th>
                    <th className="px-3 text-right">回撤</th>
                    <th className="px-3 text-right">MC中位</th>
                    <th className="px-3 text-right">破产率</th>
                    <th className="px-3 text-right">稳定性</th>
                    <th className="px-3 text-center">结论</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r) => {
                    const meta = VERDICT_META[r.verdict] ?? VERDICT_META.WARN
                    const Icon = meta.icon
                    return (
                      <tr key={r.strategy_name} className="border-b last:border-0">
                        <td className="py-2 pr-3 font-medium">{r.strategy_name}</td>
                        <td className="px-3 text-right font-mono">{r.total_score.toFixed(1)}</td>
                        <td className={cn("px-3 text-right font-mono", r.sharpe_ratio < 0.3 && "text-destructive")}>
                          {r.sharpe_ratio.toFixed(2)}
                        </td>
                        <td className={cn("px-3 text-right font-mono", r.max_drawdown > 0.25 && "text-destructive")}>
                          {(r.max_drawdown * 100).toFixed(1)}%
                        </td>
                        <td className={cn("px-3 text-right font-mono", r.mc_return_median < 0 && "text-destructive")}>
                          {(r.mc_return_median * 100).toFixed(1)}%
                        </td>
                        <td className={cn("px-3 text-right font-mono", r.mc_ruin_prob > 0.05 && "text-destructive")}>
                          {(r.mc_ruin_prob * 100).toFixed(1)}%
                        </td>
                        <td className={cn("px-3 text-right font-mono", r.param_stability < 0.4 && "text-destructive")}>
                          {r.param_stability.toFixed(3)}
                        </td>
                        <td className="px-3 text-center">
                          <Badge variant="outline" className={cn("gap-1", meta.bg, meta.color, "border-current/20")}>
                            <Icon className="h-3 w-3" />
                            {meta.label}
                          </Badge>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* 淘汰标记 */}
            {results.some((r) => r.elimination_flags.length > 0) && (
              <div className="space-y-1.5">
                <div className="text-xs font-medium text-muted-foreground">淘汰标记</div>
                {results
                  .filter((r) => r.elimination_flags.length > 0)
                  .map((r) => (
                    <div key={r.strategy_name} className="flex items-start gap-2 text-xs">
                      <span className="font-medium">{r.strategy_name}:</span>
                      <div className="flex flex-wrap gap-1">
                        {r.elimination_flags.map((flag, i) => (
                          <Badge key={i} variant="outline" className="text-destructive border-destructive/30">
                            {flag}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  ))}
              </div>
            )}
          </>
        )}

        {!results && !error && !loading && (
          <div className="text-center text-sm text-muted-foreground py-8">
            点击「运行评估」对 12 策略进行全面评估（含 MC 模拟 + 参数稳定性）
          </div>
        )}
      </CardContent>
    </Card>
  )
}
