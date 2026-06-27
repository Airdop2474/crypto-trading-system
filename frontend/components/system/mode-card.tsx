"use client"

import { useState, useCallback } from "react"
import useSWR from "swr"
import { Play, Square, ChevronDown, ChevronUp, CheckCircle, AlertTriangle, XCircle, Loader2, Database, ChevronRight } from "lucide-react"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"
import { api } from "@/lib/api"
import { toast } from "sonner"
import {
  MODE_LABEL,
  MODE_DESCRIPTION,
  MODE_ICON,
  MODE_COLOR,
  STATUS_DOT_COLOR,
  STATUS_LABEL,
  MODE_DEFAULTS,
} from "@/lib/mode-meta"
import {
  STRATEGY_TYPE_CATEGORY,
  STRATEGY_CATEGORY_LABEL,
  STRATEGY_CATEGORIES,
  type StrategyCategory,
} from "@/lib/strategy-meta"

/** 市场类型 → 中文标签（key 须与后端 app.py 一致：oscillating / trending / black_swan / random） */
const MARKET_TYPE_LABEL: Record<string, string> = {
  random: "随机",
  oscillating: "震荡",
  trending: "趋势",
  black_swan: "黑天鹅",
}
import { ModeLogViewer } from "./mode-log-viewer"
import type { ModeState, RunningMode, StartModeParams, TestnetValidationResult } from "@/lib/types"

interface ModeCardProps {
  mode: RunningMode
  state: ModeState | undefined
  tradingModeRunning: boolean
  onAction: () => void
}

/** 格式化运行时长 */
function formatUptime(seconds: number | null): string {
  if (seconds == null) return ""
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m`
  return `${seconds}s`
}

export function ModeCard({ mode, state, tradingModeRunning, onAction }: ModeCardProps) {
  const Icon = MODE_ICON[mode]
  const defaults = MODE_DEFAULTS[mode]
  const status = state?.status ?? "idle"
  const isRunning = status === "running" || status === "stopping"
  const isIdle = status === "idle"
  const isTestnet = mode === "testnet_live"

  // 参数状态
  const [symbol, setSymbol] = useState(defaults.symbol)
  const [timeframe, setTimeframe] = useState(defaults.timeframe)
  const [days, setDays] = useState(defaults.days)
  const [initialCapital, setInitialCapital] = useState(defaults.initialCapital)
  const [pollSeconds, setPollSeconds] = useState(defaults.pollSeconds)
  const [replayCsv, setReplayCsv] = useState("")
  const [fresh, setFresh] = useState(false)
  const [marketType, setMarketType] = useState("oscillating")

  // UI 状态
  const [showParams, setShowParams] = useState(false)
  const [showLogs, setShowLogs] = useState(false)
  const [loading, setLoading] = useState(false)
  const [validating, setValidating] = useState(false)
  const [validation, setValidation] = useState<TestnetValidationResult | null>(null)

  // 互斥：其他交易模式运行时，本交易模式不可启动
  const startDisabled = isRunning || tradingModeRunning

  // 策略注册表（用于启动参数选策略）
  const { data: registryData } = useSWR("strategy-registry", () => api.getStrategyRegistry(), {
    revalidateOnFocus: false,
    dedupingInterval: 60_000,
  })
  // 策略归档状态（archived 的策略显示灰色，默认不勾选）
  const { data: statusData, mutate: mutateStatus } = useSWR(
    "strategies-status",
    () => api.getStrategiesStatus(),
    { revalidateOnFocus: false, dedupingInterval: 60_000 }
  )
  const strategyLabels: Record<string, string> = Object.fromEntries(
    (registryData?.strategies ?? []).map((e) => [e.key, e.name])
  )
  /** 判断策略是否已归档/禁用 */
  const isArchived = useCallback((key: string): boolean => {
    const entry = statusData?.[key]
    return entry?.status === "archived" || entry?.status === "disabled"
  }, [statusData])
  const [selectedStrategies, setSelectedStrategies] = useState<string[]>([])
  // 分类折叠状态（默认全折叠，避免 49 个 checkbox 平铺太长）
  const [collapsedCats, setCollapsedCats] = useState<Set<StrategyCategory>>(
    new Set(STRATEGY_CATEGORIES)
  )

  /** 按分类分组策略 */
  const strategiesByCategory = STRATEGY_CATEGORIES.map((cat) => ({
    category: cat,
    label: STRATEGY_CATEGORY_LABEL[cat],
    items: Object.entries(strategyLabels)
      .filter(([key]) => STRATEGY_TYPE_CATEGORY[key as keyof typeof STRATEGY_TYPE_CATEGORY] === cat)
      .map(([key, name]) => ({ key, name })),
  })).filter((g) => g.items.length > 0)

  /** 全选/反选某个分类 */
  const toggleCategorySelection = useCallback((cat: StrategyCategory) => {
    setSelectedStrategies((prev) => {
      const catItems = strategiesByCategory.find((g) => g.category === cat)?.items ?? []
      const allSelected = catItems.every((s) => prev.includes(s.key))
      if (allSelected) {
        return prev.filter((s) => !catItems.some((item) => item.key === s))
      } else {
        return [...new Set([...prev, ...catItems.map((s) => s.key)])]
      }
    })
  }, [strategiesByCategory])

  /** 全选/反选全部 */
  const toggleAllSelection = useCallback(() => {
    setSelectedStrategies((prev) => {
      const allKeys = Object.keys(strategyLabels)
      if (prev.length === allKeys.length) return []
      return allKeys
    })
  }, [strategyLabels])

  /** 折叠/展开分类 */
  const toggleCategoryCollapse = useCallback((cat: StrategyCategory) => {
    setCollapsedCats((prev) => {
      const next = new Set(prev)
      if (next.has(cat)) next.delete(cat)
      else next.add(cat)
      return next
    })
  }, [])

  const handleStart = useCallback(async () => {
    setLoading(true)
    try {
      const params: StartModeParams = {
        symbol,
        timeframe,
        days,
        initialCapital,
      }
      if (defaults.showPollSeconds) params.pollSeconds = pollSeconds
      if (defaults.showReplayCsv) params.replayCsv = replayCsv || undefined
      if (defaults.showMarketType) params.marketType = marketType
      if (fresh) params.fresh = true
      if (selectedStrategies.length > 0) params.strategies = selectedStrategies

      await api.startMode(mode, params)
      toast.success(`${MODE_LABEL[mode]} 已启动`)
      onAction()
    } catch (e) {
      const msg = e instanceof Error ? e.message : "启动失败"
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }, [mode, symbol, timeframe, days, initialCapital, pollSeconds, replayCsv, marketType, fresh, selectedStrategies, defaults, onAction])

  const handleStop = useCallback(async () => {
    setLoading(true)
    try {
      await api.stopMode(mode)
      toast.success(`${MODE_LABEL[mode]} 已停止`)
      onAction()
    } catch (e) {
      const msg = e instanceof Error ? e.message : "停止失败"
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }, [mode, onAction])

  const handleValidate = useCallback(async () => {
    setValidating(true)
    try {
      const result = await api.validateTestnet()
      setValidation(result)
      if (result.ok) {
        toast.success("测试网验证通过")
      } else {
        toast.error("测试网验证未通过")
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "验证失败"
      toast.error(msg)
    } finally {
      setValidating(false)
    }
  }, [])

  return (
    <Card className={cn("overflow-hidden transition-colors", isRunning && "border-success/30")}>
      <CardHeader className="flex-row items-center justify-between gap-3 p-4 pb-2">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className={cn("flex items-center justify-center size-8 rounded-md border", MODE_COLOR[mode])}>
            <Icon className="size-4" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-medium truncate">{MODE_LABEL[mode]}</h3>
              <div className="flex items-center gap-1.5">
                <div className={cn("size-2 rounded-full", STATUS_DOT_COLOR[status])} />
                <span className="text-[11px] text-muted-foreground">{STATUS_LABEL[status]}</span>
              </div>
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5 truncate">
              {MODE_DESCRIPTION[mode]}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {isRunning && state?.uptimeSeconds != null && (
            <Badge variant="outline" className="text-[10px] h-5 tabular-nums">
              {formatUptime(state.uptimeSeconds)}
            </Badge>
          )}
          {status === "error" && state?.exitCode != null && (
            <Badge variant="destructive" className="text-[10px] h-5">
              exit {state.exitCode}
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="px-4 pb-3 pt-0 space-y-3">
        {/* 操作按钮 */}
        <div className="flex items-center gap-2">
          {isIdle ? (
            <Button
              size="sm"
              className="h-7 gap-1.5 text-xs"
              onClick={handleStart}
              disabled={startDisabled || loading}
            >
              {loading ? <Loader2 className="size-3 animate-spin" /> : <Play className="size-3" />}
              启动
            </Button>
          ) : (
            <Button
              size="sm"
              variant="destructive"
              className="h-7 gap-1.5 text-xs"
              onClick={handleStop}
              disabled={status === "stopping" || loading}
            >
              {loading ? <Loader2 className="size-3 animate-spin" /> : <Square className="size-3" />}
              {status === "stopping" ? "停止中…" : "停止"}
            </Button>
          )}

          {isTestnet && isIdle && (
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1.5 text-xs"
              onClick={handleValidate}
              disabled={validating || loading}
            >
              {validating ? <Loader2 className="size-3 animate-spin" /> : null}
              验证测试网
            </Button>
          )}

          <Button
            size="sm"
            variant="ghost"
            className="h-7 gap-1 text-xs ml-auto"
            onClick={() => setShowParams(!showParams)}
            disabled={isRunning}
          >
            参数
            {showParams ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
          </Button>

          <Button
            size="sm"
            variant="ghost"
            className="h-7 gap-1 text-xs"
            onClick={() => setShowLogs(!showLogs)}
          >
            {showLogs ? "收起日志" : "查看日志"}
          </Button>
        </div>

        {/* Testnet 验证结果 */}
        {isTestnet && validation && (
          <div className="rounded-md border border-border/60 bg-muted/30 p-2 space-y-1">
            {validation.checks.map((check, i) => (
              <div key={i} className="flex items-start gap-1.5 text-[11px]">
                {check.status === "PASS" ? (
                  <CheckCircle className="size-3 text-success mt-0.5 shrink-0" />
                ) : check.status === "WARN" ? (
                  <AlertTriangle className="size-3 text-warning mt-0.5 shrink-0" />
                ) : (
                  <XCircle className="size-3 text-destructive mt-0.5 shrink-0" />
                )}
                <span className="text-muted-foreground">
                  <span className="font-medium text-foreground">{check.name}</span>
                  {check.detail && `: ${check.detail}`}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* 参数表单 */}
        {showParams && isIdle && (
          <div className="grid grid-cols-2 gap-x-3 gap-y-2 rounded-md border border-border/60 bg-muted/20 p-3">
            <div className="col-span-2">
              <Label className="text-[11px]">交易对</Label>
              <Input
                className="h-7 text-xs mt-0.5"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
              />
            </div>
            <div>
              <Label className="text-[11px]">时间周期</Label>
              <Select value={timeframe} onValueChange={(v: string | null) => { if (v) setTimeframe(v) }}>
                <SelectTrigger className="h-7 text-xs mt-0.5">
                  {timeframe}
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1m">1m</SelectItem>
                  <SelectItem value="5m">5m</SelectItem>
                  <SelectItem value="15m">15m</SelectItem>
                  <SelectItem value="1h">1h</SelectItem>
                  <SelectItem value="4h">4h</SelectItem>
                  <SelectItem value="1d">1d</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-[11px]">运行天数</Label>
              <Input
                className="h-7 text-xs mt-0.5"
                type="number"
                min={1}
                max={365}
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
              />
            </div>
            <div>
              <Label className="text-[11px]">初始资金 (USDT)</Label>
              <Input
                className="h-7 text-xs mt-0.5"
                type="number"
                min={100}
                max={1000000}
                value={initialCapital}
                onChange={(e) => setInitialCapital(Number(e.target.value))}
              />
            </div>
            {defaults.showMarketType && (
              <div className="col-span-2">
                <Label className="text-[11px]">市场类型</Label>
                <Select
                  value={marketType}
                  onValueChange={(v) => setMarketType(v ?? "oscillating")}
                >
                  <SelectTrigger className="h-7 text-xs mt-0.5">
                    {MARKET_TYPE_LABEL[marketType] ?? "选择市场类型"}
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="random" className="text-xs">随机</SelectItem>
                    <SelectItem value="oscillating" className="text-xs">震荡</SelectItem>
                    <SelectItem value="trending" className="text-xs">趋势</SelectItem>
                    <SelectItem value="black_swan" className="text-xs">黑天鹅</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
            {defaults.showPollSeconds && (
              <div>
                <Label className="text-[11px]">轮询间隔 (秒)</Label>
                <Input
                  className="h-7 text-xs mt-0.5"
                  type="number"
                  min={10}
                  max={600}
                  value={pollSeconds}
                  onChange={(e) => setPollSeconds(Number(e.target.value))}
                />
              </div>
            )}
            {defaults.showReplayCsv && (
              <div className="col-span-2">
                <Label className="text-[11px]">回放数据（CSV 路径或留空自动生成）</Label>
                <Input
                  className="h-7 text-xs mt-0.5"
                  placeholder="留空 = 生成模拟数据"
                  value={replayCsv}
                  onChange={(e) => setReplayCsv(e.target.value)}
                />
              </div>
            )}
            {/* 策略选择（按分类分组，可折叠） */}
            {true && (
              <div className="col-span-2 space-y-1">
                <div className="flex items-center justify-between">
                  <Label className="text-[11px]">
                    运行策略
                    {selectedStrategies.length > 0 && (
                      <span className="ml-1.5 text-muted-foreground">
                        (已选 {selectedStrategies.length})
                      </span>
                    )}
                  </Label>
                  <button
                    type="button"
                    onClick={toggleAllSelection}
                    className="text-[10px] text-muted-foreground hover:text-foreground"
                  >
                    {selectedStrategies.length === Object.keys(strategyLabels).length
                      ? "清空"
                      : "全选"}
                  </button>
                </div>
                <div className="rounded-md border border-border/40 overflow-hidden mt-1">
                  {strategiesByCategory.map((group) => {
                    const collapsed = collapsedCats.has(group.category)
                    const catSelectedCount = group.items.filter((s) =>
                      selectedStrategies.includes(s.key)
                    ).length
                    const catAllSelected = catSelectedCount === group.items.length
                    return (
                      <div key={group.category} className="border-b border-border/30 last:border-b-0">
                        {/* 分类标题行 */}
                        <div className="flex items-center gap-1.5 px-2 py-1.5 bg-muted/30 hover:bg-muted/50 transition-colors">
                          <button
                            type="button"
                            onClick={() => toggleCategoryCollapse(group.category)}
                            className="flex items-center gap-1 flex-1 text-left"
                          >
                            {collapsed ? (
                              <ChevronRight className="size-3 text-muted-foreground" />
                            ) : (
                              <ChevronDown className="size-3 text-muted-foreground" />
                            )}
                            <span className="text-[11px] font-medium">{group.label}</span>
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
                        {/* 分类内的策略 checkbox */}
                        {!collapsed && (
                          <div className="flex flex-wrap gap-1.5 px-2 py-2">
                            {group.items.map((s) => {
                              const archived = isArchived(s.key)
                              const archReason = statusData?.[s.key]?.reason || ""
                              return (
                                <label
                                  key={s.key}
                                  className={cn(
                                    "flex items-center gap-1 cursor-pointer text-[11px] rounded px-1.5 py-0.5 transition-colors",
                                    archived
                                      ? "opacity-50 hover:opacity-80"
                                      : "hover:bg-muted/40"
                                  )}
                                  title={archived ? `已归档：${archReason}` : undefined}
                                >
                                  <input
                                    type="checkbox"
                                    checked={selectedStrategies.includes(s.key)}
                                    onChange={(e) => {
                                      setSelectedStrategies((prev) =>
                                        e.target.checked
                                          ? [...prev, s.key]
                                          : prev.filter((x) => x !== s.key)
                                      )
                                    }}
                                    className="size-3 rounded border-border"
                                  />
                                  {s.name}
                                  {archived && (
                                    <span className="text-[9px] text-amber-500/80 ml-0.5">
                                      归档
                                    </span>
                                  )}
                                </label>
                              )
                            })}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
                {selectedStrategies.length === 0 && (
                  <p className="text-[10px] text-muted-foreground mt-1">
                    未选择策略时默认运行 grid
                  </p>
                )}
              </div>
            )}
            <div className="col-span-2 flex items-center gap-2">
              <input
                type="checkbox"
                id={`fresh-${mode}`}
                checked={fresh}
                onChange={(e) => setFresh(e.target.checked)}
                className="size-3 rounded border-border"
              />
              <Label htmlFor={`fresh-${mode}`} className="text-[11px] cursor-pointer">
                忽略旧检查点，全新启动
              </Label>
            </div>
          </div>
        )}

        {/* 互斥提示 */}
        {tradingModeRunning && isIdle && (
          <p className="text-[11px] text-warning">
            另一个交易模式运行中，请先停止后再启动本模式
          </p>
        )}

        {/* 日志面板 */}
        <ModeLogViewer mode={mode} isOpen={showLogs} />
      </CardContent>
    </Card>
  )
}
