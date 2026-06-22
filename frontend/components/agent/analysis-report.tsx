"use client"

import { useState } from "react"
import { toast } from "sonner"
import { Loader2, Brain, Lightbulb, AlertTriangle, FileText } from "lucide-react"
import { api } from "@/lib/api"
import type { AgentAnalysisResult, AgentTask } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

const TASK_OPTIONS: { value: AgentTask; label: string }[] = [
  { value: "backtest", label: "回测分析" },
  { value: "trade_attribution", label: "交易归因" },
  { value: "risk_checklist", label: "风险清单" },
  { value: "param_sensitivity", label: "参数敏感性" },
  { value: "weekly_review", label: "周报" },
]

export function AnalysisReport() {
  const [task, setTask] = useState<AgentTask>("backtest")
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<AgentAnalysisResult | null>(null)

  const handleRun = async () => {
    setLoading(true)
    setResult(null)
    const toastId = toast.loading(
      `正在运行${TASK_OPTIONS.find((t) => t.value === task)?.label}…`,
    )
    try {
      const r = await api.runAgentAnalysis(task)
      setResult(r)
      toast.success("分析完成", { id: toastId })
    } catch (e) {
      const msg = e instanceof Error ? e.message : "未知错误"
      toast.error("分析失败", { id: toastId, description: msg })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <Brain className="size-4 text-primary" />
            AI 分析报告
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-3">
            <Select
              value={task}
              onValueChange={(v) => v && setTask(v as AgentTask)}
              disabled={loading}
            >
              <SelectTrigger className="w-40">
                <SelectValue placeholder="选择分析类型" />
              </SelectTrigger>
              <SelectContent>
                {TASK_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Button onClick={handleRun} disabled={loading}>
              {loading ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  运行中…
                </>
              ) : (
                "运行分析"
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {result ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">分析结果</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            {/* 分析结论 */}
            <section>
              <h4 className="mb-1.5 flex items-center gap-1.5 text-sm font-medium">
                <FileText className="size-3.5 text-blue-400" />
                分析结论
              </h4>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                {result.analysis}
              </p>
            </section>

            {/* 推理过程 */}
            <section>
              <h4 className="mb-1.5 flex items-center gap-1.5 text-sm font-medium">
                <Brain className="size-3.5 text-purple-400" />
                推理过程
              </h4>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                {result.reasoning}
              </p>
            </section>

            {/* 建议 */}
            <section>
              <h4 className="mb-1.5 flex items-center gap-1.5 text-sm font-medium">
                <Lightbulb className="size-3.5 text-amber-400" />
                建议
              </h4>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                {result.recommendation}
              </p>
            </section>

            {/* 风险 */}
            {result.risks && result.risks.length > 0 ? (
              <section>
                <h4 className="mb-1.5 flex items-center gap-1.5 text-sm font-medium">
                  <AlertTriangle className="size-3.5 text-rose-400" />
                  风险
                </h4>
                <ul className="list-inside list-disc space-y-1 text-sm leading-relaxed text-muted-foreground">
                  {result.risks.map((risk, i) => (
                    <li key={i}>{risk}</li>
                  ))}
                </ul>
              </section>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
