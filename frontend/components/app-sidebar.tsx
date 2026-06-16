"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  Activity,
  CandlestickChart,
  Grid3x3,
  LayoutDashboard,
  LineChart,
  ListOrdered,
  Wallet,
} from "lucide-react"
import { cn } from "@/lib/utils"

const nav = [
  { href: "/", label: "总览仪表盘", icon: LayoutDashboard },
  { href: "/grid", label: "网格交易", icon: Grid3x3 },
  { href: "/price-action", label: "价格行为策略", icon: CandlestickChart },
  { href: "/positions", label: "持仓与资产", icon: Wallet },
  { href: "/orders", label: "订单与成交", icon: ListOrdered },
  { href: "/analytics", label: "收益统计", icon: LineChart },
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

      <nav className="flex flex-1 flex-col gap-1 p-3">
        <p className="px-2 pb-1 pt-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          交易管理
        </p>
        {nav.map((item) => {
          const active = pathname === item.href
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
      </nav>

      <div className="border-t border-border p-3">
        <div className="flex items-center gap-3 rounded-md px-2 py-2">
          <div className="flex size-8 items-center justify-center rounded-full bg-secondary text-xs font-medium text-secondary-foreground">
            T
          </div>
          <div className="min-w-0">
            <p className="truncate text-xs font-medium text-sidebar-foreground">交易员</p>
            <p className="truncate text-[11px] text-muted-foreground">主账户 · 实盘</p>
          </div>
        </div>
      </div>
    </aside>
  )
}
