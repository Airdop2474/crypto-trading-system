"use client"

import useSWR from "swr"
import { History, TrendingUp, CheckCircle2, XCircle } from "lucide-react"
import { api } from "@/lib/api"
import type { EvolutionHistoryResponse } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

export function EvolutionHistory() {
  const { data, error, isLoading } = useSWR<EvolutionHistoryResponse>(
    "getEvolutionHistory",
    () => api.getEvolutionHistory(),
    { revalidateOnFocus: false }
  )

  const items = data?.items ?? []
  const stats = data?.stats

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <History className="h-4 w-4 text-muted-foreground" />
          进化历史
          {stats && stats.total_evolutions > 0 && (
            <span className="text-xs font-normal text-muted-foreground ml-auto">
              共 {stats.total_evolutions} 次 · 采纳 {stats.applied_count} 次
              {stats.avg_sharpe_improvement !== 0 && (
                <>
                  {" · "}
                  <TrendingUp className="inline h-3 w-3" />
                  {" "}Sharpe 平均{" "}
                  {stats.avg_sharpe_improvement > 0 ? "+" : ""}
                  {(stats.avg_sharpe_improvement * 100).toFixed(1)}%
                </>
              )}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="text-sm text-muted-foreground animate-pulse">
            加载中...
          </div>
        )}

        {error && (
          <div className="text-sm text-rose-400">
            加载失败：{error.message}
          </div>
        )}

        {!isLoading && !error && items.length === 0 && (
          <div className="text-sm text-muted-foreground">
            暂无进化记录。点击「开始优化」触发首次进化。
          </div>
        )}

        {items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/50">
                  <th className="py-1.5 px-2 text-left font-medium text-muted-foreground">时间</th>
                  <th className="py-1.5 px-2 text-left font-medium text-muted-foreground">策略</th>
                  <th className="py-1.5 px-2 text-right font-medium text-muted-foreground">旧 Sharpe</th>
                  <th className="py-1.5 px-2 text-right font-medium text-muted-foreground">新 Sharpe</th>
                  <th className="py-1.5 px-2 text-center font-medium text-muted-foreground">状态</th>
                  <th className="py-1.5 px-2 text-right font-medium text-muted-foreground">LLM</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, idx) => {
                  const oldSharpe = item.old_metrics?.sharpe_ratio ?? 0
                  const newSharpe = item.new_metrics?.sharpe_ratio
                  const confidence = item.llm_interpretation?.confidence

                  return (
                    <tr key={idx} className="border-b border-border/30">
                      <td className="py-1.5 px-2 text-xs text-muted-foreground whitespace-nowrap">
                        {new Date(item.timestamp).toLocaleString("zh-CN", {
                          month: "2-digit",
                          day: "2-digit",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </td>
                      <td className="py-1.5 px-2 font-medium text-xs">
                        {item.strategy_name}
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums">
                        {oldSharpe.toFixed(3)}
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums">
                        {newSharpe !== undefined && newSharpe !== null
                          ? newSharpe.toFixed(3)
                          : "—"}
                      </td>
                      <td className="py-1.5 px-2 text-center">
                        {item.applied ? (
                          <Badge variant="default" className="bg-emerald-500/20 text-emerald-400 text-xs">
                            <CheckCircle2 className="h-3 w-3 mr-1" />
                            已应用
                          </Badge>
                        ) : item.guardrail_passed ? (
                          <Badge variant="outline" className="text-amber-400 border-amber-400/30 text-xs">
                            待确认
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="text-rose-400/80 border-rose-400/30 text-xs">
                            <XCircle className="h-3 w-3 mr-1" />
                            已拒绝
                          </Badge>
                        )}
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums text-xs">
                        {confidence !== undefined && confidence !== null ? (
                          <span
                            className={cn(
                              confidence >= 0.7 && "text-emerald-400",
                              confidence >= 0.4 && confidence < 0.7 && "text-amber-400",
                              confidence < 0.4 && "text-rose-400"
                            )}
                          >
                            {(confidence * 100).toFixed(0)}%
                          </span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
