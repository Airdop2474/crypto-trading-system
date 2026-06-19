"use client"

import { SWRConfig } from "swr"
import { type ReactNode } from "react"

/** Global SWR configuration: auto-refresh + error retry */
export function SWRProvider({ children }: { children: ReactNode }) {
  return (
    <SWRConfig
      value={{
        refreshInterval: 30_000, // Auto-refresh every 30s
        revalidateOnFocus: true,
        revalidateOnReconnect: true,
        errorRetryCount: 3,
        errorRetryInterval: 5_000,
        dedupingInterval: 2_000,
        shouldRetryOnError: true,
      }}
    >
      {children}
    </SWRConfig>
  )
}
