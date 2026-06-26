"use client"

import { useState } from "react"
import { Loader2 } from "lucide-react"
import { toast } from "sonner"
import useSWR from "swr"
import { api } from "@/lib/api"
import type { StrategyType, ParamConstraint } from "@/lib/types"
import { getParamLabel } from "@/lib/param-labels"
import { STRATEGY_TYPE_LABEL } from "@/lib/strategy-meta"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

interface Props {
  children: React.ReactNode
}

const TIMEFRAMES = ["1h", "4h", "1d"]

export function CreateStrategyDialog({ children }: Props) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)

  const { data: registry } = useSWR(
    open ? "strategy-registry" : null,
    () => api.getStrategyRegistry(),
  )

  const { data: tickers } = useSWR(
    open ? "tickers" : null,
    () => api.getTickers(),
  )

  const strategies = registry?.strategies ?? []
  const symbols = tickers ? [...new Set(tickers.map((t) => t.symbol))].sort() : []

  const [selectedType, setSelectedType] = useState<StrategyType | "">("")
  const [symbol, setSymbol] = useState<string>("")
  const [timeframe, setTimeframe] = useState("4h")
  const [investment, setInvestment] = useState("10000")
  const [params, setParams] = useState<Record<string, string>>({})

  const activeEntry = strategies.find((s) => s.key === selectedType)

  const userParams: [string, ParamConstraint][] = activeEntry
    ? Object.entries(activeEntry.param_schema)
    : []

  function handleTypeChange(type: string) {
    setSelectedType(type as StrategyType)
    const entry = strategies.find((s) => s.key === type)
    if (entry) {
      const defaults: Record<string, string> = {}
      Object.entries(entry.param_schema).forEach(([key, constraint]) => {
        if (entry.defaults[key] != null) {
          defaults[key] = String(entry.defaults[key])
        } else if (constraint.min != null) {
          defaults[key] = String(constraint.min)
        } else {
          defaults[key] = ""
        }
      })
      setParams(defaults)
    }
  }

  function updateParam(key: string, value: string) {
    setParams((prev) => ({ ...prev, [key]: value }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!selectedType) {
      toast.error("请选择策略类型")
      return
    }
    if (!symbol) {
      toast.error("请选择交易对")
      return
    }

    const investNum = parseFloat(investment)
    if (isNaN(investNum) || investNum <= 0) {
      toast.error("投入本金必须为正数")
      return
    }

    const parsedParams: Record<string, number | boolean> = {}
    for (const [key, constraint] of userParams) {
      const raw = params[key]
      if (raw == null || raw === "") {
        toast.error(`请填写参数: ${getParamLabel(key)}`)
        return
      }
      if (constraint.type === "bool") {
        parsedParams[key] = raw === "true" || raw === "1"
      } else {
        const num = Number(raw)
        if (isNaN(num)) {
          toast.error(`参数 ${getParamLabel(key)} 必须为数字`)
          return
        }
        if (constraint.min != null && num < constraint.min) {
          toast.error(`参数 ${getParamLabel(key)} 不能小于 ${constraint.min}`)
          return
        }
        if (constraint.max != null && num > constraint.max) {
          toast.error(`参数 ${getParamLabel(key)} 不能大于 ${constraint.max}`)
          return
        }
        parsedParams[key] = constraint.type === "int" ? Math.round(num) : num
      }
    }

    setLoading(true)
    try {
      const result = await api.createStrategy({
        type: selectedType,
        symbol,
        investment: investNum,
        timeframe,
        params: parsedParams,
      })
      toast.success(`策略 "${result.name}" 已创建`, {
        description: `${symbol} | ${investNum.toLocaleString()} USDT | ${timeframe}`,
      })
      setOpen(false)
      setSelectedType("")
      setSymbol("")
      setTimeframe("4h")
      setInvestment("10000")
      setParams({})
    } catch (err) {
      const msg = err instanceof Error ? err.message : "未知错误"
      toast.error(`创建失败: ${msg}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={children as React.ReactElement} />
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>创建策略</DialogTitle>
          <DialogDescription>
            选择策略类型、交易对和参数来创建新的策略实例。
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label>策略类型</Label>
            <Select
              value={selectedType || undefined}
              onValueChange={(v) => v && handleTypeChange(v)}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="请选择策略类型">
                  {selectedType ? (STRATEGY_TYPE_LABEL[selectedType as StrategyType] || selectedType) : undefined}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {strategies.map((s) => (
                  <SelectItem key={s.key} value={s.key}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-2">
            <Label>交易对</Label>
            <Select
              value={symbol}
              onValueChange={(v) => v && setSymbol(v)}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder={symbols.length === 0 ? "加载中..." : "请选择交易对"} />
              </SelectTrigger>
              <SelectContent>
                {symbols.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-2">
              <Label>时间周期</Label>
              <Select value={timeframe} onValueChange={(v) => v && setTimeframe(v)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIMEFRAMES.map((tf) => (
                    <SelectItem key={tf} value={tf}>
                      {tf}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="create-investment">投入本金 (USDT)</Label>
              <Input
                id="create-investment"
                type="number"
                placeholder="10000"
                min={1}
                required
                value={investment}
                onChange={(e) => setInvestment(e.target.value)}
              />
            </div>
          </div>

          {userParams.length > 0 && (
            <div className="flex flex-col gap-3 rounded-lg border border-border/50 bg-muted/30 p-3 max-h-[45vh] overflow-y-auto">
              <span className="text-xs font-medium text-muted-foreground">
                策略参数
              </span>
              {userParams.map(([key, constraint]) => (
                <div key={key} className="flex flex-col gap-1.5">
                  <Label htmlFor={`param-${key}`} className="text-xs">
                    {getParamLabel(key)}
                  </Label>
                  <Input
                    id={`param-${key}`}
                    type={constraint.type === "bool" ? "text" : "number"}
                    placeholder={
                      constraint.type === "bool"
                        ? "true / false"
                        : constraint.min != null && constraint.max != null
                          ? `${constraint.min} ~ ${constraint.max}`
                          : undefined
                    }
                    min={constraint.min}
                    max={constraint.max}
                    step={constraint.type === "int" ? 1 : 0.01}
                    value={params[key] ?? ""}
                    onChange={(e) => updateParam(key, e.target.value)}
                  />
                  {(constraint.min != null || constraint.max != null) && (
                    <span className="text-[10px] text-muted-foreground">
                      {constraint.min != null && `最小: ${constraint.min}`}
                      {constraint.min != null && constraint.max != null && " | "}
                      {constraint.max != null && `最大: ${constraint.max}`}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}

          {activeEntry && (
            <div className="rounded-md bg-secondary/40 px-3 py-2 text-xs text-muted-foreground">
              {activeEntry.description}
            </div>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setOpen(false)}
              disabled={loading}
            >
              取消
            </Button>
            <Button type="submit" disabled={loading || !selectedType || !symbol}>
              {loading && <Loader2 className="mr-1.5 size-4 animate-spin" />}
              {loading ? "创建中..." : "创建策略"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}