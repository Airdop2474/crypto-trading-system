"use client"

import { useState } from "react"
import useSWR from "swr"
import { usePathname } from "next/navigation"
import { Bell, RadioTower, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { fmtNum, fmtPct } from "@/lib/format"
import { Button } from "@/components/ui/button"
import { useTickersWs } from "@/hooks/use-tickers-ws"
import { ThemeToggle } from "@/components/theme-toggle"
import { api } from "@/lib/api"

const titles: Record<string, string> = {
  "/": "总览仪表盘",
  "/grid": "网格交易",
  "/price-action": "价格行为策略",
  "/positions": "持仓与资产",
  "/orders": "订单与成交",
  "/analytics": "收益统计",
  "/risk": "风险管理",
  "/agent": "AI 分析中心",
  "/system": "系统状态",
  "/settings": "设置",
}

export function TopBar() {
  const pathname = usePathname()
  const { tickers, isConnected, isFallback } = useTickersWs()
  const [notifOpen, setNotifOpen] = useState(false)

  const { data: riskStatus } = useSWR("risk-status", () => api.getRiskStatus(), {
    refreshInterval: 30000,
    revalidateOnFocus: false,
  })

  const alerts = riskStatus?.events ?? []
  const hasAlerts = alerts.length > 0

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-border bg-background/80 px-4 backdrop-blur md:px-6">
      <div className="flex items-center gap-4">
        <h1 className="text-sm font-semibold md:text-base">{titles[pathname] ?? "QuantDesk"}</h1>
        <span
          className={cn(
            "hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium sm:flex",
            isConnected
              ? "border-success/30 bg-success/10 text-success"
              : isFallback
                ? "border-warning/30 bg-warning/10 text-warning"
                : "border-destructive/30 bg-destructive/10 text-destructive",
          )}
        >
          <RadioTower className="size-3" />
          {isConnected ? "实时连接" : isFallback ? "REST 回退" : "断线中"}
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
        <div className="relative">
          <Button
            variant="ghost"
            size="icon"
            className="size-8"
            aria-label="通知"
            onClick={() => setNotifOpen((p) => !p)}
          >
            <Bell className="size-4" />
            {hasAlerts && <span className="absolute right-1.5 top-1.5 size-2 rounded-full bg-destructive" />}
          </Button>
          {notifOpen && (
            <div className="absolute right-0 top-full mt-1 w-80 rounded-lg border border-border bg-popover p-3 shadow-lg">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-semibold text-foreground">
                  风控通知 {hasAlerts ? `(${alerts.length})` : ""}
                </span>
                <button onClick={() => setNotifOpen(false)} className="text-muted-foreground hover:text-foreground">
                  <X className="size-3.5" />
                </button>
              </div>
              {!hasAlerts ? (
                <p className="py-3 text-center text-xs text-muted-foreground">暂无风控事件</p>
              ) : (
                <div className="flex max-h-56 flex-col gap-1.5 overflow-y-auto">
                  {alerts.map((evt, i) => (
                    <div
                      key={i}
                      className={cn(
                        "rounded-md border px-2.5 py-2 text-xs",
                        evt.state === "STOPPED"
                          ? "border-destructive/20 bg-destructive/5"
                          : "border-warning/20 bg-warning/5",
                      )}
                    >
                      <span className="font-medium">{evt.type}</span>
                      <span className="ml-2 text-muted-foreground">{evt.reason}</span>
                      <span className={cn(
                        "ml-2 font-mono text-[10px]",
                        evt.state === "STOPPED" ? "text-destructive" : "text-warning",
                      )}>
                        {evt.state}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
        <ThemeToggle />
      </div>
    </header>
  )
}
