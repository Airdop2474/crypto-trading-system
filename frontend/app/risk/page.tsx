"use client"

import useSWR from "swr"
import { ErrorBoundary } from "@/components/error-boundary"
import { RiskMetricsGrid } from "@/components/risk/risk-metrics-grid"
import { DrawdownChart } from "@/components/risk/drawdown-chart"
import { RiskStatusCard } from "@/components/risk/risk-status-card"
import { PortfolioHeatCard } from "@/components/risk/portfolio-heat-card"
import { StopLossConfigCard } from "@/components/risk/stop-loss-config-card"
import { api } from "@/lib/api"

export default function RiskPage() {
  const { data: stopConfigs } = useSWR(
    "stop-configs",
    () => api.getStopConfigs().catch(() => undefined),
    { revalidateOnFocus: false }
  )

  return (
    <div className="flex flex-col gap-4 pb-16 md:pb-0">
      <ErrorBoundary>
        <PortfolioHeatCard />
      </ErrorBoundary>

      <ErrorBoundary>
        <RiskMetricsGrid />
      </ErrorBoundary>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ErrorBoundary>
            <DrawdownChart />
          </ErrorBoundary>
        </div>
        <ErrorBoundary>
          <RiskStatusCard />
        </ErrorBoundary>
      </div>

      <ErrorBoundary>
        <StopLossConfigCard configs={stopConfigs} />
      </ErrorBoundary>
    </div>
  )
}
