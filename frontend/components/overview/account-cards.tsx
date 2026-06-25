"use client"

import useSWR from "swr"
import { Coins, TrendingUp, Wallet, Activity } from "lucide-react"
import { api } from "@/lib/api"
import { fmtPct, fmtSigned, fmtUsd, pnlColor } from "@/lib/format"
import { StatCard } from "@/components/stat-card"
import { ApiError } from "@/components/api-error"

export function AccountCards() {
  const { data, isLoading, error, mutate } = useSWR("account", api.getAccountSummary, {
    refreshInterval: 10_000,
  })

  if (error && !data) {
    return <ApiError error={error} onRetry={() => mutate()} />
  }

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <StatCard
        label="账户总权益"
        value={data ? fmtUsd(data.totalEquity) : "--"}
        sub={data ? `可用 ${fmtUsd(data.availableBalance)}` : undefined}
        subClassName="text-muted-foreground"
        icon={Wallet}
        loading={isLoading}
      />
      <StatCard
        label="今日盈亏"
        value={data ? fmtSigned(data.todayPnl) : "--"}
        sub={data ? fmtPct(data.todayPnlPct) : undefined}
        subClassName={data ? pnlColor(data.todayPnl) : undefined}
        icon={Activity}
        loading={isLoading}
      />
      <StatCard
        label="未实现盈亏"
        value={data ? fmtSigned(data.unrealizedPnl) : "--"}
        sub={data ? `持仓市值 ${fmtUsd(data.positionValue)}` : undefined}
        subClassName="text-muted-foreground"
        icon={Coins}
        loading={isLoading}
      />
      <StatCard
        label="累计盈亏"
        value={data ? fmtSigned(data.totalPnl) : "--"}
        sub={data ? fmtPct(data.totalPnlPct) : undefined}
        subClassName={data ? pnlColor(data.totalPnl) : undefined}
        icon={TrendingUp}
        loading={isLoading}
      />
    </div>
  )
}
