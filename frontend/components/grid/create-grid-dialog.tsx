"use client"

import { useState } from "react"
import { Plus, Loader2 } from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

interface Props {
  onCreated?: () => void
}

export function CreateGridDialog({ onCreated }: Props) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [form, setForm] = useState({
    symbol: "BTC/USDT",
    lowerPrice: "",
    upperPrice: "",
    gridCount: "",
    investment: "",
  })

  function updateField(key: string, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)

    const lowerPrice = parseFloat(form.lowerPrice)
    const upperPrice = parseFloat(form.upperPrice)
    const gridCount = parseInt(form.gridCount, 10)
    const investment = parseFloat(form.investment)

    if (isNaN(lowerPrice) || isNaN(upperPrice) || lowerPrice >= upperPrice) {
      toast.error("价格区间无效：下限必须小于上限")
      setLoading(false)
      return
    }
    if (isNaN(gridCount) || gridCount < 3 || gridCount > 50) {
      toast.error("网格数量必须在 3-50 之间")
      setLoading(false)
      return
    }
    if (isNaN(investment) || investment <= 0) {
      toast.error("投入本金必须为正数")
      setLoading(false)
      return
    }

    try {
      const result = await api.createGridStrategy({
        symbol: form.symbol,
        lowerPrice,
        upperPrice,
        gridCount,
        investment,
      })
      toast.success(`网格策略 "${result.name}" 已创建并启动`, {
        description: `${form.symbol} | ${gridCount} 格 | ${investment.toLocaleString()} USDT`,
      })
      setOpen(false)
      setForm({ symbol: "BTC/USDT", lowerPrice: "", upperPrice: "", gridCount: "", investment: "" })
      onCreated?.()
    } catch (err) {
      const msg = err instanceof Error ? err.message : "未知错误"
      toast.error(`创建失败: ${msg}`)
    } finally {
      setLoading(false)
    }
  }

  const lower = parseFloat(form.lowerPrice)
  const upper = parseFloat(form.upperPrice)
  const count = parseInt(form.gridCount, 10) || 1
  const perGridPct = (!isNaN(lower) && !isNaN(upper) && lower > 0)
    ? ((upper - lower) / count / lower * 100).toFixed(2)
    : null

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" className="gap-1.5" />}>
        <Plus className="size-4" />
        创建网格
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>创建网格策略</DialogTitle>
          <DialogDescription>设置交易对、价格区间与网格数量。</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="symbol">交易对</Label>
            <Select value={form.symbol} onValueChange={(v) => v && updateField("symbol", v)}>
              <SelectTrigger id="symbol">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="BTC/USDT">BTC/USDT</SelectItem>
                <SelectItem value="ETH/USDT">ETH/USDT</SelectItem>
                <SelectItem value="SOL/USDT">SOL/USDT</SelectItem>
                <SelectItem value="BNB/USDT">BNB/USDT</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-2">
              <Label htmlFor="lower">价格下限</Label>
              <Input
                id="lower"
                type="number"
                placeholder="60000"
                required
                value={form.lowerPrice}
                onChange={(e) => updateField("lowerPrice", e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="upper">价格上限</Label>
              <Input
                id="upper"
                type="number"
                placeholder="72000"
                required
                value={form.upperPrice}
                onChange={(e) => updateField("upperPrice", e.target.value)}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-2">
              <Label htmlFor="count">网格数量</Label>
              <Input
                id="count"
                type="number"
                placeholder="10"
                min={3}
                max={50}
                required
                value={form.gridCount}
                onChange={(e) => updateField("gridCount", e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="invest">投入本金 (USDT)</Label>
              <Input
                id="invest"
                type="number"
                placeholder="10000"
                required
                value={form.investment}
                onChange={(e) => updateField("investment", e.target.value)}
              />
            </div>
          </div>

          {perGridPct !== null && (
            <div className="rounded-md bg-secondary/40 px-3 py-2 text-xs text-muted-foreground">
              预估每格利润率: <span className="font-mono text-foreground">{perGridPct}%</span>
              {count > 0 && !isNaN(lower) && (
                <span className="ml-2">
                  · 区间宽度{" "}
                  <span className="font-mono text-foreground">
                    {((upper - lower) / lower * 100).toFixed(1)}%
                  </span>
                </span>
              )}
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)} disabled={loading}>
              取消
            </Button>
            <Button type="submit" disabled={loading}>
              {loading && <Loader2 className="mr-1.5 size-4 animate-spin" />}
              {loading ? "创建中..." : "创建并启动"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
