"use client"

import { Download, Loader2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { exportCsv, csvFilename, type CsvColumn } from "@/lib/csv"

interface ExportButtonProps<T> {
  /** 数据行（来自 SWR 缓存，无需重新请求） */
  rows: T[]
  /** 列定义 */
  columns: CsvColumn<T>[]
  /** 文件名前缀，自动加日期戳与 .csv 后缀 */
  filenamePrefix: string
  /** 禁用条件（如 loading 或空数据） */
  disabled?: boolean
  /** 按钮文字，默认"导出 CSV" */
  label?: string
}

/**
 * CSV 导出按钮
 *
 * 通用组件，订单页/持仓页/分析页复用。
 * 点击后立即用当前 SWR 缓存数据生成 CSV 并下载，无网络请求。
 */
export function ExportButton<T>({
  rows,
  columns,
  filenamePrefix,
  disabled,
  label = "导出 CSV",
}: ExportButtonProps<T>) {
  const handleExport = () => {
    if (!rows || rows.length === 0) {
      toast.warning("没有数据可导出")
      return
    }
    try {
      const filename = csvFilename(filenamePrefix)
      exportCsv(filename, rows, columns)
      toast.success(`已导出 ${rows.length} 条到 ${filename}`)
    } catch (e) {
      const msg = e instanceof Error ? e.message : "未知错误"
      toast.error("导出失败", { description: msg })
    }
  }

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={handleExport}
      disabled={disabled || !rows || rows.length === 0}
      className="gap-1.5"
    >
      {disabled ? (
        <Loader2 className="size-3.5 animate-spin" />
      ) : (
        <Download className="size-3.5" />
      )}
      {label}
    </Button>
  )
}
