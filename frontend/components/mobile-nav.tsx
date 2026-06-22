"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  Bot,
  Grid3x3,
  LayoutDashboard,
  LineChart,
  ListOrdered,
  Scale,
  Server,
  Settings2,
  Wallet,
} from "lucide-react"
import { cn } from "@/lib/utils"

const nav = [
  { href: "/", label: "总览", icon: LayoutDashboard },
  { href: "/strategies", label: "策略", icon: Grid3x3 },
  { href: "/positions", label: "持仓", icon: Wallet },
  { href: "/orders", label: "订单", icon: ListOrdered },
  { href: "/analytics", label: "收益", icon: LineChart },
  { href: "/risk", label: "风控", icon: Scale },
  { href: "/agent", label: "AI", icon: Bot },
  { href: "/system", label: "系统", icon: Server },
  { href: "/settings", label: "设置", icon: Settings2 },
]

export function MobileNav() {
  const pathname = usePathname()

  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 flex overflow-x-auto border-t border-border bg-sidebar md:hidden">
      {nav.map((item) => {
        const active = pathname === item.href
        const Icon = item.icon
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex shrink-0 flex-col items-center gap-0.5 px-3 py-2 text-[10px]",
              active ? "text-primary" : "text-muted-foreground",
            )}
          >
            <Icon className="size-4" />
            {item.label}
          </Link>
        )
      })}
    </nav>
  )
}
