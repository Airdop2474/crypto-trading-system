import { ErrorBoundary } from "@/components/error-boundary"
import { AnalyzeTrigger } from "@/components/agent/analyze-trigger"
import { AuditLogs } from "@/components/agent/audit-logs"
import { AdoptionCard } from "@/components/agent/adoption-card"
import { EvolutionPanel } from "@/components/agent/evolution-panel"
import { EvolutionHistory } from "@/components/agent/evolution-history"

export default function AgentPage() {
  return (
    <div className="flex flex-col gap-4 pb-16 md:pb-0">
      <ErrorBoundary>
        <AnalyzeTrigger />
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
