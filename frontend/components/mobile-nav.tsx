"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  CandlestickChart,
  Grid3x3,
  LayoutDashboard,
  LineChart,
  ListOrdered,
  Wallet,
} from "lucide-react"
import { cn } from "@/lib/utils"

const nav = [
  { href: "/", label: "总览", icon: LayoutDashboard },
  { href: "/grid", label: "网格", icon: Grid3x3 },
  { href: "/price-action", label: "行为", icon: CandlestickChart },
  { href: "/positions", label: "持仓", icon: Wallet },
  { href: "/orders", label: "订单", icon: ListOrdered },
  { href: "/analytics", label: "收益", icon: LineChart },
]

export function MobileNav() {
  const pathname = usePathname()

  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 flex border-t border-border bg-sidebar md:hidden">
      {nav.map((item) => {
        const active = pathname === item.href
        const Icon = item.icon
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px]",
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
