"use client"

import { useState, useCallback, useEffect, useMemo } from "react"
import {
  Dna,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Sparkles,
  ChevronDown,
  ChevronUp,
  ChevronRight,
  CheckSquare,
  Square,
} from "lucide-react"
import { toast } from "sonner"
import { mutate } from "swr"
import { api } from "@/lib/api"
import type { EvolutionResult, StrategyType } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { ParamDiff } from "./param-diff"
import {
  STRATEGY_TYPE_LABEL,
  STRATEGY_TYPE_CATEGORY,
  STRATEGY_CATEGORY_LABEL,
  STRATEGY_CATEGORIES,
  type StrategyCategory,
} from "@/lib/strategy-meta"

/**
 * 全部可参与进化的策略（buyhold 基准策略不参与）
 * 从 STRATEGY_TYPE_LABEL 动态生成，覆盖全部 48 个策略
 */
interface StrategyOption {
  id: string
  label: string
  type: StrategyType
  category: StrategyCategory
}

const ALL_STRATEGIES: StrategyOption[] = (Object.keys(STRATEGY_TYPE_LABEL) as StrategyType[])
  .filter((type) => type !== "buyhold")
  .map((type) => ({
    id: `${type}-btc-usdt`,
    label: STRATEGY_TYPE_LABEL[type],
    type,
    category: STRATEGY_TYPE_CATEGORY[type],
  }))

/** 按分类分组 */
const STRATEGIES_BY_CATEGORY = STRATEGY_CATEGORIES.map((cat) => ({
  category: cat,
  label: STRATEGY_CATEGORY_LABEL[cat],
  items: ALL_STRATEGIES.filter((s) => s.category === cat),
})).filter((g) => g.items.length > 0)

export function EvolutionPanel() {
  // 默认只勾选「趋势跟踪」和「突破」两类（核心可优化策略），避免 48 个全选导致搜索时间过长
  const [selected, setSelected] = useState<Set<string>>(
    new Set(
      ALL_STRATEGIES
        .filter((s) => s.category === "trend" || s.category === "breakout")
        .map((s) => s.id)
    )
  )
  const [autoApply, setAutoApply] = useState(true)
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<EvolutionResult[]>([])
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)
  // 默认全部分类折叠（避免 48 个策略一次展开太长）
  const [collapsedCats, setCollapsedCats] = useState<Set<StrategyCategory>>(
    new Set(STRATEGY_CATEGORIES)
  )

  const toggleStrategy = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const toggleCategory = useCallback((cat: StrategyCategory) => {
    setCollapsedCats((prev) => {
      const next = new Set(prev)
      if (next.has(cat)) next.delete(cat)
      else next.add(cat)
      return next
    })
  }, [])

  /** 全选/反选某个分类 */
  const toggleCategorySelection = useCallback((cat: StrategyCategory) => {
    setSelected((prev) => {
      const next = new Set(prev)
      const catItems = STRATEGIES_BY_CATEGORY.find((g) => g.category === cat)?.items ?? []
      const allSelected = catItems.every((s) => next.has(s.id))
      if (allSelected) {
        catItems.forEach((s) => next.delete(s.id))
      } else {
        catItems.forEach((s) => next.add(s.id))
      }
      return next
    })
  }, [])

  /** 全选/反选全部 */
  const toggleAllSelection = useCallback(() => {
    setSelected((prev) => {
      if (prev.size === ALL_STRATEGIES.length) {
        return new Set()
      }
      return new Set(ALL_STRATEGIES.map((s) => s.id))
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

  // 防重复点击：进化完成后 30 秒内禁止再次点击
  const [cooldown, setCooldown] = useState(0)
  useEffect(() => {
    if (cooldown <= 0) return
    const t = setInterval(() => setCooldown((c) => Math.max(0, c - 1)), 1000)
    return () => clearInterval(t)
  }, [cooldown])

  const onEvolveClick = () => {
    if (cooldown > 0) return
    handleEvolve()
    setCooldown(30)
  }

  const allSelected = selected.size === ALL_STRATEGIES.length

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Dna className="h-4 w-4 text-purple-400" />
          策略参数进化
          <Badge variant="outline" className="ml-1 text-[10px]">
            已选 {selected.size} / {ALL_STRATEGIES.length}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 策略选择器 */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs text-muted-foreground">
              选择要优化的策略（buyhold 基准不参与进化）
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-[11px] gap-1"
              onClick={toggleAllSelection}
            >
              {allSelected ? <Square className="size-3" /> : <CheckSquare className="size-3" />}
              {allSelected ? "清空选择" : "全选"}
            </Button>
          </div>

          {/* 按分类分组展示，每组可折叠 */}
          <div className="space-y-1 rounded-lg border border-border/40 overflow-hidden">
            {STRATEGIES_BY_CATEGORY.map((group) => {
              const collapsed = collapsedCats.has(group.category)
              const catSelectedCount = group.items.filter((s) => selected.has(s.id)).length
              const catAllSelected = catSelectedCount === group.items.length
              return (
                <div key={group.category} className="border-b border-border/30 last:border-b-0">
                  {/* 分类标题行（可折叠 + 全选切换） */}
                  <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-muted/30 hover:bg-muted/50 transition-colors">
                    <button
                      type="button"
                      onClick={() => toggleCategory(group.category)}
                      className="flex items-center gap-1 flex-1 text-left"
                    >
                      {collapsed ? (
                        <ChevronRight className="size-3 text-muted-foreground" />
                      ) : (
                        <ChevronDown className="size-3 text-muted-foreground" />
                      )}
                      <span className="text-xs font-medium">{group.label}</span>
                      <span className="text-[10px] text-muted-foreground">
                        ({catSelectedCount}/{group.items.length})
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => toggleCategorySelection(group.category)}
                      className="text-[10px] text-muted-foreground hover:text-foreground px-1.5 py-0.5 rounded"
                    >
                      {catAllSelected ? "取消" : "全选"}
                    </button>
                  </div>
                  {/* 分类内的策略按钮 */}
                  {!collapsed && (
                    <div className="flex flex-wrap gap-1.5 px-2.5 py-2">
                      {group.items.map((s) => (
                        <button
                          key={s.id}
                          onClick={() => toggleStrategy(s.id)}
                          className={cn(
                            "px-2.5 py-1 rounded-md text-[11px] font-medium border transition-colors",
                            selected.has(s.id)
                              ? "bg-purple-500/15 border-purple-500/40 text-purple-300"
                              : "bg-muted/30 border-border/50 text-muted-foreground hover:bg-muted/50"
                          )}
                        >
                          {s.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
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
            onClick={onEvolveClick}
            disabled={loading || selected.size === 0 || cooldown > 0}
            className="ml-auto bg-purple-600 hover:bg-purple-700 text-white"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                参数搜索中...
              </>
            ) : cooldown > 0 ? (
              <>
                <Sparkles className="h-4 w-4 mr-1.5" />
                冷却中 {cooldown}s
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
