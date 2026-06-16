"use client"

import useSWR from "swr"
import { api } from "@/lib/api"
import { fmtSigned, fmtUsd, pnlColor } from "@/lib/format"
import { StatCard } from "@/components/stat-card"
import { PositionsTable } from "@/components/positions/positions-table"
import { AssetAllocation } from "@/components/positions/asset-allocation"
import { AssetsTable } from "@/components/positions/assets-table"

export default function PositionsPage() {
  const { data: positions, isLoading: posLoading } = useSWR("positions", api.getPositions)
  const { data: assets, isLoading: assetLoading } = useSWR("assets", api.getAssets)

  const totalValue = (assets ?? []).reduce((a, x) => a + x.valueUsdt, 0)
  const totalUnrealized = (positions ?? []).reduce((a, p) => a + p.unrealizedPnl, 0)
  const totalMargin = (positions ?? []).reduce((a, p) => a + p.margin, 0)

  return (
    <div className="flex flex-col gap-4 pb-16 md:pb-0">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="总资产估值" value={fmtUsd(totalValue)} loading={assetLoading} />
        <StatCard label="持仓未实现盈亏" value={fmtSigned(totalUnrealized)} valueClassName={pnlColor(totalUnrealized)} loading={posLoading} />
        <StatCard label="占用保证金" value={fmtUsd(totalMargin, 0)} loading={posLoading} />
        <StatCard label="持仓数量" value={String(positions?.length ?? 0)} loading={posLoading} />
      </div>

      <PositionsTable positions={positions ?? []} loading={posLoading} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <AssetAllocation assets={assets ?? []} loading={assetLoading} />
        </div>
        <div className="lg:col-span-3">
          <AssetsTable assets={assets ?? []} loading={assetLoading} />
        </div>
      </div>
    </div>
  )
}
