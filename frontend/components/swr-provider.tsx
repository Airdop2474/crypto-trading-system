"use client"

import { SWRConfig } from "swr"
import { type ReactNode, useCallback } from "react"

/** Default fetch timeout (ms) */
const DEFAULT_TIMEOUT = 10_000

/** Wrapped fetch with timeout + error enrichment */
async function fetchWithTimeout(url: string, timeout = DEFAULT_TIMEOUT): Promise<unknown> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)

  try {
    const res = await fetch(url, {
      signal: controller.signal,
      headers: {
        "Accept": "application/json",
        "X-API-Token": process.env.NEXT_PUBLIC_API_TOKEN || "",
      },
    })
    if (!res.ok) {
      const body = await res.text().catch(() => "")
      throw new Error(
        `HTTP ${res.status}: ${body.slice(0, 200)}`,
        { cause: { status: res.status } }
      )
    }
    return res.json()
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(`Request timeout after ${timeout}ms`, { cause: { timeout: true } })
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}

/** Global SWR configuration: auto-refresh + error retry + timeout */
export function SWRProvider({ children }: { children: ReactNode }) {
  const fetcher = useCallback(
    (url: string) => fetchWithTimeout(url, DEFAULT_TIMEOUT),
    []
  )

  return (
    <SWRConfig
      value={{
        fetcher,
        refreshInterval: 30_000,      // Auto-refresh every 30s
        revalidateOnFocus: true,       // Refetch when tab regains focus
        revalidateOnReconnect: true,   // Refetch on network reconnect
        errorRetryCount: 3,            // Retry failed requests 3 times
        errorRetryInterval: 5_000,    // 5s between retries
        dedupingInterval: 2_000,       // Dedupe identical requests within 2s
        shouldRetryOnError: true,
        revalidateIfStale: true,
        revalidateOnMount: true,
        keepPreviousData: true,        // Show stale data while revalidating
      }}
    >
      {children}
    </SWRConfig>
  )
}

