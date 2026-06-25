"use client"

import { useState, useEffect } from "react"
import { Activity, AlertTriangle, CheckCircle, Loader2, Play, TrendingDown, TrendingUp } from "lucide-react"
import { api } from "@/lib/api"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ApiError } from "@/components/api-error"
import { cn } from "@/lib/utils"
import { STRATEGY_TYPE_LABEL } from "@/lib/strategy-meta"
import type { MonteCarloResult } from "@/lib/types"

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
  dist: MonteCarloResult["return_distribution"]
  original: number
  isPct?: boolean
}) {
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
          原始: {fmt(original)}
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
