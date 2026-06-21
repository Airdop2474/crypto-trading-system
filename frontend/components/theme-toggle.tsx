"use client"

import { useEffect, useState } from "react"
import { useTheme } from "next-themes"
import { Monitor, Moon, Sun } from "lucide-react"
import { Button } from "@/components/ui/button"
import { toast } from "sonner"

type ThemeChoice = "light" | "dark" | "system"

const ORDER: ThemeChoice[] = ["dark", "light", "system"]
const LABEL: Record<ThemeChoice, string> = {
  dark: "深色",
  light: "浅色",
  system: "跟随系统",
}

/**
 * 主题切换按钮 — 单击在 深 / 浅 / 系统 三态间循环。
 *
 * 放置在 TopBar 右侧。mounted 前不渲染图标，避免 hydration 不匹配。
 * 用循环切换而非 DropdownMenu，避免 base-ui Trigger 的 render prop 与
 * shadcn 风格 asChild 不兼容的问题。
 */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)

  useEffect(() => setMounted(true), [])

  if (!mounted) {
    return (
      <Button variant="ghost" size="icon" className="size-8" aria-label="切换主题" disabled>
        <Sun className="size-4" />
      </Button>
    )
  }

  const current = (theme as ThemeChoice) ?? "dark"
  const Icon = current === "light" ? Sun : current === "system" ? Monitor : Moon

  const cycle = () => {
    const idx = ORDER.indexOf(current)
    const next = ORDER[(idx + 1) % ORDER.length]
    setTheme(next)
    toast.info(`主题切换为：${LABEL[next]}`)
  }

  return (
    <Button
      variant="ghost"
      size="icon"
      className="size-8"
      aria-label={`切换主题（当前：${LABEL[current]}）`}
      title={`当前：${LABEL[current]}（点击切换）`}
      onClick={cycle}
    >
      <Icon className="size-4" />
    </Button>
  )
}
