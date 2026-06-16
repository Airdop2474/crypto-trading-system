"use client"

import useSWR from "swr"
import { usePathname } from "next/navigation"
import { Bell, RadioTower } from "lucide-react"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import { fmtNum, fmtPct } from "@/lib/format"
import { Button } from "@/components/ui/button"

const titles: Record<string, string> = {
  "/": "总览仪表盘",
  "/grid": "网格交易",
  "/price-action": "价格行为策略",
  "/positions": "持仓与资产",
  "/orders": "订单与成交",
  "/analytics": "收益统计",
}

export function TopBar() {
  const pathname = usePathname()
  const { data: tickers } = useSWR("tickers", api.getTickers, {
    refreshInterval: 5000,
  })

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-border bg-background/80 px-4 backdrop-blur md:px-6">
      <div className="flex items-center gap-4">
        <h1 className="text-sm font-semibold md:text-base">{titles[pathname] ?? "QuantDesk"}</h1>
        <span className="hidden items-center gap-1.5 rounded-full border border-success/30 bg-success/10 px-2.5 py-1 text-[11px] font-medium text-success sm:flex">
          <RadioTower className="size-3" />
          实时连接
        </span>
      </div>

      <div className="flex items-center gap-3">
        <div className="hidden items-center gap-4 lg:flex">
          {tickers?.slice(0, 3).map((t) => (
            <div key={t.symbol} className="flex items-center gap-1.5 font-mono text-xs">
              <span className="text-muted-foreground">{t.symbol.split("/")[0]}</span>
              <span className="tabular-nums">{fmtNum(t.price, t.price < 1 ? 4 : 2)}</span>
              <span className={cn("tabular-nums", t.changePct >= 0 ? "text-success" : "text-destructive")}>
                {fmtPct(t.changePct)}
              </span>
            </div>
          ))}
        </div>
        <Button variant="ghost" size="icon" className="size-8" aria-label="通知">
          <Bell className="size-4" />
        </Button>
      </div>
    </header>
  )
}
