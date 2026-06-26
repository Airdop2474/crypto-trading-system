"use client"

import { useState, useEffect } from "react"
import { Activity, AlertTriangle, CheckCircle, Loader2, Play, TrendingDown, TrendingUp, MessageSquare } from "lucide-react"
import { api } from "@/lib/api"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ApiError } from "@/components/api-error"
import { cn } from "@/lib/utils"
import { STRATEGY_TYPE_LABEL } from "@/lib/strategy-meta"
import type { MonteCarloResult } from "@/lib/types"

/**
 * 基于 MC 结果生成自然语言解读：优点 / 缺点 / 建议
 */
function interpretMC(result: MonteCarloResult, strategyLabel: string): {
  pros: string[]
  cons: string[]
  advice: string
  rating: "优秀" | "良好" | "一般" | "谨慎" | "不建议"
} {
  const pros: string[] = []
  const cons: string[] = []
  const ruin = result.ruin_probability
  const retMedian = result.return_distribution?.median ?? 0
  const retP5 = result.return_distribution?.p5 ?? 0
  const ddP95 = result.max_dd_distribution?.p95 ?? 0
  const sharpeMedian = result.sharpe_distribution?.median ?? 0
  const sharpeP5 = result.sharpe_distribution?.p5 ?? 0

  // 优点
  if (retMedian > 0.1) pros.push(`中位预期收益 ${(retMedian * 100).toFixed(1)}%，盈利预期明确`)
  else if (retMedian > 0) pros.push(`中位预期收益为正（${(retMedian * 100).toFixed(1)}%）`)
  if (sharpeMedian > 1.0) pros.push(`风险调整后收益优秀（Sharpe 中位 ${sharpeMedian.toFixed(2)}）`)
  else if (sharpeMedian > 0.5) pros.push(`Sharpe 中位 ${sharpeMedian.toFixed(2)}，风险收益比可接受`)
  if (ruin < 0.01) pros.push(`破产概率极低（${(ruin * 100).toFixed(2)}%），资金安全`)
  if (ddP95 < 0.15) pros.push(`最差回撤可控（95% 分位 ${(ddP95 * 100).toFixed(1)}%）`)

  // 缺点
  if (ruin > 0.05) cons.push(`破产概率${ruin > 0.2 ? "过高" : "偏高"}（${(ruin * 100).toFixed(1)}%），存在爆仓风险`)
  else if (ruin > 0.01) cons.push(`破产概率 ${(ruin * 100).toFixed(2)}%，需关注尾部风险`)
  if (retMedian < 0) cons.push(`中位预期收益为负（${(retMedian * 100).toFixed(1)}%），长期会亏损`)
  if (retP5 < -0.2) cons.push(`5% 分位收益 ${(retP5 * 100).toFixed(1)}%，极端情况下亏损较大`)
  if (ddP95 > 0.3) cons.push(`95% 分位最大回撤 ${(ddP95 * 100).toFixed(1)}%，回撤幅度大`)
  if (sharpeP5 < 0) cons.push(`5% 分位 Sharpe 为负（${sharpeP5.toFixed(2)}），部分场景表现差`)
  if (sharpeMedian < 0.3) cons.push(`Sharpe 中位 ${sharpeMedian.toFixed(2)} 偏低，风险收益比不佳`)

  // 评级
  let rating: "优秀" | "良好" | "一般" | "谨慎" | "不建议" = "一般"
  if (ruin > 0.1 || retMedian < -0.1) rating = "不建议"
  else if (ruin > 0.05 || ddP95 > 0.35 || sharpeMedian < 0.3) rating = "谨慎"
  else if (retMedian > 0.15 && sharpeMedian > 1.0 && ruin < 0.01 && ddP95 < 0.2) rating = "优秀"
  else if (retMedian > 0.05 && sharpeMedian > 0.5 && ruin < 0.05) rating = "良好"

  // 建议
  let advice = ""
  if (rating === "不建议") {
    advice = `${strategyLabel} 在蒙特卡洛重采样下表现不佳，建议优化参数或暂停使用。`
  } else if (rating === "谨慎") {
    advice = `${strategyLabel} 风险较高，建议减小仓位或结合其他策略对冲，并设置严格止损。`
  } else if (rating === "一般") {
    advice = `${strategyLabel} 表现中规中矩，可作为辅助策略使用，但不宜重仓。`
  } else if (rating === "良好") {
    advice = `${strategyLabel} 整体稳健，适合纳入组合，建议控制单策略仓位在 20-30%。`
  } else {
    advice = `${strategyLabel} 各项指标优秀，可作为核心策略使用，但仍建议分散持仓降低单一策略风险。`
  }

  return { pros, cons, advice, rating }
}

const RATING_COLOR: Record<string, string> = {
  "优秀": "bg-green-500/15 text-green-600 border-green-500/30",
  "良好": "bg-blue-500/15 text-blue-600 border-blue-500/30",
  "一般": "bg-yellow-500/15 text-yellow-600 border-yellow-500/30",
  "谨慎": "bg-orange-500/15 text-orange-600 border-orange-500/30",
  "不建议": "bg-red-500/15 text-red-600 border-red-500/30",
}

export function MonteCarloPanel() {
  const [strategyId, setStrategyId] = useState("supertrend-btc-usdt")
  const [method, setMethod] = useState<"trade_bootstrap" | "return_resample">("trade_bootstrap")
  const [result, setResult] = useState<MonteCarloResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [cooldown, setCooldown] = useState(0)

  // 策略 ID → 中文显示文本
  const strategyLabel = (() => {
    const type = strategyId.split("-")[0] as keyof typeof STRATEGY_TYPE_LABEL
    return STRATEGY_TYPE_LABEL[type] ?? strategyId
  })()
  // 方法 → 中文显示文本
  const methodLabel = method === "trade_bootstrap" ? "交易重采样" : "收益重采样"

  const handleRun = async () => {
    if (cooldown > 0) return
    setLoading(true)
    setError(null)
    try {
      const res = await api.runMonteCarlo({ strategy_id: strategyId, method, n_simulations: 1000 })
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e : new Error("未知错误"))
    } finally {
      setLoading(false)
      // 点击后冷却 6 秒，防止快速连续点击触发 429
      setCooldown(6)
    }
  }

  // 冷却倒计时
  useEffect(() => {
    if (cooldown <= 0) return
    const timer = setInterval(() => setCooldown((c) => Math.max(0, c - 1)), 1000)
    return () => clearInterval(timer)
  }, [cooldown])

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Activity className="h-4 w-4" />
          Monte Carlo 模拟
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {/* 参数选择 */}
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">策略</label>
            <Select value={strategyId} onValueChange={(v) => v && setStrategyId(v)}>
              <SelectTrigger className="w-44">
                <SelectValue>{strategyLabel}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="grid-btc-usdt">{STRATEGY_TYPE_LABEL.grid}</SelectItem>
                <SelectItem value="rsi-btc-usdt">{STRATEGY_TYPE_LABEL.rsi}</SelectItem>
                <SelectItem value="ma-btc-usdt">{STRATEGY_TYPE_LABEL.ma}</SelectItem>
                <SelectItem value="donchian-btc-usdt">{STRATEGY_TYPE_LABEL.donchian}</SelectItem>
                <SelectItem value="structure-btc-usdt">{STRATEGY_TYPE_LABEL.structure}</SelectItem>
                <SelectItem value="supertrend-btc-usdt">{STRATEGY_TYPE_LABEL.supertrend}</SelectItem>
                <SelectItem value="reversal-btc-usdt">{STRATEGY_TYPE_LABEL.reversal}</SelectItem>
                <SelectItem value="buyhold-btc-usdt">{STRATEGY_TYPE_LABEL.buyhold}</SelectItem>
                <SelectItem value="priceaction-btc-usdt">{STRATEGY_TYPE_LABEL.priceaction}</SelectItem>
                <SelectItem value="bollinger-btc-usdt">{STRATEGY_TYPE_LABEL.bollinger}</SelectItem>
                <SelectItem value="macd-btc-usdt">{STRATEGY_TYPE_LABEL.macd}</SelectItem>
                <SelectItem value="composite-btc-usdt">{STRATEGY_TYPE_LABEL.composite}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">方法</label>
            <Select value={method} onValueChange={(v) => setMethod(v as typeof method)}>
              <SelectTrigger className="w-40">
                <SelectValue>{methodLabel}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="trade_bootstrap">交易重采样</SelectItem>
                <SelectItem value="return_resample">收益重采样</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button onClick={handleRun} disabled={loading || cooldown > 0}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {cooldown > 0 ? `${cooldown}s` : "运行模拟"}
          </Button>
        </div>

        {/* 错误 */}
        {error && <ApiError error={error} onRetry={handleRun} title="Monte Carlo 模拟失败" />}

        {/* 结果 */}
        {result && !error && (
          <div className="space-y-4">
            {/* 概要统计 */}
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <MetricBox
                label="95% VaR"
                value={`${(result.var_95 * 100).toFixed(2)}%`}
                icon={<TrendingDown className="h-3.5 w-3.5 text-destructive" />}
                sub="95% 置信下最大亏损"
              />
              <MetricBox
                label="95% CVaR"
                value={`${(result.cvar_95 * 100).toFixed(2)}%`}
                icon={<TrendingDown className="h-3.5 w-3.5 text-destructive" />}
                sub="尾部期望亏损"
              />
              <MetricBox
                label="破产概率"
                value={`${(result.ruin_probability * 100).toFixed(1)}%`}
                icon={<AlertTriangle className={cn("h-3.5 w-3.5", result.ruin_probability > 0.05 ? "text-destructive" : "text-muted-foreground")} />}
                sub="P(余额 < 初始 50%)"
              />
              <MetricBox
                label="模拟次数"
                value={result.n_simulations.toLocaleString()}
                icon={<Activity className="h-3.5 w-3.5 text-muted-foreground" />}
                sub={result.method === "trade_bootstrap" ? "交易重采样" : "收益重采样"}
              />
            </div>

            {/* 分布表 */}
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
              <DistributionTable title="收益率分布" dist={result.return_distribution} original={result.original_return} isPct />
              <DistributionTable title="最大回撤分布" dist={result.max_dd_distribution} original={result.original_max_dd} isPct />
              <DistributionTable title="Sharpe 分布" dist={result.sharpe_distribution} original={result.original_sharpe} />
            </div>

            {/* 自然语言解读 */}
            {(() => {
              const interp = interpretMC(result, strategyLabel)
              return (
                <div className="rounded-lg border bg-muted/20 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <MessageSquare className="h-4 w-4 text-primary" />
                      <span className="text-sm font-medium">AI 解读</span>
                    </div>
                    <Badge variant="outline" className={cn("border", RATING_COLOR[interp.rating])}>
                      评级：{interp.rating}
                    </Badge>
                  </div>
                  {interp.pros.length > 0 && (
                    <div className="space-y-1">
                      <div className="flex items-center gap-1.5 text-xs font-medium text-green-600">
                        <CheckCircle className="h-3 w-3" /> 优点
                      </div>
                      <ul className="ml-5 list-disc space-y-0.5 text-xs text-muted-foreground">
                        {interp.pros.map((p, i) => <li key={i}>{p}</li>)}
                      </ul>
                    </div>
                  )}
                  {interp.cons.length > 0 && (
                    <div className="space-y-1">
                      <div className="flex items-center gap-1.5 text-xs font-medium text-red-600">
                        <AlertTriangle className="h-3 w-3" /> 缺点
                      </div>
                      <ul className="ml-5 list-disc space-y-0.5 text-xs text-muted-foreground">
                        {interp.cons.map((c, i) => <li key={i}>{c}</li>)}
                      </ul>
                    </div>
                  )}
                  <div className="rounded bg-primary/5 px-3 py-2 text-xs">
                    <span className="font-medium text-primary">建议：</span>
                    <span className="text-muted-foreground">{interp.advice}</span>
                  </div>
                </div>
              )
            })()}
          </div>
        )}

        {!result && !error && !loading && (
          <div className="text-center text-sm text-muted-foreground py-8">
            选择策略和方法后点击「运行模拟」
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function MetricBox({ label, value, icon, sub }: { label: string; value: string; icon: React.ReactNode; sub: string }) {
  return (
    <div className="rounded-lg border bg-muted/30 p-3">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className="mt-1 font-mono text-lg font-semibold">{value}</div>
      <div className="text-xs text-muted-foreground">{sub}</div>
    </div>
  )
}

function DistributionTable({
  title,
  dist,
  original,
  isPct = false,
}: {
  title: string
  dist?: MonteCarloResult["return_distribution"]
  original?: number
  isPct?: boolean
}) {
  if (!dist) {
    return (
      <div className="rounded-lg border p-3">
        <span className="text-xs font-medium">{title}</span>
        <div className="mt-2 text-xs text-muted-foreground">数据不可用</div>
      </div>
    )
  }
  const fmt = (v: number) => (isPct ? `${(v * 100).toFixed(2)}%` : v.toFixed(3))
  const rows = [
    { label: "均值", value: dist.mean },
    { label: "中位数", value: dist.median },
    { label: "标准差", value: dist.std },
    { label: "5% 分位", value: dist.p5 },
    { label: "95% 分位", value: dist.p95 },
    { label: "最小值", value: dist.min },
    { label: "最大值", value: dist.max },
  ]

  return (
    <div className="rounded-lg border p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-medium">{title}</span>
        <Badge variant="outline" className="text-xs">
          原始: {original != null ? fmt(original) : "N/A"}
        </Badge>
      </div>
      <div className="space-y-1">
        {rows.map((r) => (
          <div key={r.label} className="flex justify-between text-xs">
            <span className="text-muted-foreground">{r.label}</span>
            <span className="font-mono">{fmt(r.value)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
