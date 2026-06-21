"use client"

import useSWR from "swr"
import { api } from "@/lib/api"
import { fmtSigned, fmtUsd, pnlColor } from "@/lib/format"
import { StatCard } from "@/components/stat-card"
import { PositionsTable } from "@/components/positions/positions-table"
import { AssetAllocation } from "@/components/positions/asset-allocation"
import { AssetsTable } from "@/components/positions/assets-table"
import { ClosedTradesTable } from "@/components/positions/closed-trades-table"
import { PnlDistributionChart } from "@/components/positions/pnl-distribution-chart"
import { ApiError } from "@/components/api-error"
import { ExportButton } from "@/components/export-button"
import { ErrorBoundary } from "@/components/error-boundary"
import type { CsvColumn } from "@/lib/csv"
import type { Position, AssetBalance } from "@/lib/types"

const positionColumns: CsvColumn<Position>[] = [
  { key: "id", label: "持仓ID" },
  { key: "symbol", label: "交易对" },
  { key: "side", label: "方向" },
  { key: "size", label: "数量" },
  { key: "entryPrice", label: "开仓价" },
  { key: "markPrice", label: "标记价" },
  { key: "leverage", label: "杠杆" },
  { key: "margin", label: "保证金" },
  { key: "unrealizedPnl", label: "未实现盈亏" },
  { key: "unrealizedPnlPct", label: "未实现盈亏%" },
  { key: "strategyName", label: "策略" },
]

const assetColumns: CsvColumn<AssetBalance>[] = [
  { key: "asset", label: "资产" },
  { key: "total", label: "总量" },
  { key: "available", label: "可用" },
  { key: "inOrder", label: "挂单占用" },
  { key: "valueUsdt", label: "估值(USDT)" },
  { key: "allocationPct", label: "占比%" },
]

export default function PositionsPage() {
  const { data: positions, isLoading: posLoading, error: posError, mutate: reloadPos } = useSWR("positions", api.getPositions)
  const { data: assets, isLoading: assetLoading, error: assetError, mutate: reloadAssets } = useSWR("assets", api.getAssets)

  const totalValue = (assets ?? []).reduce((a, x) => a + x.valueUsdt, 0)
  const totalUnrealized = (positions ?? []).reduce((a, p) => a + p.unrealizedPnl, 0)
  const totalMargin = (positions ?? []).reduce((a, p) => a + p.margin, 0)

  return (
    <ErrorBoundary>
    <div className="flex flex-col gap-4 pb-16 md:pb-0">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <ExportButton
          rows={positions ?? []}
          columns={positionColumns}
          filenamePrefix="positions"
          disabled={posLoading || !positions || positions.length === 0}
          label="导出持仓"
        />
        <ExportButton
          rows={assets ?? []}
          columns={assetColumns}
          filenamePrefix="assets"
          disabled={assetLoading || !assets || assets.length === 0}
          label="导出资产"
        />
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="总资产估值" value={fmtUsd(totalValue)} loading={assetLoading} />
        <StatCard label="持仓未实现盈亏" value={fmtSigned(totalUnrealized)} valueClassName={pnlColor(totalUnrealized)} loading={posLoading} />
        <StatCard label="占用保证金" value={fmtUsd(totalMargin, 0)} loading={posLoading} />
        <StatCard label="持仓数量" value={String(positions?.length ?? 0)} loading={posLoading} />
      </div>

      {posError ? (
        <ApiError error={posError} onRetry={() => reloadPos()} title="持仓数据加载失败" />
      ) : (
        <PositionsTable positions={positions ?? []} loading={posLoading} />
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <div className="lg:col-span-2">
          {assetError ? (
            <ApiError error={assetError} onRetry={() => reloadAssets()} title="资产配置加载失败" />
          ) : (
            <AssetAllocation assets={assets ?? []} loading={assetLoading} />
          )}
        </div>
        <div className="lg:col-span-3">
          {assetError ? (
            <ApiError error={assetError} onRetry={() => reloadAssets()} title="资产明细加载失败" />
          ) : (
            <AssetsTable assets={assets ?? []} loading={assetLoading} />
          )}
        </div>
      </div>

      {/* 平仓历史 + 盈亏分布 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ClosedTradesTable />
        <PnlDistributionChart />
      </div>
    </div>
    </ErrorBoundary>
  )
}
