"use client"

import { cn } from "@/lib/utils"
import { fmtCompact, fmtNum, fmtPct } from "@/lib/format"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useTickersWs } from "@/hooks/use-tickers-ws"

export function MarketWatch() {
  const { tickers: data, isConnected } = useTickersWs()

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="text-sm font-medium">
          市场行情
          <span
            className={cn(
              "ml-2 inline-block size-2 rounded-full",
              isConnected ? "bg-success" : "bg-destructive",
            )}
            title={isConnected ? "WebSocket 已连接" : "WebSocket 断线"}
            aria-label={isConnected ? "WebSocket 已连接" : "WebSocket 断线"}
          />
        </CardTitle>
      </CardHeader>
      <CardContent className="px-0">
        <div className="flex flex-col">
          {(data ?? []).map((t) => (
            <div
              key={t.symbol}
              className="flex items-center justify-between border-b border-border/60 px-6 py-2.5 last:border-0"
            >
              <div className="flex flex-col">
                <span className="text-sm font-medium">{t.symbol}</span>
                <span className="text-xs text-muted-foreground">
                  量 {fmtCompact(t.volume)}
                </span>
              </div>
              <div className="flex flex-col items-end">
                <span className="font-mono text-sm tabular-nums">
                  {fmtNum(t.price, t.price < 1 ? 4 : 2)}
                </span>
                <span
                  className={cn(
                    "font-mono text-xs tabular-nums",
                    t.changePct >= 0 ? "text-success" : "text-destructive",
                  )}
                >
                  {fmtPct(t.changePct)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
