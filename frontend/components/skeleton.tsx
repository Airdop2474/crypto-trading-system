"use client"

import { type ReactNode } from "react"

/** Skeleton block for loading charts / cards */
export function SkeletonBlock({
  className = "",
  lines = 3,
}: {
  className?: string
  lines?: number
}) {
  return (
    <div className={`animate-pulse space-y-3 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="h-4 rounded bg-muted/60"
          style={{ width: `${85 - i * 15}%` }}
        />
      ))}
    </div>
  )
}

/** Skeleton for a stat card (value + label) */
export function SkeletonStatCard() {
  return (
    <div className="animate-pulse rounded-xl border border-border bg-card p-4 space-y-2">
      <div className="h-3 w-20 rounded bg-muted/60" />
      <div className="h-7 w-28 rounded bg-muted/50" />
      <div className="h-3 w-16 rounded bg-muted/60" />
    </div>
  )
}

/** Skeleton for a chart placeholder */
export function SkeletonChart({ className = "" }: { className?: string }) {
  return (
    <div className={`animate-pulse rounded-xl border border-border bg-card p-4 ${className}`}>
      <div className="h-4 w-32 rounded bg-muted/60 mb-4" />
      <div className="h-48 rounded bg-muted/40" />
    </div>
  )
}

/** Skeleton for a table placeholder */
export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div className="animate-pulse space-y-2">
      <div className="h-8 rounded bg-muted/50" />
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-10 rounded bg-muted/40" />
      ))}
    </div>
  )
}

/** Full page loading skeleton */
export function PageSkeleton({
  statCards = 4,
  charts = 1,
  tableRows = 5,
}: {
  statCards?: number
  charts?: number
  tableRows?: number
}) {
  return (
    <div className="space-y-6 p-6">
      <SkeletonBlock lines={2} className="max-w-sm" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: statCards }).map((_, i) => (
          <SkeletonStatCard key={i} />
        ))}
      </div>
      {Array.from({ length: charts }).map((_, i) => (
        <SkeletonChart key={i} />
      ))}
      <SkeletonTable rows={tableRows} />
    </div>
  )
}
