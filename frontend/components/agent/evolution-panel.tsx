"use client"

import { useState, useCallback } from "react"
import {
  Dna,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Sparkles,
  ChevronDown,
  ChevronUp,
} from "lucide-react"
import { toast } from "sonner"
import { mutate } from "swr"
import { api } from "@/lib/api"
import type { EvolutionResult } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { ParamDiff } from "./param-diff"

const ALL_STRATEGIES = [
  { id: "grid-btc-usdt", label: "网格策略", type: "grid" },
  { id: "rsi-btc-usdt", label: "RSI 动量", type: "rsi" },
  { id: "ma-btc-usdt", label: "均线策略", type: "ma" },
  { id: "donchian-btc-usdt", label: "唐奇安通道", type: "donchian" },
  { id: "structure-btc-usdt", label: "市场结构", type: "structure" },
  { id: "supertrend-btc-usdt", label: "SuperTrend", type: "supertrend" },
  { id: "reversal-btc-usdt", label: "关键位反转", type: "reversal" },
  { id: "priceaction-btc-usdt", label: "价格行为学", type: "priceaction" },
  { id: "bollinger-btc-usdt", label: "布林带均值回归", type: "bollinger" },
  { id: "macd-btc-usdt", label: "MACD 趋势跟踪", type: "macd" },
  { id: "composite-btc-usdt", label: "复合趋势", type: "composite" },
] as const

export function EvolutionPanel() {
  const [selected, setSelected] = useState<Set<string>>(
    new Set(ALL_STRATEGIES.map((s) => s.id))
  )
  const [autoApply, setAutoApply] = useState(true)
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<EvolutionResult[]>([])
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)

  const toggleStrategy = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const handleEvolve = useCallback(async () => {
    if (selected.size === 0) {
      toast.error("请至少选择一个策略")
      return
    }

    setLoading(true)
    setResults([])
    setExpandedIdx(null)

    try {
      const res = await api.runEvolution({
        strategy_ids: Array.from(selected),
        auto_apply: autoApply,
      })
      setResults(res)
      toast.success(
        `进化完成：${res.filter((r) => r.applied).length} 个已应用，${res.filter((r) => !r.guardrail_passed).length} 个被拒绝`
      )
      // 刷新历史记录
      mutate("getEvolutionHistory")
      mutate("getEvolutionStats")
    } catch (err) {
      const msg = err instanceof Error ? err.message : "未知错误"
      toast.error(`进化失败：${msg}`)
    } finally {
      setLoading(false)
    }
  }, [selected, autoApply])

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Dna className="h-4 w-4 text-purple-400" />
          策略参数进化
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 策略选择器 */}
        <div>
          <div className="text-xs text-muted-foreground mb-2">
            选择要优化的策略（买入持有基准策略不参与进化）
          </div>
          <div className="flex flex-wrap gap-2">
            {ALL_STRATEGIES.map((s) => (
              <button
                key={s.id}
                onClick={() => toggleStrategy(s.id)}
                className={cn(
                  "px-3 py-1.5 rounded-md text-xs font-medium border transition-colors",
                  selected.has(s.id)
                    ? "bg-purple-500/15 border-purple-500/40 text-purple-300"
                    : "bg-muted/30 border-border/50 text-muted-foreground hover:bg-muted/50"
                )}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>

        {/* 控制区 */}
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
            <input
              type="checkbox"
              checked={autoApply}
              onChange={(e) => setAutoApply(e.target.checked)}
              className="rounded border-border accent-purple-500"
            />
            <span className="text-muted-foreground">
              安全阈值通过时自动应用
            </span>
          </label>
          <Button
            size="sm"
            onClick={handleEvolve}
            disabled={loading || selected.size === 0}
            className="ml-auto bg-purple-600 hover:bg-purple-700 text-white"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                参数搜索中...
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4 mr-1.5" />
                开始优化
              </>
            )}
          </Button>
        </div>

        {/* 加载提示 */}
        {loading && (
          <div className="text-center py-6 space-y-2">
            <Loader2 className="h-6 w-6 mx-auto animate-spin text-purple-400" />
            <p className="text-sm text-muted-foreground">
              正在执行参数搜索，预计需要 10-30 秒...
            </p>
          </div>
        )}

        {/* 结果卡片 */}
        {!loading && results.length > 0 && (
          <div className="space-y-3">
            {results.map((r, idx) => (
              <ResultCard
                key={r.strategy_id}
                result={r}
                expanded={expandedIdx === idx}
                onToggle={() =>
                  setExpandedIdx(expandedIdx === idx ? null : idx)
                }
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function ResultCard({
  result,
  expanded,
  onToggle,
}: {
  result: EvolutionResult
  expanded: boolean
  onToggle: () => void
}) {
  const statusIcon = result.applied ? (
    <CheckCircle2 className="h-4 w-4 text-emerald-400" />
  ) : result.guardrail_passed ? (
    <AlertTriangle className="h-4 w-4 text-amber-400" />
  ) : (
    <XCircle className="h-4 w-4 text-rose-400" />
  )

  const statusLabel = result.applied
    ? "已应用"
    : result.guardrail_passed
      ? "通过 · 待应用"
      : "已拒绝"

  const statusColor = result.applied
    ? "bg-emerald-500/20 text-emerald-400"
    : result.guardrail_passed
      ? "bg-amber-500/20 text-amber-400"
      : "bg-rose-500/20 text-rose-400"

  const oldSharpe = result.old_metrics?.sharpe_ratio ?? 0
  const newSharpe = result.new_metrics?.sharpe_ratio
  const sharpeDelta = newSharpe !== undefined && newSharpe !== null ? newSharpe - oldSharpe : null

  return (
    <div className="rounded-lg border border-border/50 overflow-hidden">
      {/* 头部 */}
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-muted/30 transition-colors"
      >
        {statusIcon}
        <span className="font-medium text-sm">{result.strategy_name}</span>
        <Badge variant="outline" className={cn("text-xs ml-1", statusColor)}>
          {statusLabel}
        </Badge>

        {sharpeDelta !== null && (
          <span
            className={cn(
              "text-xs tabular-nums ml-auto mr-2",
              sharpeDelta > 0 && "text-emerald-400",
              sharpeDelta < 0 && "text-rose-400",
              sharpeDelta === 0 && "text-muted-foreground"
            )}
          >
            Sharpe {sharpeDelta > 0 ? "+" : ""}
            {sharpeDelta.toFixed(3)}
          </span>
        )}

        {expanded ? (
          <ChevronUp className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        )}
      </button>

      {/* 展开详情 */}
      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-border/30">
          {/* 指标对比 */}
          <div className="grid grid-cols-3 gap-3 mt-3">
            <MetricBox
              label="Sharpe"
              old={result.old_metrics?.sharpe_ratio}
              new={result.new_metrics?.sharpe_ratio}
            />
            <MetricBox
              label="最大回撤"
              old={result.old_metrics?.max_drawdown}
              new={result.new_metrics?.max_drawdown}
              isPercent
              lowerIsBetter
            />
            <MetricBox
              label="总收益"
              old={result.old_metrics?.total_return}
              new={result.new_metrics?.total_return}
              isPercent
            />
          </div>

          {/* 参数对比 */}
          <div>
            <div className="text-xs font-medium text-muted-foreground mb-1">
              参数变化
            </div>
            <ParamDiff
              oldParams={result.old_params}
              newParams={result.new_params}
            />
          </div>

          {/* Guardrail 原因 */}
          {result.guardrail_reasons.length > 0 && (
            <div>
              <div className="text-xs font-medium text-muted-foreground mb-1">
                安全校验
              </div>
              <div className="text-xs space-y-0.5">
                {result.guardrail_reasons.map((reason, i) => (
                  <div key={i} className="text-rose-400/80">
                    · {reason}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* LLM 解读 */}
          {result.llm_interpretation && (
            <div>
              <div className="text-xs font-medium text-muted-foreground mb-1">
                AI 解读
                {result.llm_interpretation.provider !== "local" && (
                  <span className="ml-1 text-purple-400">
                    ({result.llm_interpretation.provider})
                  </span>
                )}
              </div>
              <div className="text-xs space-y-1">
                <p>{result.llm_interpretation.summary}</p>
                {result.llm_interpretation.reasoning && (
                  <p className="text-muted-foreground">
                    {result.llm_interpretation.reasoning}
                  </p>
                )}
                {result.llm_interpretation.risks && (
                  <p className="text-amber-400/80">
                    风险：{result.llm_interpretation.risks}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* 元信息 */}
          <div className="text-xs text-muted-foreground pt-1 border-t border-border/30">
            {result.walk_forward_windows} 个验证窗口 ·{" "}
            {new Date(result.timestamp).toLocaleString("zh-CN")}
          </div>
        </div>
      )}
    </div>
  )
}

function MetricBox({
  label,
  old,
  new: newVal,
  isPercent = false,
  lowerIsBetter = false,
}: {
  label: string
  old?: number
  new?: number | null
  isPercent?: boolean
  lowerIsBetter?: boolean
}) {
  if (old === undefined && (newVal === undefined || newVal === null)) {
    return (
      <div className="rounded bg-muted/20 px-3 py-2">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="text-sm">—</div>
      </div>
    )
  }

  const format = (v: number) =>
    isPercent ? `${(v * 100).toFixed(1)}%` : v.toFixed(3)

  const delta =
    newVal !== undefined && newVal !== null && old !== undefined
      ? newVal - old
      : null
  const improved =
    delta !== null
      ? lowerIsBetter
        ? delta < 0
        : delta > 0
      : false

  return (
    <div className="rounded bg-muted/20 px-3 py-2">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-sm tabular-nums flex items-baseline gap-1.5">
        <span>{old !== undefined ? format(old) : "—"}</span>
        {newVal !== undefined && newVal !== null && (
          <>
            <span className="text-muted-foreground">→</span>
            <span
              className={cn(
                "font-medium",
                improved && "text-emerald-400",
                delta !== null && !improved && delta !== 0 && "text-rose-400"
              )}
            >
              {format(newVal)}
            </span>
          </>
        )}
      </div>
    </div>
  )
}
