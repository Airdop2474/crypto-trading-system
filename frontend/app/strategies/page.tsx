"use client"

import { useState } from "react"
import useSWR, { mutate as globalMutate } from "swr"
import Link from "next/link"
import { api } from "@/lib/api"
import type { StrategyRegistryEntry, MultiStrategyDetail } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError } from "@/components/api-error"
import { ErrorBoundary } from "@/components/error-boundary"
import { StrategyCard } from "@/components/strategies/strategy-card"
import { CreateStrategyDialog } from "@/components/strategies/create-strategy-dialog"
import { StrategyParamsDialog } from "@/components/strategies/strategy-params-dialog"
import { RunHistory } from "@/components/strategies/run-history"
import { StrategyStatusBadge } from "@/components/status-badge"
import { fmtSigned, pnlColor, fmtNum } from "@/lib/format"
import { parseStrategyType, STRATEGY_TYPE_ICON, STRATEGY_FALLBACK_ICON, STRATEGY_TYPE_LABEL, getParamLabel } from "@/lib/strategy-meta"
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "@/components/ui/tooltip"
import { Plus, ArrowUpRight, Trash2, Pencil, Check, X } from "lucide-react"
import { toast } from "sonner"

export default function StrategiesPage() {
  return (
    <ErrorBoundary>
      <StrategiesContent />
    </ErrorBoundary>
  )
}

function StrategiesContent() {
  const { data, error, isLoading, mutate } = useSWR(
    "strategy-registry",
    () => api.getStrategyRegistry(),
    { revalidateOnFocus: false },
  )

  const { data: instances } = useSWR("multi-details", () => api.getMultiDetails())

  // 持久化策略参数配置
  const { data: configs } = useSWR("strategy-configs", () => api.getStrategyConfigs(), {
    revalidateOnFocus: false,
    dedupingInterval: 30_000,
  })

  // 参数配置对话框状态
  const [configTarget, setConfigTarget] = useState<{
    entry: StrategyRegistryEntry
    strategyId: string
  } | null>(null)

  const strategies = data?.strategies ?? []
  const runningInstances = (instances ?? []).filter((d) => d.totalTrades > 0 || d.realizedPnl !== 0)

  function handleConfigure(entry: StrategyRegistryEntry) {
    setConfigTarget({ entry, strategyId: entry.key })
  }

  return (
    <div className="flex flex-col gap-4 pb-16 md:pb-0">
      {/* 页头 */}
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div className="flex flex-col gap-1">
            <CardTitle className="text-sm font-medium">全部策略</CardTitle>
            <p className="text-xs text-muted-foreground">
              查看所有可用策略类型，创建新实例或调整运行参数。
            </p>
          </div>
          <CreateStrategyDialog>
            <Button size="sm" className="gap-1.5">
              <Plus className="size-4" />
              创建策略
            </Button>
          </CreateStrategyDialog>
        </CardHeader>
      </Card>

      {/* 正在运行的实例 */}
      {runningInstances.length > 0 && (
        <Card>
          <CardHeader className="flex-row items-center justify-between pb-3">
            <CardTitle className="text-sm font-medium">正在运行的策略实例</CardTitle>
            <Link
              href="/"
              className="flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground"
            >
              总览 <ArrowUpRight className="size-3" />
            </Link>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {runningInstances.map((inst) => {
              const type = parseStrategyType(inst.strategyId)
              const Icon = type ? STRATEGY_TYPE_ICON[type] : STRATEGY_FALLBACK_ICON
              return (
                <Link
                  key={inst.strategyId}
                  href={`/strategy/${inst.strategyId}`}
                  className="flex items-center justify-between rounded-md border border-border/60 bg-secondary/30 px-3 py-2.5 hover:bg-secondary/60 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex size-8 items-center justify-center rounded-md bg-secondary text-muted-foreground">
                      <Icon className="size-4" />
                    </div>
                    <div>
                      <p className="text-sm font-medium">{inst.strategyId}</p>
                      <p className="text-xs text-muted-foreground">{inst.symbol}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 text-right">
                    <div>
                      <p className={`font-mono text-sm tabular-nums ${pnlColor(inst.realizedPnl)}`}>
                        {fmtSigned(inst.realizedPnl)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {inst.totalTrades} 笔 / {fmtNum(inst.winRate * 100, 0)}% 胜率
                      </p>
                    </div>
                    <StrategyStatusBadge status="running" />
                  </div>
                </Link>
              )
            })}
          </CardContent>
        </Card>
      )}

      {/* 错误状态 */}
      {error && (
        <ApiError
          error={error}
          onRetry={() => mutate()}
          title="策略注册表加载失败"
          minHeight={200}
        />
      )}

      {/* 加载中 */}
      {isLoading && !data && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i}>
              <CardHeader className="pb-3">
                <div className="h-4 w-32 animate-pulse rounded bg-muted" />
              </CardHeader>
              <CardContent>
                <div className="h-20 animate-pulse rounded bg-muted" />
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* 策略卡片网格 */}
      {!isLoading && strategies.length === 0 && !error && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center gap-3 py-12 text-center">
            <p className="text-sm text-muted-foreground">暂无可用策略</p>
            <CreateStrategyDialog>
              <Button variant="outline" size="sm" className="gap-1.5">
                <Plus className="size-4" />
                创建第一个策略
              </Button>
            </CreateStrategyDialog>
          </CardContent>
        </Card>
      )}

      {strategies.length > 0 && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {strategies.map((entry) => (
            <StrategyCard
              key={entry.key}
              entry={entry}
              instance={instances?.find((d) => d.strategyId === entry.key)}
              onConfigure={() => handleConfigure(entry)}
            />
          ))}
        </div>
      )}

      {/* 持久化参数配置一览 */}
      {configs && Object.keys(configs).length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">已保存的策略参数</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            <TooltipProvider>
              {Object.entries(configs).map(([key, params]) => (
                <SavedConfigCard key={key} configKey={key} params={params} />
              ))}
            </TooltipProvider>
          </CardContent>
        </Card>
      )}

      {/* 运行历史 */}
      <Card>
        <CardContent className="p-4">
          <RunHistory />
        </CardContent>
      </Card>

      {/* 参数配置对话框 */}
      {configTarget && (
        <StrategyParamsDialog
          strategyId={configTarget.strategyId}
          strategyName={configTarget.entry.name}
          paramSchema={configTarget.entry.param_schema}
          currentParams={configTarget.entry.defaults}
          defaultParams={configTarget.entry.defaults}
          open={!!configTarget}
          onOpenChange={(open) => {
            if (!open) {
              setConfigTarget(null)
              mutate()
            }
          }}
        />
      )}
    </div>
  )
}

/** 已保存策略配置卡片：hover 显示参数，支持删除和重命名 */
function SavedConfigCard({
  configKey,
  params,
}: {
  configKey: string
  params: Record<string, number | boolean>
}) {
  const [renaming, setRenaming] = useState(false)
  const [newName, setNewName] = useState(configKey)
  const [deleting, setDeleting] = useState(false)

  const displayName = (() => {
    const t = parseStrategyType(configKey)
    return t ? STRATEGY_TYPE_LABEL[t] : configKey
  })()

  const paramCount = Object.keys(params).length

  async function handleDelete() {
    setDeleting(true)
    try {
      await api.deleteStrategyConfig(configKey)
      toast.success(`已删除 "${displayName}" 的配置`)
      globalMutate("strategy-configs")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败")
    } finally {
      setDeleting(false)
    }
  }

  async function handleRename() {
    const trimmed = newName.trim()
    if (!trimmed || trimmed === configKey) {
      setRenaming(false)
      return
    }
    try {
      await api.renameStrategyConfig(configKey, trimmed)
      toast.success(`已重命名为 "${trimmed}"`)
      globalMutate("strategy-configs")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "重命名失败")
    } finally {
      setRenaming(false)
    }
  }

  return (
    <div className="group relative rounded-md border border-border/60 bg-muted/20 p-3">
      <div className="flex items-center justify-between gap-2">
        {renaming ? (
          <div className="flex items-center gap-1 flex-1">
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleRename()
                if (e.key === "Escape") setRenaming(false)
              }}
              className="h-6 text-xs"
              autoFocus
            />
            <Button size="icon" variant="ghost" className="size-6" onClick={handleRename}>
              <Check className="size-3" />
            </Button>
            <Button size="icon" variant="ghost" className="size-6" onClick={() => setRenaming(false)}>
              <X className="size-3" />
            </Button>
          </div>
        ) : (
          <Tooltip>
            <TooltipTrigger
              render={
                <p className="text-xs font-medium text-foreground cursor-help truncate">
                  {displayName}
                  <span className="ml-1.5 text-[10px] text-muted-foreground">({paramCount} 个参数)</span>
                </p>
              }
            />
            <TooltipContent side="bottom" className="max-w-sm">
              <div className="space-y-0.5 text-left">
                {Object.entries(params).map(([k, v]) => (
                  <p key={k} className="text-[11px]">
                    {getParamLabel(k)}: <span className="font-mono">{v === true ? "是" : v === false ? "否" : String(v)}</span>
                  </p>
                ))}
              </div>
            </TooltipContent>
          </Tooltip>
        )}

        {!renaming && (
          <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
            <Button
              size="icon"
              variant="ghost"
              className="size-6"
              onClick={() => { setNewName(configKey); setRenaming(true) }}
              title="重命名"
            >
              <Pencil className="size-3" />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              className="size-6 hover:text-destructive"
              onClick={handleDelete}
              disabled={deleting}
              title="删除"
            >
              <Trash2 className="size-3" />
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
