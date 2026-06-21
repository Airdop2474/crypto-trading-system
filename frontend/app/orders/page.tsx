"use client"

import useSWR from "swr"
import { api } from "@/lib/api"
import { fmtNum, fmtUsd } from "@/lib/format"
import { StatCard } from "@/components/stat-card"
import { OrdersTable } from "@/components/orders/orders-table"
import { ApiError } from "@/components/api-error"

export default function OrdersPage() {
  const { data: orders, isLoading, error, mutate } = useSWR("orders", api.getOrders)
  const list = orders ?? []

  const openCount = list.filter((o) => o.status === "open" || o.status === "partially_filled").length
  const filledCount = list.filter((o) => o.status === "filled").length
  const totalFee = list.reduce((a, o) => a + o.fee, 0)

  return (
    <div className="flex flex-col gap-4 pb-16 md:pb-0">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="订单总数" value={fmtNum(list.length, 0)} loading={isLoading} />
        <StatCard label="挂单中" value={fmtNum(openCount, 0)} loading={isLoading} />
        <StatCard label="已成交" value={fmtNum(filledCount, 0)} loading={isLoading} />
        <StatCard label="累计手续费" value={fmtUsd(totalFee)} loading={isLoading} />
      </div>

      {error ? (
        <ApiError error={error} onRetry={() => mutate()} title="订单数据加载失败" />
      ) : (
        <OrdersTable orders={list} loading={isLoading} />
      )}
    </div>
  )
}
