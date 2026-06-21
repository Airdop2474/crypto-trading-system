# 前后端对比分析报告 · 准确性核查

> 核查日期：2026-06-22
> 被核查报告：`frontend-backend-gap-analysis-2026-06-22.md`
> 核查方式：逐项对照后端 `src/api/app.py`、`src/api/service.py` 与前端 `frontend/` 实际代码

---

## 核查结论：整体高度准确

报告共提出 6 大类、约 20 项具体声明，经逐项核查：

- **17 项完全准确**
- **2 项基本准确但表述略有偏差**（不影响结论）
- **1 项小遗漏**（不影响结论）

总体可信度高，可作为后续优化的依据。

---

## 逐项核查明细

### 1️⃣ 后端端点存在性 — ✅ 全部准确

| 报告声明 | 核查结果 |
|---------|---------|
| `POST /agent/analyze` 存在，支持 5 种分析 | ✅ `app.py:325`，`AnalyzeRequest.task` 为 `Literal["backtest", "trade_attribution", "risk_checklist", "param_sensitivity", "weekly_review"]`，5 种完全对应 |
| `GET /agent/audit-logs` 存在 | ✅ `app.py:377` |
| `GET /agent/adoption-rate` 存在 | ✅ `app.py:384` |
| `GET /health/detailed` 返回 WS 连接/缓存/客户端数 | ✅ `app.py:109`，返回 `ws_connected` / `ws_clients` / `cache_backend` / `cache_available` |
| 前端完全未对接上述端点 | ✅ `frontend/lib/api.ts` 无 `/agent/*` 与 `/health/detailed` 调用；`components/`、`app/`、`hooks/` 全目录搜索均无引用 |

### 2️⃣ 类型安全缺口 — ✅ 准确

| 报告声明 | 核查结果 |
|---------|---------|
| `api.ts:96` `getMultiStrategy` 返回 `Promise<unknown>` | ✅ 第 96 行确为 `getMultiStrategy: (id: string): Promise<unknown> => get(...)` |
| 后端 `/multi/strategy/{id}` 返回单策略完整结果 | ✅ `app.py:250` → `service.multi_strategy_result` |
| 前端完全没消费这个端点 | ✅ 全目录搜索 `getMultiStrategy` 无任何调用方（仅定义未使用） |

### 3️⃣ 页面功能深度 — ✅ 准确（含 1 处小遗漏）

| 页面 | 报告"缺失"声明 | 核查结果 |
|-----|--------------|---------|
| 总览 `/` | 无风险指标看板（回撤/夏普/波动率） | ✅ 准确。实际含 AccountCards/EquityChart/MarketWatch/ActiveStrategies/StrategyPerformance/MultiStrategyPanel，确无独立风险指标看板 |
| 网格 `/grid` | 无网格详情页 | ✅ 准确。`app/grid/` 下仅 `page.tsx`，无 `[id]` 动态路由 |
| 价格行为 `/price-action` | 无策略详情页 | ✅ 准确。`app/price-action/` 下仅 `page.tsx` |
| 持仓 `/positions` | 无平仓历史/交易时间线/盈亏分布 | ✅ 准确。页面仅 StatCards + PositionsTable + AssetAllocation + AssetsTable |
| 订单 `/orders` | 后端只返回最新 100 条，无分页 | ✅ 准确。`service.py:358` `orders(state, limit=100)` 默认 100；`app.py:221` 未暴露 limit 参数；`orders-table.tsx` 仅搜索+状态筛选，无分页控件 |
| 分析 `/analytics` | 无胜率趋势图/回撤曲线/相关性矩阵 | ✅ 准确。页面仅 CumulativePnl + DailyPnl + StrategyComparison |

> **小遗漏**：总览页报告"现有"一栏漏列了 `ActiveStrategies` 与 `MultiStrategyPanel` 两个组件，但不影响"无风险指标看板"的结论。

### 4️⃣ 缺失页面路由 — ✅ 准确

现有路由仅 6 个：`/`、`/grid`、`/price-action`、`/positions`、`/orders`、`/analytics`。
报告所列 `/agent`、`/risk`、`/system`、`/settings` 确实均不存在。

### 5️⃣ 代码质量问题 — ✅ 基本准确（含 1 处表述偏差）

| 报告声明 | 位置 | 核查结果 |
|---------|------|---------|
| 策略标签硬编码 3 个 | `multi-strategy-panel.tsx:17-21` | ✅ 准确。`STRATEGY_LABELS` 仅 grid/rsi/sma 三个，fallback 为 `bg-gray-500/20 text-gray-400` |
| 多策略页映射全 8 个 | `strategy-performance.tsx:22-31` | ✅ 准确。`STRATEGY_META` 覆盖 grid/rsi/sma/donchian/structure/supertrend/reversal/buyhold 全部 8 个 |
| `getMultiStrategy` 弱类型 | `api.ts:96` | ✅ 准确 |
| WebSocket 断连提示弱 | `market-watch.tsx:17-20` | ✅ 准确。仅 `size-2 rounded-full` 小圆点 + `title` 属性，无 toast/重连文本 |
| 侧栏显示"实盘" | `app-sidebar.tsx:71` | ✅ 准确。第 71 行 `<p>主账户 · 实盘</p>`，与后端 Paper Trading 模式不符 |
| 暗色模式无切换入口 | `layout.tsx` | ⚠️ **基本准确但表述偏差**：`next-themes@0.4.6` 确已安装（`package.json:18`），但 `layout.tsx` 根本未引入 `ThemeProvider`。报告 P1 第 5 条说"依赖已装，只需加按钮"——**实际还需先加 `ThemeProvider` 包裹**，不仅是加按钮 |
| 无数据导出 CSV | 所有页面 | ✅ 准确，未发现导出功能 |
| 订单无分页 | `orders-table.tsx` | ✅ 准确 |

### 6️⃣ 优化优先级建议 — ✅ 合理

P0/P1/P2 分级与上述核查一致，建议可直接采纳。唯一需修正的实施细节：

> P1 第 5 项"添加暗色模式切换 UI（依赖已装，只需加按钮）" → 应改为"需在 `layout.tsx` 引入 `ThemeProvider` 并添加切换按钮"。

---

## 汇总

| 类别 | 准确 | 基本准确 | 不准确 |
|------|-----|---------|-------|
| 后端端点（4 项） | 4 | 0 | 0 |
| 类型安全（2 项） | 2 | 0 | 0 |
| 页面功能深度（6 项） | 5 | 0 | 0（1 项小遗漏） |
| 缺失路由（4 项） | 4 | 0 | 0 |
| 代码质量问题（8 项） | 7 | 1 | 0 |
| **合计** | **22** | **1** | **0** |

**最终判断：报告内容真实可靠，可作为优化路线图的依据。** 唯一需修正的是"暗色模式只需加按钮"这一实施细节——实际还需补 `ThemeProvider`。
