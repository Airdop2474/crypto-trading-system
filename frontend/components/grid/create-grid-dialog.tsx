"use client"

import { useState } from "react"
import { Plus } from "lucide-react"
import { toast } from "sonner"
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

export function CreateGridDialog() {
  const [open, setOpen] = useState(false)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    // 真实接入时：调用 api.createStrategy(...)
    toast.success("网格策略已创建并启动")
    setOpen(false)
  }

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
            <Select defaultValue="BTC/USDT">
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
              <Input id="lower" type="number" placeholder="60000" required />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="upper">价格上限</Label>
              <Input id="upper" type="number" placeholder="72000" required />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-2">
              <Label htmlFor="count">网格数量</Label>
              <Input id="count" type="number" placeholder="60" required />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="invest">投入本金 (USDT)</Label>
              <Input id="invest" type="number" placeholder="30000" required />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              取消
            </Button>
            <Button type="submit">创建并启动</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
