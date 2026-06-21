"use client"

import useSWR from "swr"
import { TrendingDown, Activity, Zap, Gauge } from "lucide-react"
import { api } from "@/lib/api"
import { fmtNum, fmtPct, pnlColor } from "@/lib/format"
import { StatCard } from "@/components/stat-card"
import { ApiError } from "@/components/api-error"

/**
 * 总览页风险指标看板（4 张卡）
 *
 * 数据源：GET /account/risk-metrics
 * 展示：最大回撤 / 夏普 / Sortino / 年化波动率
 */
export function RiskMetricsCards() {
  const { data, error, isLoading, mutate } = useSWR(
    "risk-metrics",
    api.getRiskMetrics,
    { revalidateOnFocus: false, refreshInterval: 60_000 },
  )

  if (error) {
    return (
      <ApiError
        error={error}
        onRetry={() => mutate()}
        title="风险指标加载失败"
        minHeight={120}
      />
    )
  }

  const maxDD = data?.max_drawdown_pct ?? 0
  const sharpe = data?.sharpe_ratio ?? 0
  const sortino = data?.sortino_ratio ?? 0
  const vol = data?.volatility ?? 0

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <StatCard
        label="最大回撤"
        value={isLoading ? "—" : fmtPct(maxDD).replace("+", "")}
        sub={`当前 ${fmtPct(data?.current_drawdown ?? 0).replace("+", "")}`}
        subClassName={pnlColor(data?.current_drawdown ?? 0)}
        icon={TrendingDown}
        valueClassName="text-destructive"
        loading={isLoading}
      />
      <StatCard
        label="夏普比率"
        value={isLoading ? "—" : fmtNum(sharpe, 2)}
        sub={sharpe >= 1 ? "优秀" : sharpe >= 0.5 ? "可接受" : "偏低"}
        subClassName={sharpe >= 1 ? "text-success" : sharpe >= 0.5 ? "text-warning" : "text-destructive"}
        icon={Activity}
        loading={isLoading}
      />
      <StatCard
        label="Sortino 比率"
        value={isLoading ? "—" : fmtNum(sortino, 2)}
        sub={sortino >= 1.5 ? "下行风险控制好" : sortino >= 1 ? "尚可" : "下行波动大"}
        subClassName={sortino >= 1.5 ? "text-success" : sortino >= 1 ? "text-warning" : "text-destructive"}
        icon={Zap}
        loading={isLoading}
      />
      <StatCard
        label="年化波动率"
        value={isLoading ? "—" : `${fmtNum(vol, 1)}%`}
        sub={vol < 20 ? "低波动" : vol < 50 ? "中波动" : "高波动"}
        subClassName={vol < 20 ? "text-success" : vol < 50 ? "text-warning" : "text-destructive"}
        icon={Gauge}
        loading={isLoading}
      />
    </div>
  )
}
