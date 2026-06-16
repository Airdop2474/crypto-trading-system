import type { LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"
import { Card } from "@/components/ui/card"

interface StatCardProps {
  label: string
  value: string
  sub?: string
  subClassName?: string
  valueClassName?: string
  icon?: LucideIcon
  loading?: boolean
}

export function StatCard({ label, value, sub, subClassName, valueClassName, icon: Icon, loading }: StatCardProps) {
  return (
    <Card className="gap-0 p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">{label}</span>
        {Icon ? <Icon className="size-4 text-muted-foreground" /> : null}
      </div>
      {loading ? (
        <div className="mt-2 h-7 w-28 animate-pulse rounded bg-muted" />
      ) : (
        <p className={cn("mt-1.5 font-mono text-2xl font-semibold tabular-nums tracking-tight", valueClassName)}>
          {value}
        </p>
      )}
      {sub ? (
        <p className={cn("mt-1 font-mono text-xs tabular-nums", subClassName)}>{sub}</p>
      ) : null}
    </Card>
  )
}
