// ============================================================================
// CSV 导出工具
// ----------------------------------------------------------------------------
// 纯前端实现，无后端依赖。用 Blob + a 标签下载。
//
// 用法：
//   import { exportCsv } from "@/lib/csv"
//   exportCsv(
//     "orders-2026-06-22.csv",
//     [{id:"1",symbol:"BTC",price:67000}, {id:"2",symbol:"ETH",price:3200}],
//     [
//       {key:"id",     label:"订单ID"},
//       {key:"symbol", label:"交易对"},
//       {key:"price",  label:"价格", format: (v) => v.toFixed(2)},
//     ],
//   )
// ============================================================================

export interface CsvColumn<T> {
  /** 行对象中取值的 key（支持嵌套，如 "stats.total"） */
  key: string
  /** CSV 列标题 */
  label: string
  /** 可选格式化函数，默认直接取值 */
  format?: (value: unknown, row: T) => string | number
}

/**
 * 从嵌套对象按 dotted path 取值
 * 例：getByPath({a:{b:1}}, "a.b") → 1
 */
function getByPath(obj: Record<string, unknown>, path: string): unknown {
  return path.split(".").reduce<unknown>((acc, k) => {
    if (acc && typeof acc === "object") {
      return (acc as Record<string, unknown>)[k]
    }
    return undefined
  }, obj)
}

/**
 * 把单元格值转成 CSV 安全字符串
 * - 含逗号 / 引号 / 换行 → 用双引号包裹，内部引号转义为 ""
 */
function escapeCell(v: unknown): string {
  if (v === null || v === undefined) return ""
  const s = String(v)
  if (/[",\n\r]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`
  }
  return s
}

/**
 * 导出 CSV 文件
 *
 * @param filename 下载文件名（含 .csv 后缀）
 * @param rows 数据行
 * @param columns 列定义（顺序即 CSV 列顺序）
 */
export function exportCsv<T>(
  filename: string,
  rows: T[],
  columns: CsvColumn<T>[],
): void {
  // 1. 表头
  const header = columns.map((c) => escapeCell(c.label)).join(",")

  // 2. 数据行
  const body = rows
    .map((row) =>
      columns
        .map((c) => {
          const raw = getByPath(row as unknown as Record<string, unknown>, c.key)
          const val = c.format ? c.format(raw, row) : raw
          return escapeCell(val)
        })
        .join(","),
    )
    .join("\r\n")

  // 3. BOM（让 Excel 正确识别 UTF-8，否则中文乱码）
  const bom = "\uFEFF"
  const csv = bom + header + "\r\n" + body

  // 4. Blob + 下载
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.style.display = "none"
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  // 释放 URL，避免内存泄漏
  setTimeout(() => URL.revokeObjectURL(url), 100)
}

/**
 * 生成带日期戳的文件名
 * 例：csvFilename("orders") → "orders-2026-06-22.csv"
 */
export function csvFilename(prefix: string): string {
  const d = new Date()
  const ymd = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
  return `${prefix}-${ymd}.csv`
}
