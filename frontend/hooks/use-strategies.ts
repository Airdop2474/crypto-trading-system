"use client"

import useSWR from "swr"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { Strategy, StrategyStatus } from "@/lib/types"

export function useStrategies() {
  const { data, isLoading, mutate } = useSWR("strategies", api.getStrategies)

  async function setStatus(id: string, status: StrategyStatus) {
    // 乐观更新：先改 UI，再调用服务层
    mutate(
      (prev) => prev?.map((s) => (s.id === id ? { ...s, status } : s)),
      { revalidate: false },
    )
    try {
      await api.updateStrategyStatus(id, status)
      const label = status === "running" ? "已启动" : status === "paused" ? "已暂停" : "已停止"
      toast.success(`策略${label}`)
    } catch {
      toast.error("操作失败，请重试")
      mutate()
    }
  }

  return {
    strategies: data ?? [],
    isLoading,
    setStatus,
    mutate,
  }
}

export function filterByType(strategies: Strategy[], type: Strategy["type"]) {
  return strategies.filter((s) => s.type === type)
}
