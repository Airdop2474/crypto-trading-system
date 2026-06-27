"use client"

import { useState, useEffect } from "react"
import { Loader2 } from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { ParamConstraint } from "@/lib/types"
import { getParamLabel } from "@/lib/param-labels"
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
} from "@/components/ui/dialog"

interface Props {
  strategyId: string
  strategyName: string
  paramSchema: Record<string, ParamConstraint>
  currentParams: Record<string, number | boolean | string>
  defaultParams?: Record<string, number | boolean | string | null>
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function StrategyParamsDialog({
  strategyId,
  strategyName,
  paramSchema,
  currentParams,
  defaultParams,
  open,
  onOpenChange,
}: Props) {
  const [loading, setLoading] = useState(false)
  const [params, setParams] = useState<Record<string, string>>({})

  useEffect(() => {
    if (open) {
      const init: Record<string, string> = {}
      for (const key of Object.keys(paramSchema)) {
        init[key] = currentParams[key] != null ? String(currentParams[key]) : ""
      }
      setParams(init)
    }
  }, [open, paramSchema, currentParams])

  function updateParam(key: string, value: string) {
    setParams((prev) => ({ ...prev, [key]: value }))
  }

  function resetParam(key: string) {
    const dflt = defaultParams?.[key] ?? currentParams[key]
    setParams((prev) => ({ ...prev, [key]: dflt != null ? String(dflt) : "" }))
  }

  function resetAll() {
    const reset: Record<string, string> = {}
    for (const key of Object.keys(paramSchema)) {
      const dflt = defaultParams?.[key] ?? currentParams[key]
      reset[key] = dflt != null ? String(dflt) : ""
    }
    setParams(reset)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)

    const parsed: Record<string, number | boolean | string> = {}
    for (const [key, constraint] of Object.entries(paramSchema)) {
      const raw = params[key]
      if (raw == null || raw === "") continue

      if (constraint.type === "bool") {
        parsed[key] = raw === "true" || raw === "1"
      } else if (constraint.type === "str" || constraint.type === "list") {
        parsed[key] = raw
      } else {
        const num = Number(raw)
        if (isNaN(num)) {
          toast.error(`参数 ${getParamLabel(key)} 必须为数字`)
          setLoading(false)
          return
        }
        if (constraint.min != null && num < constraint.min) {
          toast.error(`参数 ${getParamLabel(key)} 不能小于 ${constraint.min}`)
          setLoading(false)
          return
        }
        if (constraint.max != null && num > constraint.max) {
          toast.error(`参数 ${getParamLabel(key)} 不能大于 ${constraint.max}`)
          setLoading(false)
          return
        }
        parsed[key] = constraint.type === "int" ? Math.round(num) : num
      }
    }

    if (Object.keys(parsed).length === 0) {
      toast.error("未修改任何参数")
      setLoading(false)
      return
    }

    try {
      await api.updateStrategyParams(strategyId, parsed)
      toast.success(`策略 "${strategyName}" 参数已更新`)
      onOpenChange(false)
    } catch (err) {
      const msg = err instanceof Error ? err.message : "未知错误"
      toast.error(`更新失败: ${msg}`)
    } finally {
      setLoading(false)
    }
  }

  const paramEntries = Object.entries(paramSchema)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md flex flex-col max-h-[80vh]">
        <DialogHeader className="flex-shrink-0">
          <DialogTitle>配置策略参数</DialogTitle>
          <DialogDescription>
            修改 {strategyName} 的运行参数。仅调整需要变更的值，留空则保持原值。
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4 flex-1 overflow-hidden">
          {paramEntries.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              该策略无可调参数
            </p>
          ) : (
            <div className="flex flex-col gap-3 rounded-lg border border-border/50 bg-muted/30 p-3 overflow-y-auto flex-1">
              {paramEntries.map(([key, constraint]) => {
                const isDefault = params[key] != null && defaultParams?.[key] != null && params[key] === String(defaultParams[key])
                return (
                  <div key={key} className="flex flex-col gap-1.5">
                    <div className="flex items-center justify-between">
                      <Label htmlFor={`sp-${key}`} className="text-xs">
                        {getParamLabel(key)}
                        {currentParams[key] != null && (
                          <span className="ml-2 text-muted-foreground font-mono">
                            (当前: {String(currentParams[key])})
                          </span>
                        )}
                      </Label>
                      {!isDefault && defaultParams?.[key] != null && (
                        <button
                          type="button"
                          className="text-[10px] text-muted-foreground hover:text-foreground underline"
                          onClick={() => resetParam(key)}
                        >
                          重置默认 {String(defaultParams[key])}
                        </button>
                      )}
                    </div>
                    <Input
                      id={`sp-${key}`}
                      type={(constraint.type === "int" || constraint.type === "float") ? "number" : "text"}
                      placeholder={
                        constraint.type === "bool"
                          ? "true / false"
                          : constraint.type === "list"
                            ? "逗号分隔，如 1,2,3,4"
                            : constraint.type === "str"
                              ? "请输入文本"
                              : constraint.min != null && constraint.max != null
                                ? `${constraint.min} ~ ${constraint.max}`
                                : undefined
                      }
                      min={(constraint.type === "int" || constraint.type === "float") ? constraint.min : undefined}
                      max={(constraint.type === "int" || constraint.type === "float") ? constraint.max : undefined}
                      step={constraint.type === "int" ? 1 : 0.01}
                      value={params[key] ?? ""}
                      onChange={(e) => updateParam(key, e.target.value)}
                    />
                    {(constraint.type === "int" || constraint.type === "float") && (constraint.min != null || constraint.max != null) && (
                      <span className="text-[10px] text-muted-foreground">
                        {constraint.min != null && `最小: ${constraint.min}`}
                        {constraint.min != null && constraint.max != null && " | "}
                        {constraint.max != null && `最大: ${constraint.max}`}
                      </span>
                    )}
                  </div>
                )
              })}
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-1 h-7 text-xs"
                onClick={resetAll}
              >
                重置全部为默认值
              </Button>
            </div>
          )}

          <DialogFooter className="flex-shrink-0">
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              disabled={loading}
            >
              取消
            </Button>
            <Button type="submit" disabled={loading || paramEntries.length === 0}>
              {loading && <Loader2 className="mr-1.5 size-4 animate-spin" />}
              {loading ? "保存中..." : "保存参数"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
