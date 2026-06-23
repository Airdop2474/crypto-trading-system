"use client"

import { useEffect } from "react"
import { getPref } from "@/lib/prefs"

export function PrefsApplier() {
  useEffect(() => {
    const compact = getPref("compactMode")
    document.documentElement.classList.toggle("compact-mode", compact)
  }, [])

  useEffect(() => {
    const handler = (e: StorageEvent) => {
      if (e.key === "quantdesk-ui-prefs") {
        const compact = getPref("compactMode")
        document.documentElement.classList.toggle("compact-mode", compact)
      }
    }
    window.addEventListener("storage", handler)
    return () => window.removeEventListener("storage", handler)
  }, [])

  return null
}
