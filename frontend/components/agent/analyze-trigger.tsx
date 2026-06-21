"use client"

import { useState } from "react"
import {
  BarChart3,
  ClipboardCheck,
  Loader2,
  SlidersHorizontal,
  CalendarCheck,
  TrendingDown,
  Sparkles,
  type LucideIcon,
} from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { AgentAnalysisResult, AgentTask } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { AnalyzeResult } from "./analyze-result"

interface TaskConfig {
  task: AgentTask
  label: string
  description: string
  icon: LucideIcon
  color: string
}

const TASKS: TaskConfig[] = [
  {
    task: "backtest",
    label: "回测解读",
    description: "解释收益来源、回撤原因与潜在风险",
    icon: BarChart3,
    color: "text-blue-400",
  },
  {
    task: "trade_attribution",
    label: "交易归因",
    description: "对失败交易做归因分析，找出共性错误",
    icon: TrendingDown,
    color: "text-rose-400",
  },
  {
    task: "risk_checklist",
    label: "风险清单",
    description: "逐项检查风控、密钥、数据质量等合规项",
    icon: ClipboardCheck,
    color: "text-amber-400",
  },
  {
    task: "param_sensitivity",
    label: "参数敏感性",
    description: "总结参数扫描结果，指出稳健区间",
    icon: SlidersHorizontal,
    color: "text-purple-400",
  },
  {
    task: "weekly_review",
    label: "周报复盘",
    description: "生成本周策略表现综述与下周建议",
    icon: CalendarCheck,
    color: "text-emerald-400",
  },
]

export function AnalyzeTrigger() {
  const [runningTask, setRunningTask] = useState<AgentTask | null>(null)
  const [result, setResult] = useState<AgentAnalysisResult | null>(null)
  const [resultTask, setResultTask] = useState<AgentTask | null>(null)
  const [error, setError] = useState<string | null>(null)

  const run = async (task: AgentTask) => {
    setRunningTask(task)
    setError(null)
    setResult(null)
    const toastId = toast.loading(`正在生成 ${TASKS.find((t) => t.task === task)?.label} …`)
    try {
      const r = await api.runAgentAnalysis(task)
      setResult(r)
      setResultTask(task)
      toast.success("分析完成", { id: toastId })
    } catch (e) {
      const msg = e instanceof Error ? e.message : "未知错误"
      setError(msg)
      toast.error("分析失败", { id: toastId, description: msg })
    } finally {
      setRunningTask(null)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <Sparkles className="size-4 text-primary" />
            选择分析类型
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {TASKS.map((t) => {
              const Icon = t.icon
              const isRunning = runningTask === t.task
              return (
                <button
                  key={t.task}
                  type="button"
                  onClick={() => run(t.task)}
                  disabled={runningTask !== null}
                  className={cn(
                    "group flex flex-col gap-2 rounded-lg border border-border bg-card p-4 text-left transition-colors",
                    "hover:border-primary/40 hover:bg-accent/40",
                    "disabled:cursor-not-allowed disabled:opacity-60",
                  )}
                >
                  <div className="flex items-center justify-between">
                    <Icon className={cn("size-5", t.color)} />
                    {isRunning ? (
                      <Loader2 className="size-4 animate-spin text-primary" />
                    ) : null}
                  </div>
                  <div>
                    <p className="text-sm font-medium">{t.label}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">{t.description}</p>
                  </div>
                </button>
              )
            })}
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            所有分析仅作参考，不自动执行任何交易决策；输出标注"需人工确认"。
          </p>
        </CardContent>
      </Card>

      {error ? (
        <Card className="border-destructive/40 bg-destructive/5">
          <CardContent className="p-4 text-sm text-destructive">
            分析失败：{error}
          </CardContent>
        </Card>
      ) : null}

      {result ? (
        <AnalyzeResult result={result} task={resultTask} />
      ) : null}
    </div>
  )
}
