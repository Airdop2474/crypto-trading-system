"use client"

import { useState } from "react"
import { toast } from "sonner"
import { Shield, Loader2, Save, Sparkles } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { api } from "@/lib/api"
import { STRATEGY_TYPE_LABEL } from "@/lib/strategy-meta"
import type { StopConfig, StopConfigMap } from "@/lib/types"

const STOP_TYPE_LABELS: Record<string, string> = {
  none: "不止损",
  atr_trailing: "ATR 追踪止损",
  range_breakout: "区间突破止损",
  time_only: "仅时间止损",
}

export function StopLossConfigCard({ configs }: { configs: StopConfigMap | undefined }) {
  const [editingType, setEditingType] = useState<string>("")
  const [form, setForm] = useState<StopConfig | null>(null)
  const [saving, setSaving] = useState(false)
  const [optimizing, setOptimizing] = useState(false)

  const strategyTypes = Object.keys(configs || {}).sort()

  const handleSelectStrategy = (type: string) => {
    setEditingType(type)
    const cfg = configs?.[type]
    if (cfg) {
      setForm({ ...cfg })
    }
  }

  const handleSave = async () => {
    if (!form || !editingType) return
    setSaving(true)
    try {
      const result = await api.saveStopConfig({
        strategy_type: editingType,
        ...form,
      })
      if (result.ok) {
        toast.success(result.message)
      } else {
        toast.error(result.message || "保存失败")
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败")
    } finally {
      setSaving(false)
    }
  }

  const update = (field: keyof StopConfig, value: number | string) => {
    setForm(prev => prev ? { ...prev, [field]: value } : prev)
  }

  const handleAutoOptimize = async () => {
    if (!editingType) return
    setOptimizing(true)
    try {
      const result = await api.autoOptimizeStopConfig(editingType)
      if (result.ok) {
        setForm({ ...result.config })
        const stats = result.stats
        const statsStr = stats
          ? `（${stats.total_trades} 笔交易，胜率 ${(stats.win_rate * 100).toFixed(1)}%，均盈 ${stats.avg_win.toFixed(1)}，均亏 ${stats.avg_loss.toFixed(1)}）`
          : ""
        toast.success(result.message, { description: statsStr })
      } else {
        toast.info(result.message)
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "AI 优化失败")
    } finally {
      setOptimizing(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Shield className="size-4 text-primary" />
          止损配置
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 策略选择 */}
        <div className="space-y-2">
          <Label className="text-sm font-medium">选择策略类型</Label>
          <Select
            value={editingType}
            onValueChange={(v: string | null) => v && handleSelectStrategy(v)}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder="选择要编辑的策略">
                {editingType ? (STRATEGY_TYPE_LABEL[editingType as keyof typeof STRATEGY_TYPE_LABEL] || editingType) : undefined}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {strategyTypes.map((type) => (
                <SelectItem key={type} value={type}>
                  <div className="flex items-center justify-between w-full">
                    <span>{STRATEGY_TYPE_LABEL[type as keyof typeof STRATEGY_TYPE_LABEL] || type}</span>
                    <Badge variant="outline" className="ml-2 text-xs">
                      {STOP_TYPE_LABELS[configs?.[type]?.stop_type || ""] || configs?.[type]?.stop_type}
                    </Badge>
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* 编辑表单 */}
        {form && editingType && (
          <div className="space-y-3 rounded-lg border p-3">
            {/* 止损类型 */}
            <div className="space-y-2">
              <Label className="text-xs">止损类型</Label>
              <Select
                value={form.stop_type}
                onValueChange={(v: string | null) => v && update("stop_type", v)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue>
                    {STOP_TYPE_LABELS[form.stop_type] || form.stop_type}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">不止损</SelectItem>
                  <SelectItem value="atr_trailing">ATR 追踪止损</SelectItem>
                  <SelectItem value="range_breakout">区间突破止损</SelectItem>
                  <SelectItem value="time_only">仅时间止损</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* ATR 参数（仅 atr_trailing 显示） */}
            {form.stop_type === "atr_trailing" && (
              <>
                <ParamInput
                  label="ATR 倍数"
                  hint="止损 = 入场价 - ATR × 倍数，范围 [0.5, 4.0]"
                  value={form.atr_mult}
                  step={0.1}
                  min={0.5}
                  max={4.0}
                  onChange={(v) => update("atr_mult", v)}
                />
                <ParamInput
                  label="移动止损激活阈值"
                  hint="价格涨多少后激活追踪，范围 [0.01, 0.10]"
                  value={form.trailing_activation}
                  step={0.005}
                  min={0.01}
                  max={0.10}
                  isPercent
                  onChange={(v) => update("trailing_activation", v)}
                />
                <ParamInput
                  label="移动止损回撤比例"
                  hint="从最高点回撤多少触发，范围 [0.01, 0.08]"
                  value={form.trailing_drawback}
                  step={0.005}
                  min={0.01}
                  max={0.08}
                  isPercent
                  onChange={(v) => update("trailing_drawback", v)}
                />
                <ParamInput
                  label="最小止损比例"
                  hint="防止 ATR 过小止损太紧，范围 [0.005, 0.03]"
                  value={form.min_stop_pct}
                  step={0.005}
                  min={0.005}
                  max={0.03}
                  isPercent
                  onChange={(v) => update("min_stop_pct", v)}
                />
              </>
            )}

            {/* 区间突破参数 */}
            {form.stop_type === "range_breakout" && (
              <ParamInput
                label="区间突破止损比例"
                hint="突破入场价多少触发，范围 [0.02, 0.10]"
                value={form.range_breakout_pct}
                step={0.005}
                min={0.02}
                max={0.10}
                isPercent
                onChange={(v) => update("range_breakout_pct", v)}
              />
            )}

            {/* 时间止损（非 none 类型显示） */}
            {form.stop_type !== "none" && (
              <ParamInput
                label="时间止损 K 线数"
                hint="持仓多少根 K 线后强制平仓，0 = 不启用"
                value={form.max_bars}
                step={5}
                min={0}
                max={200}
                isInt
                onChange={(v) => update("max_bars", v)}
              />
            )}

            {/* 按钮组：AI 优化 + 保存 */}
            <div className="flex gap-2">
              <Button
                onClick={handleAutoOptimize}
                disabled={optimizing || saving}
                variant="outline"
                className="flex-1"
                size="sm"
              >
                {optimizing ? (
                  <>
                    <Loader2 className="mr-2 size-3.5 animate-spin" />
                    AI 分析中...
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 size-3.5" />
                    AI 自动优化
                  </>
                )}
              </Button>
              <Button onClick={handleSave} disabled={saving || optimizing} className="flex-1" size="sm">
                {saving ? (
                  <>
                    <Loader2 className="mr-2 size-3.5 animate-spin" />
                    保存中...
                  </>
                ) : (
                  <>
                    <Save className="mr-2 size-3.5" />
                    保存配置
                  </>
                )}
              </Button>
            </div>
          </div>
        )}

        {!editingType && (
          <p className="text-center text-sm text-muted-foreground py-4">
            选择策略类型后编辑止损参数
          </p>
        )}

        <p className="text-xs text-muted-foreground">
          参数会自动限制在安全范围内。保存后立即生效，下次策略创建时使用新配置。
        </p>
      </CardContent>
    </Card>
  )
}

function ParamInput({
  label,
  hint,
  value,
  step,
  min,
  max,
  isPercent = false,
  isInt = false,
  onChange,
}: {
  label: string
  hint?: string
  value: number
  step: number
  min: number
  max: number
  isPercent?: boolean
  isInt?: boolean
  onChange: (v: number) => void
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Input
        type="number"
        value={isPercent ? value * 100 : value}
        step={isPercent ? step * 100 : step}
        min={isPercent ? min * 100 : min}
        max={isPercent ? max * 100 : max}
        onChange={(e) => {
          const raw = parseFloat(e.target.value)
          const val = isPercent ? raw / 100 : raw
          onChange(isInt ? Math.round(val) : val)
        }}
        className="h-8"
      />
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}
