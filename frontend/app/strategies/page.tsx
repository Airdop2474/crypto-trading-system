"use client"

import { useState } from "react"
import useSWR from "swr"
import { api } from "@/lib/api"
import type { StrategyRegistryEntry } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { ApiError } from "@/components/api-error"
import { ErrorBoundary } from "@/components/error-boundary"
import { StrategyCard } from "@/components/strategies/strategy-card"
import { CreateStrategyDialog } from "@/components/strategies/create-strategy-dialog"
import { StrategyParamsDialog } from "@/components/strategies/strategy-params-dialog"
import { RunHistory } from "@/components/strategies/run-history"
import { Plus } from "lucide-react"

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

  // 参数配置对话框状态
  const [configTarget, setConfigTarget] = useState<{
    entry: StrategyRegistryEntry
    strategyId: string
  } | null>(null)

  const strategies = data?.strategies ?? []

  function handleConfigure(entry: StrategyRegistryEntry) {
    // 使用 entry.key 作为 strategyId（后端通过 type 查找实例）
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
              onConfigure={() => handleConfigure(entry)}
            />
          ))}
        </div>
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
          open={!!configTarget}
          onOpenChange={(open) => {
            if (!open) {
              setConfigTarget(null)
              mutate() // 刷新注册表
            }
          }}
        />
      )}
    </div>
  )
}
