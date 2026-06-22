// 数字与货币格式化工具

export function fmtUsd(n: number, decimals = 2): string {
  return `$${n.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`
}

export function fmtNum(n: number, decimals = 2): string {
  return n.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

export function fmtPct(n: number, decimals = 2): string {
  const sign = n > 0 ? "+" : ""
  return `${sign}${n.toFixed(decimals)}%`
}

export function fmtSigned(n: number, decimals = 2): string {
  const sign = n > 0 ? "+" : ""
  return `${sign}${n.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`
}

export function fmtCompact(n: number): string {
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`
  if (n >= 1e3) return `$${(n / 1e3).toFixed(2)}K`
  return `$${n.toFixed(2)}`
}

// 盈亏正负对应的文字颜色 class
export function pnlColor(n: number): string {
  if (n > 0) return "text-success"
  if (n < 0) return "text-destructive"
  return "text-muted-foreground"
}
