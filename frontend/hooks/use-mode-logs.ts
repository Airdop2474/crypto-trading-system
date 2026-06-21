"use client"

/**
 * WebSocket 实时日志 Hook
 *
 * 连接后端 /ws/logs/{mode} WebSocket 端点，接收子进程的实时日志输出。
 * 自动重连（指数退避），断线时回退到 REST 轮询。
 *
 * 用法：
 *   const { logs, isConnected, clearLogs } = useModeLogs("live_paper")
 */

import { useCallback, useEffect, useRef, useState } from "react"
import type { RunningMode } from "@/lib/types"
import { api } from "@/lib/api"

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"

const API_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN || ""

const MAX_LOGS = 500

/** 将 http:// 转为 ws://，https:// 转为 wss:// */
function toWsUrl(base: string, mode: string): string {
  let wsBase = base.replace(/^http/, "ws")
  if (process.env.NODE_ENV === "production" && wsBase.startsWith("ws://")) {
    wsBase = "wss://" + wsBase.slice("ws://".length)
  }
  return `${wsBase}/ws/logs/${mode}`
}

/** 重连延迟：1s → 2s → 4s → 8s → 16s → 30s（上限） */
function reconnectDelay(attempt: number): number {
  return Math.min(1000 * 2 ** attempt, 30_000)
}

export interface UseModeLogsResult {
  /** 日志行数组 */
  logs: string[]
  /** WebSocket 是否已连接 */
  isConnected: boolean
  /** 是否使用 REST 回退模式 */
  isFallback: boolean
  /** 清空日志 */
  clearLogs: () => void
}

export function useModeLogs(mode: RunningMode | null): UseModeLogsResult {
  const [logs, setLogs] = useState<string[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [isFallback, setIsFallback] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const attemptRef = useRef(0)
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const unmountedRef = useRef(false)
  const fallbackTimerRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined)

  // mode 变化时清空日志
  useEffect(() => {
    setLogs([])
  }, [mode])

  const appendLog = useCallback((line: string) => {
    setLogs((prev) => {
      const next = [...prev, line]
      if (next.length > MAX_LOGS) return next.slice(-MAX_LOGS)
      return next
    })
  }, [])

  // REST 回退轮询
  const fallbackPoll = useCallback(async () => {
    if (!mode) return
    try {
      const data = await api.getModeLogs(mode, 200)
      setLogs(data)
    } catch {
      // 静默失败
    }
  }, [mode])

  // WebSocket 连接逻辑
  const connect = useCallback(() => {
    if (unmountedRef.current || !mode) return

    // 关闭旧连接
    if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
      try {
        wsRef.current.onclose = null
        wsRef.current.close()
      } catch {
        // ignore
      }
      wsRef.current = null
    }

    const url = toWsUrl(API_BASE, mode)
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setIsConnected(true)
      setIsFallback(false)
      attemptRef.current = 0
      // 首条消息认证
      ws.send(JSON.stringify({ type: "auth", token: API_TOKEN }))
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === "ping") return
        if (data.type === "log" && typeof data.line === "string") {
          appendLog(data.line)
        }
        if (data.error) {
          console.error("[ws-logs]", data.error)
        }
      } catch {
        // 解析失败忽略
      }
    }

    ws.onclose = () => {
      setIsConnected(false)
      setIsFallback(true)
      wsRef.current = null

      if (unmountedRef.current) return

      const delay = reconnectDelay(attemptRef.current++)
      timerRef.current = setTimeout(connect, delay)
      fallbackPoll()
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [mode, appendLog, fallbackPoll])

  useEffect(() => {
    if (!mode) {
      setLogs([])
      setIsConnected(false)
      setIsFallback(false)
      return
    }

    unmountedRef.current = false
    connect()

    // REST 回退定时器（WS 断线时每 5s 轮询一次）
    fallbackTimerRef.current = setInterval(() => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        fallbackPoll()
      }
    }, 5_000)

    return () => {
      unmountedRef.current = true
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      if (timerRef.current) {
        clearTimeout(timerRef.current)
      }
      if (fallbackTimerRef.current) {
        clearInterval(fallbackTimerRef.current)
      }
    }
  }, [mode, connect, fallbackPoll])

  const clearLogs = useCallback(() => setLogs([]), [])

  return { logs, isConnected, isFallback, clearLogs }
}
