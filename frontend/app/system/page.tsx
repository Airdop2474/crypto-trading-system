"use client"

import { useEffect, useState } from "react"
import useSWR from "swr"
import { toast } from "sonner"
import {
  Activity,
  Database,
  HardDrive,
  OctagonAlert,
  RadioTower,
  RefreshCw,
  Server,
  Trash2,
  Users,
  Zap,
} from "lucide-react"
import { api } from "@/lib/api"
import { fmtNum } from "@/lib/format"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ApiError } from "@/components/api-error"
import { ModeControls } from "@/components/system/mode-controls"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"

const REFRESH_INTERVAL = 5_000  // 5s 自动刷新

export default function SystemPage() {
  const { data, error, isLoading, mutate } = useSWR(
    "health-detailed",
    api.getHealthDetailed,
    { revalidateOnFocus: false, refreshInterval: REFRESH_INTERVAL },
  )

  // 上次更新时间（用于显示"X 秒前更新"）
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [stopDialogOpen, setStopDialogOpen] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [cleanupDialogOpen, setCleanupDialogOpen] = useState(false)
  const [cleaning, setCleaning] = useState(false)
  const [cleanupScope, setCleanupScope] = useState<"all" | "runs" | "evolutions">("all")
  const [keepLatest, setKeepLatest] = useState(true)
  useEffect(() => {
    if (data) setUpdatedAt(new Date())
  }, [data])

  // 触发后端重建 Paper Trading state
  const handleRebuildState = async () => {
    setRefreshing(true)
    const toastId = toast.loading("正在重建 Paper Trading 引擎…")
    try {
      // 直接调 fetch（api.ts 未封装 admin 端点）
      const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"
      const API_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN || ""
      const res = await fetch(`${API_BASE}/admin/refresh-state`, {
        method: "POST",
        headers: { "X-API-Token": API_TOKEN },
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const d = await res.json()
      toast.success("引擎已重建，下次请求将使用新数据", { id: toastId })
      // 主动刷新本页 + 触发其他 SWR key 失效
      mutate()
    } catch (e) {
      const msg = e instanceof Error ? e.message : "未知错误"
      toast.error("重建失败", { id: toastId, description: msg })
    } finally {
      setRefreshing(false)
    }
  }

  // 全局急停
  const handleEmergencyStop = async () => {
    setStopping(true)
    const toastId = toast.loading("正在触发全局急停…")
    try {
      const result = await api.emergencyStop()
      toast.success("全局急停已触发", {
        id: toastId,
        description: `${result.previous_state} → STOPPED。所有策略交易已停止，需通过 reset() 恢复。`,
      })
      setStopDialogOpen(false)
      mutate()
    } catch (e) {
      const msg = e instanceof Error ? e.message : "未知错误"
      toast.error("急停失败", { id: toastId, description: msg })
    } finally {
      setStopping(false)
    }
  }

  // 清理历史数据
  const handleCleanup = async () => {
    setCleaning(true)
    const toastId = toast.loading("正在清理历史数据…")
    try {
      const result = await api.cleanupData(cleanupScope, keepLatest)
      const parts: string[] = []
      if (result.runs_deleted > 0) parts.push(`运行记录 ${result.runs_deleted} 条`)
      if (result.evolutions_deleted > 0) parts.push(`进化记录 ${result.evolutions_deleted} 条`)
      if (result.audit_deleted > 0) parts.push(`审计日志 ${result.audit_deleted} 条`)
      const summary = parts.length > 0 ? `已删除：${parts.join("、")}` : "没有需要清理的数据"
      toast.success("数据清理完成", { id: toastId, description: summary })
      setCleanupDialogOpen(false)
    } catch (e) {
      const msg = e instanceof Error ? e.message : "未知错误"
      toast.error("清理失败", { id: toastId, description: msg })
    } finally {
      setCleaning(false)
    }
  }

  return (
    <div className="flex flex-col gap-4 pb-16 md:pb-0">
      {/* 顶部状态条 */}
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <Server className="size-4 text-primary" />
            系统状态
          </CardTitle>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            {updatedAt ? (
              <span>更新于 {updatedAt.toLocaleTimeString("zh-CN", { hour12: false })}</span>
            ) : null}
            <Badge variant="outline" className="text-xs">
              <Zap className="mr-1 size-3" />
              {REFRESH_INTERVAL / 1000}s 自动刷新
            </Badge>
            <Button
              variant="outline"
              size="sm"
              className="h-7 gap-1.5 text-xs"
              onClick={handleRebuildState}
              disabled={refreshing}
            >
              <RefreshCw className={cn("size-3", refreshing && "animate-spin")} />
              {refreshing ? "重建中…" : "重建引擎"}
            </Button>
            <Button
              variant="destructive"
              size="sm"
              className="h-7 gap-1.5 text-xs"
              onClick={() => setStopDialogOpen(true)}
            >
              <OctagonAlert className="size-3" />
              全局急停
            </Button>
          </div>
        </CardHeader>
      </Card>

      {error ? (
        <ApiError
          error={error}
          onRetry={() => mutate()}
          title="系统状态加载失败"
          minHeight={200}
        />
      ) : (
        <>
          {/* 整体状态 */}
          <Card>
            <CardContent className="flex items-center gap-3 p-4">
              {isLoading || !data ? (
                <>
                  <div className="size-3 animate-pulse rounded-full bg-muted" />
                  <span className="text-sm text-muted-foreground">加载中…</span>
                </>
              ) : (
                <>
                  <div
                    className={cn(
                      "size-3 rounded-full",
                      data.status === "ok" ? "bg-success" : "bg-destructive",
                    )}
                  />
                  <span className="text-sm font-medium">
                    {data.status === "ok" ? "服务运行正常" : "服务异常"}
                  </span>
                </>
              )}
            </CardContent>
          </Card>

          {/* 4 张状态卡 */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {/* WebSocket 状态 */}
            <StatusCard
              title="WebSocket 行情"
              icon={RadioTower}
              loading={isLoading || !data}
              ok={data?.ws_connected ?? false}
              okLabel="已连接"
              failLabel="断开"
              detail={
                data
                  ? `Binance 实时行情推送${data.ws_connected ? "正常" : "已断开，前端回退 REST 轮询"}`
                  : undefined
              }
            />

            {/* WS 客户端数 */}
            <MetricCard
              title="WS 客户端数"
              icon={Users}
              value={isLoading || !data ? "—" : String(data.ws_clients)}
              detail={`当前订阅行情推送的前端连接数（上限 50）`}
              loading={isLoading || !data}
            />

            {/* 缓存后端 */}
            <StatusCard
              title="缓存后端"
              icon={Database}
              loading={isLoading || !data}
              ok={data?.cache_available ?? false}
              okLabel={data?.cache_backend ?? "—"}
              failLabel={data?.cache_backend ?? "—"}
              detail={
                data
                  ? data.cache_available
                    ? "Redis 可用，缓存层正常工作"
                    : "Redis 不可用，已回退到内存缓存"
                  : undefined
              }
            />

            {/* 缓存可用性 */}
            <StatusCard
              title="缓存可用性"
              icon={Activity}
              loading={isLoading || !data}
              ok={data?.cache_available ?? false}
              okLabel="ping 成功"
              failLabel="ping 失败"
              detail={
                data
                  ? data.cache_available
                    ? "缓存读写正常"
                    : "缓存读写异常，所有操作退化为直读"
                  : undefined
              }
            />
          </div>

          {/* 运行模式控制 */}
          <ModeControls />

          {/* 提示卡片 */}
          {data && !data.ws_connected ? (
            <Card className="border-warning/30 bg-warning/5">
              <CardContent className="flex items-start gap-3 p-4">
                <RadioTower className="mt-0.5 size-5 shrink-0 text-warning" />
                <div className="space-y-1">
                  <p className="text-sm font-medium text-warning">WebSocket 行情断开</p>
                  <p className="text-xs text-muted-foreground">
                    后端无法连接 Binance 实时行情推送。前端已自动回退到 REST 轮询（10 秒一次）。
                    请检查：网络出口、Binance API 限流、或服务器时间是否同步。
                  </p>
                </div>
              </CardContent>
            </Card>
          ) : null}

          {data && !data.cache_available ? (
            <Card className="border-warning/30 bg-warning/5">
              <CardContent className="flex items-start gap-3 p-4">
                <Database className="mt-0.5 size-5 shrink-0 text-warning" />
                <div className="space-y-1">
                  <p className="text-sm font-medium text-warning">缓存不可用</p>
                  <p className="text-xs text-muted-foreground">
                    Redis 连接失败，已回退到内存缓存。多 worker 部署下会出现缓存不共享。
                    请检查 Redis 服务是否运行、<code className="font-mono">REDIS_URL</code> 是否正确。
                  </p>
                </div>
              </CardContent>
            </Card>
          ) : null}

          {/* 运维提示 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">运维提示</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs text-muted-foreground">
              <p>
                · 本页每 {REFRESH_INTERVAL / 1000} 秒自动刷新，无需手动操作
              </p>
              <p>
                · WS 客户端数 = 当前订阅 <code className="font-mono">/ws/tickers</code> 的前端连接数，超过 50 会被拒绝
              </p>
              <p>
                · 缓存后端显示 <code className="font-mono">redis</code> 表示正常，<code className="font-mono">memory</code> 表示回退
              </p>
              <p>
                · <strong className="text-foreground">重建引擎</strong> 按钮：清空后端 Paper Trading 缓存，下次请求重跑（限 2 次/分钟）。数据源更新或配置变更后使用，不必重启服务
              </p>
              <p>
                · <strong className="text-destructive">全局急停</strong> 按钮：立即停止所有策略交易，RiskManager 进入 STOPPED 状态（限 5 次/分钟）。恢复需调用 reset()
              </p>
            </CardContent>
          </Card>
        </>
      )}

      {/* 数据管理 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <HardDrive className="size-4 text-primary" />
            数据管理
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-muted-foreground">
            清理历史运行记录、进化记录和审计日志，释放存储空间。此操作不可逆，请谨慎使用。
          </p>
          <Button
            variant="destructive"
            size="sm"
            className="h-7 gap-1.5 text-xs"
            onClick={() => setCleanupDialogOpen(true)}
          >
            <Trash2 className="size-3" />
            清理历史数据
          </Button>
        </CardContent>
      </Card>

      {/* 急停确认对话框 */}
      <Dialog open={stopDialogOpen} onOpenChange={setStopDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-destructive">
              <OctagonAlert className="size-5" />
              确认全局急停
            </DialogTitle>
            <DialogDescription>
              此操作将立即停止所有策略的交易，RiskManager 状态切换为 STOPPED。
              所有未成交挂单将被保留，不会自动取消。恢复交易需要通过 reset() 重置风控状态。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setStopDialogOpen(false)} disabled={stopping}>
              取消
            </Button>
            <Button variant="destructive" onClick={handleEmergencyStop} disabled={stopping}>
              {stopping ? "急停中…" : "确认急停"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 数据清理确认对话框 */}
      <Dialog open={cleanupDialogOpen} onOpenChange={setCleanupDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-destructive">
              <Trash2 className="size-5" />
              确认清理历史数据
            </DialogTitle>
            <DialogDescription>
              此操作将永久删除指定的历史数据，无法恢复。请确认清理范围后继续。
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-foreground">清理范围</label>
              <Select
                value={cleanupScope}
                onValueChange={(v) => v && setCleanupScope(v as "all" | "runs" | "evolutions")}
                disabled={cleaning}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部数据</SelectItem>
                  <SelectItem value="runs">仅运行记录</SelectItem>
                  <SelectItem value="evolutions">仅进化记录</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={keepLatest}
                onChange={(e) => setKeepLatest(e.target.checked)}
                disabled={cleaning}
                className="size-4 rounded border-border accent-primary"
              />
              保留最近 7 天数据
            </label>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setCleanupDialogOpen(false)} disabled={cleaning}>
              取消
            </Button>
            <Button variant="destructive" onClick={handleCleanup} disabled={cleaning}>
              {cleaning ? "清理中…" : "确认清理"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function StatusCard({
  title,
  icon: Icon,
  loading,
  ok,
  okLabel,
  failLabel,
  detail,
}: {
  title: string
  icon: typeof Activity
  loading: boolean
  ok: boolean
  okLabel: string
  failLabel: string
  detail?: string
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-2 p-4">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Icon className="size-3.5" />
            {title}
          </span>
          {loading ? (
            <div className="size-2 animate-pulse rounded-full bg-muted" />
          ) : (
            <span
              className={cn(
                "size-2 rounded-full",
                ok ? "bg-success" : "bg-destructive",
              )}
            />
          )}
        </div>
        <p className={cn(
          "font-mono text-lg font-semibold tabular-nums",
          loading ? "text-muted-foreground" : ok ? "text-success" : "text-destructive",
        )}>
          {loading ? "—" : ok ? okLabel : failLabel}
        </p>
        {detail ? (
          <p className="text-[11px] leading-relaxed text-muted-foreground">{detail}</p>
        ) : null}
      </CardContent>
    </Card>
  )
}

function MetricCard({
  title,
  icon: Icon,
  value,
  detail,
  loading,
}: {
  title: string
  icon: typeof Activity
  value: string
  detail?: string
  loading: boolean
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-2 p-4">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Icon className="size-3.5" />
            {title}
          </span>
        </div>
        <p className="font-mono text-lg font-semibold tabular-nums">
          {loading ? "—" : value}
        </p>
        {detail ? (
          <p className="text-[11px] leading-relaxed text-muted-foreground">{detail}</p>
        ) : null}
      </CardContent>
    </Card>
  )
}
