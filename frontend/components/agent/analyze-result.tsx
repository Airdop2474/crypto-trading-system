"use client"

import { AlertTriangle, CheckCircle2, Lightbulb, ShieldAlert } from "lucide-react"
import type { AgentAnalysisResult, AgentTask } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

const TASK_LABEL: Record<AgentTask, string> = {
  backtest: "回测解读",
  trade_attribution: "交易归因",
  risk_checklist: "风险清单",
  param_sensitivity: "参数敏感性",
  weekly_review: "周报复盘",
}

function confidenceColor(c: number): string {
  if (c >= 0.75) return "text-success"
  if (c >= 0.5) return "text-warning"
  return "text-destructive"
}

function confidenceLabel(c: number): string {
  if (c >= 0.75) return "高置信"
  if (c >= 0.5) return "中置信"
  return "低置信"
}

export function AnalyzeResult({
  result,
  task,
}: {
  result: AgentAnalysisResult
  task: AgentTask | null
}) {
  const confidence = typeof result.confidence === "number" ? result.confidence : 0
  const risks = Array.isArray(result.risks) ? result.risks : []

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Lightbulb className="size-4 text-primary" />
          分析结果
          {task ? (
            <Badge variant="secondary" className="text-xs">
              {TASK_LABEL[task]}
            </Badge>
          ) : null}
        </CardTitle>
        <div className="flex items-center gap-2">
          <Badge
            variant="outline"
            className={cn("text-xs tabular-nums", confidenceColor(confidence))}
          >
            {confidenceLabel(confidence)} · {(confidence * 100).toFixed(0)}%
          </Badge>
          {result.requires_human_approval ? (
            <Badge variant="outline" className="border-warning/40 text-warning text-xs">
              <ShieldAlert className="mr-1 size-3" />
              需人工确认
            </Badge>
          ) : (
            <Badge variant="outline" className="border-success/40 text-success text-xs">
              <CheckCircle2 className="mr-1 size-3" />
              无需确认
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <Section title="分析结论" body={result.analysis} />
        <Section title="推理过程" body={result.reasoning} muted />
        <Section title="建议" body={result.recommendation} />

        {risks.length > 0 ? (
          <div>
            <p className="mb-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
              风险提示
            </p>
            <ul className="space-y-1.5">
              {risks.map((r, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 rounded-md border border-warning/20 bg-warning/5 px-3 py-2 text-xs text-foreground/90"
                >
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warning" />
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}

function Section({
  title,
  body,
  muted,
}: {
  title: string
  body: string
  muted?: boolean
}) {
  if (!body) return null
  return (
    <div>
      <p className="mb-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
        {title}
      </p>
      <p
        className={cn(
          "whitespace-pre-wrap text-sm leading-relaxed",
          muted ? "text-muted-foreground" : "text-foreground/90",
        )}
      >
        {body}
      </p>
    </div>
  )
}
