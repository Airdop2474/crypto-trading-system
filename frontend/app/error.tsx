"use client"

/**
 * 路由级错误边界（Next.js App Router 约定文件）。
 *
 * 当任意路由段抛出未捕获异常时，Next.js 会渲染此组件替代页面内容，
 * 并传入 `error`（错误对象）与 `reset`（重置边界、重新渲染路由）回调。
 *
 * 与组件级 `ErrorBoundary`（components/error-boundary.tsx）互补：
 * - 组件级负责 widget 级故障隔离（Overview 已用）
 * - 本文件负责整页兜底，避免白屏。
 *
 * 参考：https://nextjs.org/docs/app/api-reference/file-conventions/error
 */

import { useEffect } from "react"
import { AlertTriangle, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"

export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  // 路由错误通常意味着组件抛出异常，记录到控制台便于调试。
  useEffect(() => {
    console.error("[RouteError]", error.message, error.digest)
  }, [error])

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] p-8 text-center">
      <div className="rounded-full bg-amber-500/10 p-4 mb-4">
        <AlertTriangle className="h-10 w-10 text-amber-400" />
      </div>
      <h2 className="text-xl font-semibold text-foreground mb-2">
        页面加载失败
      </h2>
      <p className="text-sm text-muted-foreground mb-6 max-w-md">
        {error.message || "发生未知错误，请重试或刷新页面。"}
      </p>
      <div className="flex items-center gap-2">
        <Button variant="default" onClick={() => reset()}>
          <RefreshCw className="h-4 w-4" />
          重试
        </Button>
        <Button variant="outline" onClick={() => window.location.reload()}>
          刷新页面
        </Button>
      </div>
    </div>
  )
}
