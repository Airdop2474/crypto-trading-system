"use client"

import useSWR from "swr"
import { CheckCircle2, Percent, Timer } from "lucide-react"
import { api } from "@/lib/api"
import { StatCard } from "@/components/stat-card"
import { ApiError } from "@/components/api-error"

export function AdoptionCard() {
  const { data, error, isLoading, mutate } = useSWR(
    "agent-adoption-rate",
    () => api.getAgentAdoptionRate(),
    { revalidateOnFocus: false, refreshInterval: 60_000 },
  )

  if (error) {
    return (
      <ApiError
        error={error}
        onRetry={() => mutate()}
        title="采纳率加载失败"
        minHeight={120}
      />
    )
  }

  const total = data?.total_calls ?? 0
  const approved = data?.approved ?? 0
  const rate = data?.adoption_rate ?? 0

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <StatCard
        label="AI 分析调用次数"
        value={isLoading ? "—" : String(total)}
        icon={Timer}
        loading={isLoading}
      />
      <StatCard
        label="人工采纳次数"
        value={isLoading ? "—" : String(approved)}
        icon={CheckCircle2}
        valueClassName="text-success"
        loading={isLoading}
      />
      <StatCard
        label="建议采纳率"
        value={isLoading ? "—" : `${(rate * 100).toFixed(1)}%`}
        icon={Percent}
        valueClassName={rate >= 0.5 ? "text-success" : "text-warning"}
        loading={isLoading}
      />
    </div>
  )
}
