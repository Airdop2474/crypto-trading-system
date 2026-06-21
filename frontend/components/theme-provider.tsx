"use client"

/**
 * 主题 Provider — 包裹 next-themes 的 ThemeProvider
 *
 * 默认深色（与原"统一深色交易终端"设计一致），
 * 允许用户在 TopBar 切换到浅色或跟随系统。
 */

import * as React from "react"
import { ThemeProvider as NextThemesProvider } from "next-themes"

export function ThemeProvider({
  children,
  ...props
}: React.ComponentProps<typeof NextThemesProvider>) {
  return <NextThemesProvider {...props}>{children}</NextThemesProvider>
}
