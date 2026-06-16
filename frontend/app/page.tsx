import { AccountCards } from "@/components/overview/account-cards"
import { ActiveStrategies } from "@/components/overview/active-strategies"
import { EquityChart } from "@/components/overview/equity-chart"
import { MarketWatch } from "@/components/overview/market-watch"

export default function OverviewPage() {
  return (
    <div className="flex flex-col gap-4 pb-16 md:pb-0">
      <AccountCards />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <EquityChart />
        </div>
        <MarketWatch />
      </div>

      <ActiveStrategies />
    </div>
  )
}
