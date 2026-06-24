"use client"

import { useState } from "react"
import { toast } from "sonner"
import { Send, Loader2, CheckCircle2, XCircle, Eye, EyeOff } from "lucide-react"
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
import type { TelegramConfig } from "@/lib/types"

export function TelegramConfigCard({ config }: { config: TelegramConfig | undefined }) {
  const [botToken, setBotToken] = useState("")
  const [chatId, setChatId] = useState(config?.chat_id ?? "")
  const [minLevel, setMinLevel] = useState(config?.min_level ?? "INFO")
  const [showToken, setShowToken] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)

  // 同步外部加载的 config
  const currentChatId = config?.chat_id ?? ""
  const currentMinLevel = config?.min_level ?? "INFO"
  const enabled = config?.enabled ?? false

  const handleSave = async () => {
    setSaving(true)
    try {
      const result = await api.saveTelegramConfig({
        bot_token: botToken, // 空字符串=不修改（后端会读已有值）；非空=更新
        chat_id: chatId || currentChatId,
        min_level: minLevel,
      })
      if (result.ok) {
        toast.success(result.message)
        setBotToken("") // 清空输入框，避免重复提交
      } else {
        toast.error(result.message || "保存失败")
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败")
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    try {
      const result = await api.testTelegram()
      if (result.ok) {
        toast.success(result.message)
      } else {
        toast.error(result.message)
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "测试失败")
    } finally {
      setTesting(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm font-medium">
            <Send className="size-4 text-primary" />
            Telegram 通知
          </span>
          {enabled ? (
            <Badge variant="default" className="bg-green-600 text-white">
              <CheckCircle2 className="mr-1 size-3" />
              已启用
            </Badge>
          ) : (
            <Badge variant="secondary">
              <XCircle className="mr-1 size-3" />
              未配置
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Bot Token */}
        <div className="space-y-2">
          <Label htmlFor="bot-token" className="text-sm font-medium">
            Bot Token
          </Label>
          <div className="flex items-center gap-2">
            <Input
              id="bot-token"
              type={showToken ? "text" : "password"}
              placeholder={
                config?.bot_token_set
                  ? `已设置（${config.bot_token_masked}）`
                  : "从 @BotFather 获取的 Bot Token"
              }
              value={botToken}
              onChange={(e) => setBotToken(e.target.value)}
              className="flex-1"
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => setShowToken(!showToken)}
              className="size-9 shrink-0"
            >
              {showToken ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            {config?.bot_token_set
              ? `当前 Token: ${config.bot_token_masked}（留空则不修改）`
              : "在 Telegram 中找 @BotFather，发送 /newbot 创建机器人后获取"}
          </p>
        </div>

        {/* Chat ID */}
        <div className="space-y-2">
          <Label htmlFor="chat-id" className="text-sm font-medium">
            Chat ID
          </Label>
          <Input
            id="chat-id"
            type="text"
            placeholder="如 123456789 或 -100xxxxxxxxxx"
            value={chatId || currentChatId}
            onChange={(e) => setChatId(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            私聊用个人 ID；群组用群 ID（以 -100 开头）。可向 @userinfobot 发消息获取
          </p>
        </div>

        {/* 最低通知级别 */}
        <div className="space-y-2">
          <Label className="text-sm font-medium">最低通知级别</Label>
          <Select
            value={minLevel || currentMinLevel}
            onValueChange={(v: string | null) => {
              if (v) setMinLevel(v)
            }}
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="INFO">
                <div className="flex flex-col">
                  <span>INFO - 全部通知</span>
                  <span className="text-xs text-muted-foreground">包括日常日报、运行状态</span>
                </div>
              </SelectItem>
              <SelectItem value="WARNING">
                <div className="flex flex-col">
                  <span>WARNING - 仅警告</span>
                  <span className="text-xs text-muted-foreground">闪崩保护、Heat 超阈值</span>
                </div>
              </SelectItem>
              <SelectItem value="CRITICAL">
                <div className="flex flex-col">
                  <span>CRITICAL - 仅紧急</span>
                  <span className="text-xs text-muted-foreground">急停触发、异常退出</span>
                </div>
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* 操作按钮 */}
        <div className="flex gap-2 pt-2">
          <Button
            onClick={handleSave}
            disabled={saving}
            className="flex-1"
          >
            {saving ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" />
                保存中...
              </>
            ) : (
              "保存配置"
            )}
          </Button>
          <Button
            onClick={handleTest}
            disabled={testing || !enabled}
            variant="outline"
            className="flex-1"
          >
            {testing ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" />
                发送中...
              </>
            ) : (
              <>
                <Send className="mr-2 size-4" />
                发送测试
              </>
            )}
          </Button>
        </div>

        {/* 状态提示 */}
        {!enabled && (
          <p className="rounded-md bg-muted p-2 text-xs text-muted-foreground">
            未配置 Token 时自动降级为纯日志模式，所有通知仅输出到日志文件，不会发送到 Telegram。
          </p>
        )}
      </CardContent>
    </Card>
  )
}
