"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Copy, ArrowDown, Wifi, WifiOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { useModeLogs } from "@/hooks/use-mode-logs"
import type { RunningMode } from "@/lib/types"

interface ModeLogViewerProps {
  mode: RunningMode
  isOpen: boolean
}

export function ModeLogViewer({ mode, isOpen }: ModeLogViewerProps) {
  const { logs, isConnected, clearLogs } = useModeLogs(isOpen ? mode : null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [copied, setCopied] = useState(false)

  // 自动滚底
  useEffect(() => {
    if (!autoScroll || !containerRef.current) return
    containerRef.current.scrollTop = containerRef.current.scrollHeight
  }, [logs, autoScroll])

  // 检测用户滚动
  const handleScroll = useCallback(() => {
    if (!containerRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current
    const atBottom = scrollHeight - scrollTop - clientHeight < 40
    setAutoScroll(atBottom)
  }, [])

  const scrollToBottom = useCallback(() => {
    if (!containerRef.current) return
    containerRef.current.scrollTop = containerRef.current.scrollHeight
    setAutoScroll(true)
  }, [])

  const handleCopy = useCallback(async () => {
    const text = logs.join("\n")
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // ignore
    }
  }, [logs])

  if (!isOpen) return null

  return (
    <div className="rounded-md border border-border/60 bg-[#0d1117] overflow-hidden">
      {/* 工具栏 */}
      <div className="flex items-center justify-between border-b border-border/40 px-3 py-1.5">
        <div className="flex items-center gap-2">
          {isConnected ? (
            <Wifi className="size-3 text-emerald-400" />
          ) : (
            <WifiOff className="size-3 text-amber-400" />
          )}
          <span className="text-[11px] text-zinc-500">
            {isConnected ? "实时日志" : "已断开 (REST 回退)"}
          </span>
          <Badge variant="outline" className="text-[10px] h-4 px-1.5 text-zinc-500 border-zinc-700">
            {logs.length} 行
          </Badge>
        </div>
        <div className="flex items-center gap-1">
          {!autoScroll && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 text-[10px] text-zinc-400 hover:text-zinc-200 gap-1 px-2"
              onClick={scrollToBottom}
            >
              <ArrowDown className="size-3" />
              回到底部
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-[10px] text-zinc-400 hover:text-zinc-200 gap-1 px-2"
            onClick={handleCopy}
          >
            <Copy className="size-3" />
            {copied ? "已复制" : "复制"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-[10px] text-zinc-400 hover:text-zinc-200 px-2"
            onClick={clearLogs}
          >
            清空
          </Button>
        </div>
      </div>

      {/* 日志内容 */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="overflow-auto font-mono text-[11px] leading-relaxed p-3"
        style={{ maxHeight: "320px", minHeight: "160px" }}
      >
        {logs.length === 0 ? (
          <div className="text-zinc-600 italic">暂无日志输出…</div>
        ) : (
          logs.map((line, i) => (
            <div key={i} className="flex gap-3 hover:bg-white/[0.03]">
              <span className="text-zinc-600 select-none w-8 text-right shrink-0 tabular-nums">
                {i + 1}
              </span>
              <span className="text-zinc-300 whitespace-pre-wrap break-all">
                {line}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
