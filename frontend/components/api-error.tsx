"use client"

import { AlertCircle, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"

interface ApiErrorProps {
  /** 错误对象（来自 useSWR 的 error）。为空时不渲染。 */
  error?: unknown
  /** 重试回调，通常传 SWR 的 mutate()。 */
  onRetry?: () => void
  /** 自定义错误提示；默认从 error.message 提取。 */
  message?: string
  /** 占位高度，默认 200px。 */
  minHeight?: number
  /** 可选标题，默认"数据加载失败"。 */
  title?: string
}

/**
 * API 错误状态组件：统一渲染加载失败提示 + 重试按钮。
 *
 * 用于补齐各页面 SWR `error` 状态的 UI（F-02）。
 * 当 error 为空（正常 / loading）时返回 null，调用方无需额外条件判断。
 */
export function ApiError({
  error,
  onRetry,
  message,
  minHeight = 200,
  title = "数据加载失败",
}: ApiErrorProps) {
  if (!error) return null

  const detail =
    message ??
    (error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : "请检查后端服务是否正常运行，或稍后重试。")

  return (
    <div
      className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-destructive/40 bg-destructive/5 p-6 text-center"
      style={{ minHeight }}
    >
      <div className="rounded-full bg-destructive/10 p-2.5">
        <AlertCircle className="h-6 w-6 text-destructive" />
      </div>
      <div className="space-y-1">
        <p className="text-sm font-medium text-foreground">{title}</p>
        <p className="mx-auto max-w-md text-xs text-muted-foreground">{detail}</p>
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw className="h-3.5 w-3.5" />
          重试
        </Button>
      )}
    </div>
  )
}
