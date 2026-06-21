"use client"

import { useState } from "react"
import useSWR from "swr"
import { api } from "@/lib/api"
import { fmtNum, fmtUsd } from "@/lib/format"
import { StatCard } from "@/components/stat-card"
import { OrdersTable } from "@/components/orders/orders-table"
import { ApiError } from "@/components/api-error"
import { ExportButton } from "@/components/export-button"
import { ErrorBoundary } from "@/components/error-boundary"
import type { CsvColumn } from "@/lib/csv"
import type { Order } from "@/lib/types"

const DEFAULT_PAGE_SIZE = 20

// 订单 CSV 列定义
const orderColumns: CsvColumn<Order>[] = [
  { key: "id", label: "订单ID" },
  { key: "time", label: "时间" },
  { key: "symbol", label: "交易对" },
  { key: "side", label: "方向" },
  { key: "type", label: "类型" },
  { key: "price", label: "委托价" },
  { key: "amount", label: "数量" },
  { key: "filled", label: "已成交" },
  { key: "fee", label: "手续费" },
  { key: "status", label: "状态" },
  { key: "strategyName", label: "策略" },
]

export default function OrdersPage() {
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [page, setPage] = useState(1)

  // SWR key 含分页参数，切换页码/每页条数会自动重发请求
  const offset = (page - 1) * pageSize
  const swrKey = `orders?limit=${pageSize}&offset=${offset}`

  const { data, isLoading, error, mutate } = useSWR(swrKey, () =>
    api.getOrders(pageSize, offset),
  )

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const stats = data?.stats

  // 统计卡用后端聚合 stats，不随翻页变化
  const openCount = stats?.open_count ?? 0
  const filledCount = stats?.filled_count ?? 0
  const totalFee = stats?.total_fee ?? 0

  const handlePageSizeChange = (size: number) => {
    setPageSize(size)
    setPage(1) // 切换每页条数时回到第 1 页
  }

  const handlePageChange = (next: number) => {
    setPage(next)
  }

  return (
    <ErrorBoundary>
    <div className="flex flex-col gap-4 pb-16 md:pb-0">
      <div className="flex items-center justify-end">
        <ExportButton
          rows={items}
          columns={orderColumns}
          filenamePrefix="orders"
          disabled={isLoading || items.length === 0}
        />
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="订单总数"
          value={isLoading && !stats ? "—" : fmtNum(total, 0)}
          loading={isLoading && !stats}
        />
        <StatCard
          label="挂单中"
          value={isLoading && !stats ? "—" : fmtNum(openCount, 0)}
          loading={isLoading && !stats}
        />
        <StatCard
          label="已成交"
          value={isLoading && !stats ? "—" : fmtNum(filledCount, 0)}
          loading={isLoading && !stats}
        />
        <StatCard
          label="累计手续费"
          value={isLoading && !stats ? "—" : fmtUsd(totalFee)}
          loading={isLoading && !stats}
        />
      </div>

      {error ? (
        <ApiError error={error} onRetry={() => mutate()} title="订单数据加载失败" />
      ) : (
        <OrdersTable
          orders={items}
          total={total}
          pageSize={pageSize}
          page={page}
          loading={isLoading}
          onPageSizeChange={handlePageSizeChange}
          onPageChange={handlePageChange}
        />
      )}
    </div>
    </ErrorBoundary>
  )
}
