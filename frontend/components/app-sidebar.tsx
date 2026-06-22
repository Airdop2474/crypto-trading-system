"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  Activity,
  Layers,
  LayoutDashboard,
  LineChart,
  ListOrdered,
  Server,
  Settings,
  ShieldAlert,
  Sparkles,
  Wallet,
} from "lucide-react"
import { cn } from "@/lib/utils"

type NavItem = { href: string; label: string; icon: typeof LayoutDashboard }

const navGroups: { label: string; items: NavItem[] }[] = [
  {
    label: "交易管理",
    items: [
      { href: "/", label: "总览仪表盘", icon: LayoutDashboard },
      { href: "/strategies", label: "全部策略", icon: Layers },
      { href: "/positions", label: "持仓与资产", icon: Wallet },
      { href: "/orders", label: "订单与成交", icon: ListOrdered },
    ],
  },
  {
    label: "分析与风控",
    items: [
      { href: "/analytics", label: "收益统计", icon: LineChart },
      { href: "/risk", label: "风险管理", icon: ShieldAlert },
    ],
  },
  {
    label: "系统与工具",
    items: [
      { href: "/agent", label: "AI 分析中心", icon: Sparkles },
      { href: "/system", label: "系统状态", icon: Server },
      { href: "/settings", label: "设置", icon: Settings },
    ],
  },
]

export function AppSidebar() {
  const pathname = usePathname()

  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-sidebar md:flex">
      <div className="flex h-14 items-center gap-2 border-b border-border px-5">
        <div className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Activity className="size-4" />
        </div>
        <span className="font-mono text-sm font-semibold tracking-tight text-sidebar-foreground">
          QuantDesk
        </span>
      </div>

      <nav className="flex flex-1 flex-col gap-4 overflow-y-auto p-3">
        {navGroups.map((group) => (
          <div key={group.label} className="flex flex-col gap-1">
            <p className="px-2 pb-1 pt-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              {group.label}
            </p>
            {group.items.map((item) => {
              const active = item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href)
              const Icon = item.icon
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                    active
                      ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                      : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground",
                  )}
                >
                  <Icon className="size-4 shrink-0" />
                  {item.label}
                </Link>
              )
            })}
          </div>
        ))}
      </nav>

      <div className="border-t border-border p-3">
        <div className="flex items-center gap-3 rounded-md px-2 py-2">
          <div className="flex size-8 items-center justify-center rounded-full bg-secondary text-xs font-medium text-secondary-foreground">
            T
          </div>
          <div className="min-w-0">
            <p className="truncate text-xs font-medium text-sidebar-foreground">交易员</p>
            <p className="truncate text-[11px] text-muted-foreground">主账户 · 模拟盘</p>
          </div>
        </div>
      </div>
    </aside>
  )
}
