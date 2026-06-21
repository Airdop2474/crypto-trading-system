# 前后端差距报告 · 修复总结

> 修复日期：2026-06-22
> 对应报告：`frontend-backend-gap-analysis-2026-06-22.md`（核查见 `*-verification.md`）
> 验证：`npx tsc --noEmit` 通过 + `npx next build` 成功（8 路由全静态生成）

---

## 修复范围

按报告 P0/P1 优先级，本次共完成 **6 项修复**，覆盖报告所列全部 P0 与 P1 项（除 P1 第 6 项订单分页需后端配合暴露 limit 参数，留待后续）。

---

## 修复明细

### P0-1 · 建立 `/agent` AI 分析页面 ✅

**报告原文**：建立 `/agent` AI 分析页面 — 调用 `POST /agent/analyze`，展示 5 种分析类型结果

**实施**：
- `frontend/app/agent/page.tsx` — 主页面，组合三个 section
- `frontend/components/agent/analyze-trigger.tsx` — 5 种分析类型卡片（回测解读 / 交易归因 / 风险清单 / 参数敏感性 / 周报复盘），点击触发 `POST /agent/analyze`，loading toast + 成功/失败 toast
- `frontend/components/agent/analyze-result.tsx` — 结构化展示 `analysis` / `reasoning` / `recommendation` / `risks[]`，含置信度徽章与"需人工确认"徽章
- `frontend/components/agent/audit-logs.tsx` — 审计日志表（30s 自动刷新），调用 `GET /agent/audit-logs`
- `frontend/components/agent/adoption-card.tsx` — 三张统计卡（调用次数 / 采纳次数 / 采纳率），调用 `GET /agent/adoption-rate`
- `frontend/lib/api.ts` 新增 `runAgentAnalysis` / `getAgentAuditLogs` / `getAgentAdoptionRate` / `getHealthDetailed`
- `frontend/lib/types.ts` 新增 `AgentTask` / `AgentAnalysisResult` / `AgentAuditLogEntry` / `AgentAdoptionRate`
- `frontend/components/app-sidebar.tsx` + `top-bar.tsx` 加 `/agent` 路由入口

### P0-2 · 修复 `getMultiStrategy` 类型定义 ✅

**报告原文**：修复 `getMultiStrategy` 类型定义，添加详情类型

**实施**：
- `frontend/lib/types.ts` 新增 `MultiStrategyResult`（含 `symbol` / `statistics` / `trade_history` / `signals` / `open_lots` / `realized_pnl` / `closed_trades`）+ 配套 `StrategyStatistics` / `BrokerOrder` / `ClosedTrade` / `StrategySignal`
- 类型严格对齐后端 `src/execution/paper_trading_runner.py::_build_result` 与 `src/execution/paper_broker.py::get_statistics` 的实际返回结构
- `frontend/lib/api.ts` 第 96 行 `Promise<unknown>` → `Promise<MultiStrategyResult>`

### P0-3 · 统一策略标签映射 ✅

**报告原文**：统一策略标签映射，覆盖全部 8 种策略

**实施**：
- 新建 `frontend/lib/strategy-meta.ts` — 全部 8 种策略（grid / rsi / ma / buyhold / donchian / structure / supertrend / reversal）的标签、配色、图标统一定义
- 提供 `parseStrategyType(strategyId)` 从 `grid-btc-usdt` 解析出类型
- 提供 `getStrategyLabelColor()` 与 `getStrategyLabelIcon()` 两个便捷函数
- `multi-strategy-panel.tsx` 删除局部 3 项硬编码 `STRATEGY_LABELS`，改用 `getStrategyLabelColor`
- `strategy-performance.tsx` 删除局部 8 项 `STRATEGY_META`，改用 `getStrategyLabelIcon`
- 现在两处来源统一，新增策略只需在 `strategy-meta.ts` 改一处

### P1-4 · 暗色模式切换 UI（含 Provider 与 light 主题） ✅

**报告原文**：添加暗色模式切换 UI（依赖已装，只需加按钮）
**核查修正**：实际还需补 `ThemeProvider` 与 light 主题 CSS 变量

**实施**：
- `frontend/app/globals.css` — 原"统一深色"拆为双套：`:root` 浅色 + `.dark` 深色（深色与原配色完全一致，保留"交易终端"调性）
- 新建 `frontend/components/theme-provider.tsx` — 包裹 `next-themes`
- 新建 `frontend/components/theme-toggle.tsx` — 深/浅/系统三态循环切换按钮（避开 base-ui Trigger 的 `render` prop 与 shadcn 风格 `asChild` 不兼容的问题）
- `frontend/app/layout.tsx` — 挂 `<ThemeProvider attribute="class" defaultTheme="dark" enableSystem disableTransitionOnChange>`，`<html>` 加 `suppressHydrationWarning`，`viewport.colorScheme` 改为 `'dark light'`

### P1-5 · WebSocket 断连 toast 通知 ✅

**报告原文**：WebSocket 断连时显示 toast + 重连进度

**实施**：
- `frontend/hooks/use-tickers-ws.ts` —
  - `onclose` 时若"曾连上过"且未弹过 toast，弹 `toast.warning("实时行情连接断开，正在尝试重连（已切换到 REST 回退）", { duration: Infinity })`
  - `onopen` 重连成功时 `toast.success("实时行情已恢复连接", { id })` 替换原 toast
  - 组件卸载时 `toast.dismiss()` 主动清理，避免悬挂
- 仅在"曾连上过"后弹，避免首屏后端未起时刷屏

### P1-6 · 修正侧栏"实盘"误导文案 ✅

**报告原文**（第 5 节）：侧栏显示"实盘"，后端明确是 Paper Trading 模式

**实施**：
- `frontend/components/app-sidebar.tsx:71` — `"主账户 · 实盘"` → `"主账户 · 模拟盘"`

---

## 顺手修（非报告项）

- `frontend/lib/mock-data.ts` — 3 处 `mockPositions` 缺 `leverage` / `liquidationPrice` 字段（与 `Position` 接口不一致，会让 `next build` 类型检查失败），补齐 `leverage: 1, liquidationPrice: 0`

---

## 未做项

| 报告项 | 原因 |
|--------|------|
| P1-6 订单分页 / 加载更多 | 需后端 `GET /orders` 暴露 `limit` / `offset` 参数，前端再加分页控件。建议作为下一次后端 + 前端协同改动 |
| P2 `/system` 系统状态页 | P2 优先级，且 `getHealthDetailed` 已封装，后续直接建页面即可 |
| P2 `/settings` 设置页 | P2 优先级 |
| P2 数据导出 CSV | P2 优先级 |
| P2 策略详情页（点击卡片进入） | P2 优先级，需为 `/grid/[id]` 与 `/price-action/[id]` 建动态路由 |

---

## 验证

```bash
$ cd frontend && npx tsc --noEmit
# 仅 0 个新增错误（mock-data 历史遗留已顺手修）

$ cd frontend && npx next build
✓ Compiled successfully in 4.3s
✓ Finished TypeScript in 7.6s
✓ Generating static pages (9/9)

Route (app)
├ ○ /
├ ○ /agent         ← 新增
├ ○ /analytics
├ ○ /grid
├ ○ /orders
├ ○ /positions
└ ○ /price-action
```

---

## 文件清单

**新增**（8 个）：
- `frontend/app/agent/page.tsx`
- `frontend/components/agent/analyze-trigger.tsx`
- `frontend/components/agent/analyze-result.tsx`
- `frontend/components/agent/audit-logs.tsx`
- `frontend/components/agent/adoption-card.tsx`
- `frontend/components/theme-provider.tsx`
- `frontend/components/theme-toggle.tsx`
- `frontend/lib/strategy-meta.ts`

**修改**（9 个）：
- `frontend/app/globals.css`（拆 light/dark 双套变量）
- `frontend/app/layout.tsx`（挂 ThemeProvider + suppressHydrationWarning）
- `frontend/lib/api.ts`（4 个新方法 + `getMultiStrategy` 类型修复）
- `frontend/lib/types.ts`（10+ 个新类型）
- `frontend/lib/mock-data.ts`（补 Position 缺失字段）
- `frontend/components/app-sidebar.tsx`（"实盘"→"模拟盘" + `/agent` 入口）
- `frontend/components/top-bar.tsx`（`/agent` 标题 + 主题切换按钮）
- `frontend/components/overview/multi-strategy-panel.tsx`（共用映射）
- `frontend/components/overview/strategy-performance.tsx`（共用映射）
- `frontend/hooks/use-tickers-ws.ts`（断连 toast）
