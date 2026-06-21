"use client"

/**
 * WebSocket 实时 Ticker Hook
 *
 * 连接后端 /ws/tickers WebSocket 端点，接收实时行情更新。
 * 自动重连（指数退避），断线时回退到 REST 轮询。
 *
 * 用法：
 *   const { tickers, isConnected } = useTickersWs()
 */

import { useCallback, useEffect, useRef, useState } from "react"
import type { Ticker } from "@/lib/types"
import { api } from "@/lib/api"

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"

const API_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN || ""

/** 将 http:// 转为 ws://，https:// 转为 wss://。生产环境强制 wss://（F-07）。 */
function toWsUrl(base: string): string {
  let wsBase = base.replace(/^http/, "ws")
  // F-07: 生产环境强制 wss://，防止 API_BASE 误配为 http 时 WS 明文传输。
  if (process.env.NODE_ENV === "production" && wsBase.startsWith("ws://")) {
    wsBase = "wss://" + wsBase.slice("ws://".length)
  }
  return wsBase + "/ws/tickers"
}

/** 重连延迟：1s → 2s → 4s → 8s → 16s → 30s（上限） */
function reconnectDelay(attempt: number): number {
  return Math.min(1000 * 2 ** attempt, 30_000)
}

export interface UseTickersWsResult {
  /** 最新 ticker 数据 */
  tickers: Ticker[]
  /** WebSocket 是否已连接 */
  isConnected: boolean
  /** 是否使用 REST 回退模式 */
  isFallback: boolean
  /** 重连尝试次数 */
  reconnectAttempts: number
}

export function useTickersWs(): UseTickersWsResult {
  const [tickers, setTickers] = useState<Ticker[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [isFallback, setIsFallback] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const attemptRef = useRef(0)
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const unmountedRef = useRef(false)

  // REST 回退轮询
  const fallbackPoll = useCallback(async () => {
    try {
      const data = await api.getTickers()
      setTickers(data)
    } catch {
      // 静默失败
    }
  }, [])

  // WebSocket 连接逻辑
  const connect = useCallback(() => {
    if (unmountedRef.current) return

    // F-05: 修复连接状态竞态 —— 若旧连接仍处于 CONNECTING/OPEN/CLOSING，
    // 先关闭再创建新连接，避免旧连接引用被覆盖后泄漏（其 onclose 仍会触发并叠加重连）。
    if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
      try {
        wsRef.current.onclose = null
        wsRef.current.close()
      } catch {
        // 关闭失败忽略，下方会覆盖引用
      }
      wsRef.current = null
    }

    const url = toWsUrl(API_BASE)
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setIsConnected(true)
      setIsFallback(false)
      attemptRef.current = 0
      // R-05: WebSocket first-message authentication
      ws.send(JSON.stringify({ type: "auth", token: API_TOKEN }))
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        // 忽略心跳 ping
        if (data.type === "ping") return
        // 数据是 Ticker 数组
        if (Array.isArray(data)) {
          setTickers(data)
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
      // onerror 后会自动触发 onclose
      ws.close()
    }
  }, [fallbackPoll])

  useEffect(() => {
    unmountedRef.current = false
    connect()

    // REST 回退定时器（WS 断线时每 10s 轮询一次）
    const fallbackTimer = setInterval(() => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        fallbackPoll()
      }
    }, 10_000)

    return () => {
      unmountedRef.current = true
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      if (timerRef.current) {
        clearTimeout(timerRef.current)
      }
      clearInterval(fallbackTimer)
    }
  }, [connect, fallbackPoll])

  return { tickers, isConnected, isFallback, reconnectAttempts: attemptRef.current }
}
