"use client"

import useSWR from "swr"
import { api } from "@/lib/api"
import { fmtNum, fmtPct, pnlColor } from "@/lib/format"
import { StatCard } from "@/components/stat-card"
import { TrendingDown, TrendingUp, Activity, Gauge, Calendar, BarChart3 } from "lucide-react"
import { ApiError } from "@/components/api-error"

/**
 * /risk 页头部风险指标卡（6 张，比总览页的 4 张更全）
 */
export function RiskMetricsGrid() {
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

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
      <StatCard
        label="最大回撤"
        value={isLoading ? "—" : fmtPct(data?.max_drawdown_pct ?? 0).replace("+", "")}
        sub={`持续 ${data?.max_drawdown_duration ?? 0} bar`}
        icon={TrendingDown}
        valueClassName="text-destructive"
        loading={isLoading}
      />
      <StatCard
        label="当前回撤"
        value={isLoading ? "—" : fmtPct(data?.current_drawdown ?? 0).replace("+", "")}
        sub={`峰值 $${fmtNum(data?.equity_peak ?? 0, 0)}`}
        subClassName={pnlColor(data?.current_drawdown ?? 0)}
        icon={TrendingDown}
        valueClassName={pnlColor(data?.current_drawdown ?? 0)}
        loading={isLoading}
      />
      <StatCard
        label="年化收益率"
        value={isLoading ? "—" : fmtPct(data?.annual_return ?? 0)}
        icon={TrendingUp}
        valueClassName={pnlColor(data?.annual_return ?? 0)}
        loading={isLoading}
      />
      <StatCard
        label="夏普比率"
        value={isLoading ? "—" : fmtNum(data?.sharpe_ratio ?? 0, 2)}
        sub={data ? (data.sharpe_ratio >= 1 ? "优秀" : data.sharpe_ratio >= 0.5 ? "可接受" : "偏低") : undefined}
        subClassName={
          data
            ? data.sharpe_ratio >= 1
              ? "text-success"
              : data.sharpe_ratio >= 0.5
                ? "text-warning"
                : "text-destructive"
            : undefined
        }
        icon={Activity}
        loading={isLoading}
      />
      <StatCard
        label="Sortino 比率"
        value={isLoading ? "—" : fmtNum(data?.sortino_ratio ?? 0, 2)}
        icon={BarChart3}
        loading={isLoading}
      />
      <StatCard
        label="年化波动率"
        value={isLoading ? "—" : `${fmtNum(data?.volatility ?? 0, 1)}%`}
        sub={data ? (data.volatility < 20 ? "低波动" : data.volatility < 50 ? "中波动" : "高波动") : undefined}
        subClassName={
          data
            ? data.volatility < 20
              ? "text-success"
              : data.volatility < 50
                ? "text-warning"
                : "text-destructive"
            : undefined
        }
        icon={Gauge}
        loading={isLoading}
      />
    </div>
  )
}
