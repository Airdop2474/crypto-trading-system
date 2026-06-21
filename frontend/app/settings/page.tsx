"use client"

import { useEffect, useState } from "react"
import { useTheme } from "next-themes"
import { toast } from "sonner"
import { Moon, Palette, RefreshCw, Layout, Gauge } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/utils"

/** UI 偏好键（localStorage） */
const PREF_KEY = "quantdesk-ui-prefs"

interface UiPrefs {
  refreshInterval: number   // SWR 刷新间隔，秒
  defaultPage: string       // 默认打开页面
  ordersPageSize: number    // 订单每页条数
  compactMode: boolean      // 紧凑模式
  showTooltips: boolean     // 显示提示
}

const DEFAULT_PREFS: UiPrefs = {
  refreshInterval: 30,
  defaultPage: "/",
  ordersPageSize: 20,
  compactMode: false,
  showTooltips: true,
}

function loadPrefs(): UiPrefs {
  if (typeof window === "undefined") return DEFAULT_PREFS
  try {
    const raw = localStorage.getItem(PREF_KEY)
    if (!raw) return DEFAULT_PREFS
    return { ...DEFAULT_PREFS, ...JSON.parse(raw) }
  } catch {
    return DEFAULT_PREFS
  }
}

function savePrefs(prefs: UiPrefs) {
  try {
    localStorage.setItem(PREF_KEY, JSON.stringify(prefs))
  } catch {
    // 忽略写入失败（隐私模式等）
  }
}

const DEFAULT_PAGE_OPTIONS = [
  { value: "/", label: "总览仪表盘" },
  { value: "/grid", label: "网格交易" },
  { value: "/positions", label: "持仓与资产" },
  { value: "/orders", label: "订单与成交" },
  { value: "/analytics", label: "收益统计" },
  { value: "/risk", label: "风险管理" },
  { value: "/agent", label: "AI 分析中心" },
  { value: "/system", label: "系统状态" },
]

const REFRESH_OPTIONS = [
  { value: "0", label: "不自动刷新" },
  { value: "15", label: "15 秒" },
  { value: "30", label: "30 秒" },
  { value: "60", label: "60 秒" },
]

const PAGE_SIZE_OPTIONS = [
  { value: "10", label: "10 条" },
  { value: "20", label: "20 条" },
  { value: "50", label: "50 条" },
  { value: "100", label: "100 条" },
]

export default function SettingsPage() {
  const { theme, setTheme } = useTheme()
  const [prefs, setPrefs] = useState<UiPrefs>(DEFAULT_PREFS)
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setPrefs(loadPrefs())
    setMounted(true)
  }, [])

  // theme 在 mounted 前可能为 undefined（next-themes 行为），统一兜底
  const themeValue: string = theme ?? "dark"

  const update = (patch: Partial<UiPrefs>) => {
    const next = { ...prefs, ...patch }
    setPrefs(next)
    savePrefs(next)
    toast.success("设置已保存")
  }

  if (!mounted) {
    return (
      <div className="flex flex-col gap-4 pb-16 md:pb-0">
        <Card>
          <CardContent className="p-4">
            <div className="h-8 w-32 animate-pulse rounded bg-muted" />
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 pb-16 md:pb-0">
      <p className="text-sm text-muted-foreground">
        UI 偏好保存在浏览器本地，不影响其他用户。刷新页面后生效。
      </p>

      {/* 主题 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <Palette className="size-4 text-primary" />
            外观主题
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">主题模式</p>
              <p className="text-xs text-muted-foreground">深色 / 浅色 / 跟随系统</p>
            </div>
            <Select
              value={themeValue as string}
              onValueChange={(v: string | null) => {
                if (!v) return
                setTheme(v)
                toast.success(`主题切换为：${v === "dark" ? "深色" : v === "light" ? "浅色" : "跟随系统"}`)
              }}
            >
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="dark">深色</SelectItem>
                <SelectItem value="light">浅色</SelectItem>
                <SelectItem value="system">跟随系统</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* 数据刷新 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <RefreshCw className="size-4 text-primary" />
            数据刷新
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Row label="自动刷新间隔" hint="各页面 SWR 数据自动刷新频率">
            <Select
              value={String(prefs.refreshInterval)}
              onValueChange={(v) => update({ refreshInterval: Number(v) })}
            >
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {REFRESH_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Row>

          <Row label="订单每页条数" hint="订单页默认每页显示条数">
            <Select
              value={String(prefs.ordersPageSize)}
              onValueChange={(v) => update({ ordersPageSize: Number(v) })}
            >
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PAGE_SIZE_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Row>
        </CardContent>
      </Card>

      {/* 页面偏好 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <Layout className="size-4 text-primary" />
            页面偏好
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Row label="默认打开页面" hint="登录后自动跳转的页面">
            <Select
              value={prefs.defaultPage as string | null}
              onValueChange={(v: string | null) => {
                if (v) update({ defaultPage: v })
              }}
            >
              <SelectTrigger className="w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DEFAULT_PAGE_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Row>

          <Row label="紧凑模式" hint="减少卡片间距，单屏显示更多内容">
            <Switch
              checked={prefs.compactMode}
              onCheckedChange={(v) => update({ compactMode: v })}
            />
          </Row>

          <Row label="显示提示" hint="鼠标悬浮时显示辅助提示文本">
            <Switch
              checked={prefs.showTooltips}
              onCheckedChange={(v) => update({ showTooltips: v })}
            />
          </Row>
        </CardContent>
      </Card>

      {/* 重置 */}
      <div className="flex justify-end">
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setPrefs(DEFAULT_PREFS)
            savePrefs(DEFAULT_PREFS)
            toast.success("已恢复默认设置")
          }}
        >
          恢复默认
        </Button>
      </div>

      {/* 说明 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <Gauge className="size-4 text-primary" />
            说明
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-xs text-muted-foreground">
          <p>· 偏好存储在浏览器 <code className="font-mono">localStorage</code>，清除浏览器数据后会丢失</p>
          <p>· 主题切换即时生效；刷新间隔与每页条数在下次页面加载时生效</p>
          <p>· API 密钥管理、通知配置等敏感设置暂未开放（需后端加密存储）</p>
        </CardContent>
      </Card>
    </div>
  )
}

function Row({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <p className="text-sm font-medium">{label}</p>
        {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
      </div>
      {children}
    </div>
  )
}
