import { ErrorBoundary } from "@/components/error-boundary"
import { AnalysisReport } from "@/components/agent/analysis-report"
import { AnalyzeTrigger } from "@/components/agent/analyze-trigger"
import { AuditLogs } from "@/components/agent/audit-logs"
import { AdoptionCard } from "@/components/agent/adoption-card"
import { EvolutionPanel } from "@/components/agent/evolution-panel"
import { EvolutionHistory } from "@/components/agent/evolution-history"
import { EvolutionStatsCard } from "@/components/agent/evolution-stats"

export default function AgentPage() {
  return (
    <div className="flex flex-col gap-4 pb-16 md:pb-0">
      <ErrorBoundary>
        <AnalysisReport />
      </ErrorBoundary>

      <ErrorBoundary>
        <AnalyzeTrigger />
      </ErrorBoundary>

      <ErrorBoundary>
        <EvolutionStatsCard />
      </ErrorBoundary>

      <ErrorBoundary>
        <EvolutionPanel />
      </ErrorBoundary>

      <ErrorBoundary>
        <EvolutionHistory />
      </ErrorBoundary>

      <ErrorBoundary>
        <AdoptionCard />
      </ErrorBoundary>

      <ErrorBoundary>
        <AuditLogs />
      </ErrorBoundary>
    </div>
  )
}
