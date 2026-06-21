# 前端系统审查报告 — QuantDesk 加密交易终端

**日期**: 2026-06-20
**审查范围**: `frontend/` 全部源码（55 文件，约 4,994 行）
**技术栈**: Next.js 16 + React 19 + TypeScript 5.7 + Tailwind v4 + shadcn/ui + SWR + Recharts

---

## 执行摘要

前端是一个单暗色主题的加密货币量化交易管理终端（QuantDesk），架构选型现代且合理——Next.js App Router、SWR 数据获取、WebSocket 实时行情、Recharts 图表。代码整体 TypeScript 纪律良好，组件拆分清晰。

但存在一个**系统性短板**：几乎所有数据获取组件只处理了 loading 状态而忽略了 error 状态，API 调用失败时用户看到的是空白或零值，无法区分"没有数据"和"数据加载失败"。对于交易系统这是高风险问题。此外，`NEXT_PUBLIC_API_TOKEN` 暴露在客户端包中，以及 `positions-table.tsx` 表头与数据列不对齐，是需要优先修复的问题。

整体评估：**架构 B+，实现质量 B，生产就绪度 C+**。修复 5 项 CRITICAL/HIGH 后可达到上线标准。

---

## 1. 项目结构概览

### 1.1 文件统计

| 分类 | 文件数 | 行数 | 说明 |
|------|-------|------|------|
| 页面（app/） | 7 | 315 | 6 个路由页面 + 1 个根布局 |
| 业务组件（components/） | 16 | 1,375 | Overview/Grid/Orders/Positions/PriceAction/Analytics |
| UI 基础组件（components/ui/） | 18 | 1,763 | shadcn/ui 组件（Button/Card/Dialog/Table 等） |
| Hooks | 2 | 173 | useStrategies + useTickersWs |
| Lib 工具层 | 5 | 507 | API 客户端、类型、格式化、Mock、工具函数 |
| 配置文件 | 6 | 155 | next.config/tsconfig/postcss/package.json 等 |
| **合计** | **55** | **~4,994** | |

### 1.2 路由结构

```
/                    Overview 仪表盘（总览）
/grid                网格策略管理
/orders              订单列表
/positions           持仓与资产
/analytics           PnL 分析
/price-action        Price Action 策略（Donchian/Structure/SuperTrend/Reversal）
```

全部为静态路由，无动态路由 `[id]`。无 API Routes（后端独立部署 FastAPI）。无 `middleware.ts`。无 `loading.tsx`、`error.tsx`、`not-found.tsx` 等 App Router 约定文件。

### 1.3 技术选型评价

| 选择 | 评价 |
|------|------|
| Next.js 16 App Router | 合理，服务端/客户端组件分离清晰 |
| React 19 | 最新稳定版，支持新特性 |
| TypeScript 5.7 strict | 严格模式开启，编译期类型安全有保障 |
| Tailwind v4 + CSS 变量主题 | 现代方案，无 tailwind.config 文件（v4 通过 CSS 配置） |
| shadcn/ui + @base-ui/react | 高质量无头组件库，可定制性好 |
| SWR 2.x | 适合仪表盘场景的 stale-while-revalidate 策略 |
| Recharts 3.x | React 原生图表库，功能够用 |
| next-themes | 已安装但仅配置了暗色主题，未启用主题切换 |
| sonner | 轻量 toast 通知库 |

---

## 2. 架构与代码质量

### 2.1 组件架构 — 评分: B+

**优点**:

组件拆分粒度合理，遵循"页面 → 业务组件 → UI 基础组件"三层架构。根布局（`layout.tsx`）的包装层次 `ErrorBoundary > SWRProvider > Shell > children` 设计清晰。Overview 页面的每个 widget 都独立包裹了 `<ErrorBoundary>`，实现了优秀的故障隔离——一个组件崩溃不会影响其他 widget。

`Shell` 组件统一处理桌面侧边栏（`AppSidebar`）、顶栏（`TopBar`）和移动端底部导航（`MobileNav`），响应式架构思路正确。

**问题**:

- Overview 页面做了 per-widget ErrorBoundary，但 Grid/Orders/Positions/Analytics/PriceAction 页面均无 ErrorBoundary 包裹，一个组件渲染异常会导致整个页面白屏。
- `app-sidebar.tsx` 和 `mobile-nav.tsx` 硬编码了用户信息（"T"、"Trader"、"Main account - Live"），应来自用户上下文或 API。
- 无 `<h1>` 页面标题——所有 6 个页面均缺少语义化的页面主标题，对屏幕阅读器和 SEO 都不友好。

### 2.2 TypeScript 纪律 — 评分: B+

**优点**:

`tsconfig.json` 开启了 `strict: true`，`next.config.mjs` 配置了 `ignoreBuildErrors: false`（类型错误会导致构建失败）。`lib/types.ts` 定义了完整的领域模型，所有 API 调用都有返回类型标注。`status-badge.tsx` 使用 `Record<StrategyStatus, ...>` 确保所有枚举值都被覆盖，新增状态时 TypeScript 会在编译期报错——这是很好的防御性编程。

**问题**:

- `api.ts` 的 `getMultiStrategy()` 返回 `Promise<unknown>`（第 97 行），完全丧失类型安全
- `create-grid-dialog.tsx` 的 `updateField` 参数类型为 `key: string`，应改为 `keyof typeof form`
- `status-badge.tsx` 的 `SideBadge` 使用内联类型 `{ side: "buy" | "sell" }` 而非导入 `Side` 类型
- `MultiStrategySlot` 使用 snake_case（`strategy_id`、`realized_pnl`）而 `MultiStrategyDetail` 使用 camelCase，命名不一致暴露了后端 API 两种格式的直接映射

### 2.3 数据获取层 — 评分: B

**SWR 配置（`swr-provider.tsx`）**:

全局配置合理——30 秒自动刷新、错误重试（3 次）、去重、stale-while-revalidate。Fetcher 实现了 `AbortController` 超时（10 秒）和错误响应体解析，比 `api.ts` 的 `get<T>()` 更健壮。

**WebSocket（`use-tickers-ws.ts`）**:

实现质量高——指数退避重连、REST 轮询降级、`useEffect` 清理逻辑正确（关闭 WS、清除定时器、设置 unmounted 标记防止内存泄漏）。认证消息在 `ws.onopen` 后发送（符合前一轮审查报告的 R-05 修复建议）。

**API 客户端（`api.ts`）**:

`get<T>()` 泛型 helper 减少了样板代码。所有端点都有类型标注。`API_TOKEN` 通过 `X-API-Token` 请求头传递。

**问题**:

- `get<T>()` 无 `AbortController` 超时，直接调用时请求可能无限挂起
- 错误消息格式不统一：`api.ts` 抛出 `GET ${path} failed: ${status}` 而 `swr-provider.tsx` 使用不同的格式
- `getMultiStrategy` 返回 `unknown` 类型，调用方无法获得类型提示
- `id` 参数无输入校验，路径拼接 `${API_BASE}/strategies/${id}/status` 存在路径遍历风险
- `API_TOKEN` 默认为空字符串，未配置时静默发送无认证请求

---

## 3. 发现详表

### CRITICAL（3 项）

| # | 类别 | 位置 | 问题描述 | 建议 |
|---|------|------|---------|------|
| F-01 | 安全 | `api.ts` + `swr-provider.tsx` | **`NEXT_PUBLIC_API_TOKEN` 暴露在客户端包中**。所有 `NEXT_PUBLIC_` 前缀的环境变量会被 Next.js 内联到浏览器 JS bundle 中，任何人打开 DevTools 即可提取 API token。对于交易系统，这等于公开了全部 API 的控制权 | 将所有 API 调用通过 Next.js Route Handler（`app/api/`）代理，token 仅存在于服务端环境变量（不带 `NEXT_PUBLIC_` 前缀）。前端请求本地 `/api/*`，Route Handler 注入 token 后转发到后端 |
| F-02 | 可靠性 | 全局（除 overview/page.tsx 外） | **系统性 error 状态缺失**。Grid/Orders/Positions/Analytics/PriceAction 5 个页面以及大部分业务组件只处理了 `isLoading` 状态，完全忽略 SWR 返回的 `error`。API 失败时用户看到空白或零值数据——在交易场景中，"显示 0 持仓"和"持仓数据加载失败"是完全不同的含义 | 为每个 SWR 消费组件添加 error 状态 UI（至少显示错误提示 + 重试按钮）。考虑封装 `useApi` hook 统一处理 loading/error/data 三态 |
| F-03 | UI Bug | `components/positions/positions-table.tsx` | **表头与数据列不对齐**。表头定义了 10 列（含 Leverage、Liquidation Price），但表体每行只渲染 8 个 `TableCell`。这会导致列错位，用户在查看持仓数据时看到的是错误列对应关系——对于交易终端这是直接的误导 | 补齐缺失的 2 列数据渲染，或从表头移除对应列名 |

### HIGH（5 项）

| # | 类别 | 位置 | 问题描述 | 建议 |
|---|------|------|---------|------|
| F-04 | 安全 | `next.config.mjs` | **缺少 Content-Security-Policy 响应头**。现有安全头包含 X-Frame-Options/X-Content-Type-Options/Referrer-Policy（做得好），但缺少 CSP。CSP 是 XSS 防线的核心 | 添加 `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ${API_BASE} wss://...` |
| F-05 | 可靠性 | `hooks/use-tickers-ws.ts` | **WebSocket 连接状态竞态**。如果 `connect()` 被调用时旧 WS 仍在 CONNECTING 状态（既非 OPEN 也非 CLOSED），旧连接引用会被直接覆盖而不关闭，导致泄漏的 WebSocket 连接 | 在 `connect()` 开头检查 `wsRef.current` 状态，如果存在且未关闭则先调用 `close()` |
| F-06 | 架构 | `app/` 全局 | **缺少 App Router 约定文件**。无 `loading.tsx`（无法利用 Next.js 流式 Suspense）、无 `error.tsx`（无路由级错误 UI）、无 `not-found.tsx`（404 使用默认页） | 至少为每个路由添加 `error.tsx` 和 `loading.tsx`，利用 React Suspense 边界实现流式加载 |
| F-07 | 安全 | `hooks/use-tickers-ws.ts` | **WebSocket 未强制 wss:// 协议**。`toWsUrl()` 根据 `API_BASE` 的 http/https 前缀决定 ws/wss，但无生产环境强制 wss 的逻辑。如果 `NEXT_PUBLIC_API_BASE` 误配为 http，WebSocket 将以明文传输 | 在生产环境中强制使用 `wss://`，无论 `API_BASE` 协议如何 |
| F-08 | 质量 | 全局 | **无 ESLint 配置文件**。`package.json` 有 `lint` 脚本但项目根目录无 `.eslintrc.*` 或 `eslint.config.*`。代码规范完全依赖开发者自觉 | 创建 `eslint.config.mjs`，至少继承 `eslint-config-next`，启用 `@typescript-eslint` 规则 |

### MEDIUM（8 项）

| # | 类别 | 位置 | 问题描述 |
|---|------|------|---------|
| F-09 | 性能 | `components/positions/asset-allocation.tsx` | 饼图 `config` 对象在每次渲染时重建，应用 `useMemo` |
| F-10 | 性能 | `hooks/use-strategies.ts` | `setStatus` 函数未用 `useCallback` 包裹，每次渲染生成新引用导致子组件不必要的重渲染 |
| F-11 | 性能 | `components/orders/orders-table.tsx` | 无分页机制，48+ 条订单全量渲染。大数据集下性能会退化 |
| F-12 | 质量 | `lib/format.ts` | `fmtCompact` 对负数大值处理有 bug：`fmtCompact(-2_000_000_000)` 返回 `$-2000000000.00` 而非 `$-2.00B`；所有格式化函数无 `NaN`/`Infinity` 守卫 |
| F-13 | 质量 | `lib/mock-data.ts` | 201 行 mock 数据在有真实 API 后已成为死代码。`mockOrders` 在模块加载时即执行 `Array.from({length:48})` 计算 |
| F-14 | 可用性 | `components/strategy-controls.tsx` | "停止"按钮无确认对话框，点击即执行。交易策略的停止操作应有二次确认 |
| F-15 | 类型 | `lib/types.ts` | `MultiStrategySlot` 使用 snake_case 而其他类型使用 camelCase，命名不一致 |
| F-16 | 配置 | `app/layout.tsx` | `metadata.generator: 'v0.app'` 将构建工具信息泄露到生产 HTML `<meta>` 标签中 |

### LOW（5 项）

| # | 问题 |
|---|------|
| F-17 | 侧边栏和底部导航无 `aria-current` 属性标记活跃链接 |
| F-18 | 加载骨架屏无 `aria-busy="true"` 或 `role="progressbar"` |
| F-19 | `grid-visual.tsx` 的网格可视化无 `role="img"` 和 `aria-label` |
| F-20 | `use-tickers-ws.ts` 的 REST 降级轮询定时器在 WS 已连接时仍每 10 秒触发条件检查 |
| F-21 | `top-bar.tsx` 的 `t.symbol.split("/")[0]` 在 symbol 不含 "/" 时会崩溃 |

---

## 4. 亮点

审查中也发现了多个值得肯定的设计：

1. **Overview 页面的 per-widget ErrorBoundary**（`app/page.tsx`）——每个 widget 独立包裹，故障隔离做得很好，是其他页面应该学习的模式

2. **WebSocket 重连机制**（`use-tickers-ws.ts`）——指数退避、REST 降级、完整的清理逻辑，是项目中实现质量最高的 hook

3. **Grid 创建表单**（`create-grid-dialog.tsx`）——表单验证完整（价格范围、网格数量、正数投资额），实时预览每格利润率，提交按钮有 loading 状态，成功后自动重置表单

4. **策略状态乐观更新**（`use-strategies.ts`）——先 mutate 后调 API，失败时回滚，toast 通知用户，是标准的乐观 UI 模式

5. **TypeScript strict 模式 + 构建失败**——`tsconfig` strict + `next.config` 不忽略 TS 错误，保证了编译期类型安全

6. **安全响应头**（`next.config.mjs`）——X-Frame-Options/X-Content-Type-Options/Referrer-Policy/X-DNS-Prefetch-Control 已配置

---

## 5. 页面质量评分

| 页面 | 结构 | 数据获取 | 错误处理 | 加载状态 | 可访问性 | 综合 |
|------|------|---------|---------|---------|---------|------|
| Layout | A | A | B+ | N/A | B | A- |
| Overview (/) | A | A | A | B+ | C+ | B+ |
| Grid (/grid) | B+ | A- | D | B+ | C | B- |
| Orders (/orders) | B+ | B+ | D | B | C | C+ |
| Positions (/positions) | B+ | A- | D | B+ | C | C+ |
| Analytics (/analytics) | B+ | B+ | D | B+ | C | C+ |
| Price Action (/price-action) | B+ | A- | D+ | B+ | C | B- |

Overview 页面明显优于其他页面——它是唯一实现了 per-widget ErrorBoundary 和全面 error 状态处理的页面。其他页面在错误处理维度均为 D 级。

---

## 6. 行动清单

### P0 — 上线前必须完成

| # | 行动 | 负责方 | 预估 |
|---|------|--------|------|
| 1 | 消除 `NEXT_PUBLIC_API_TOKEN`：创建 Next.js Route Handler 代理层，token 仅存于服务端 | 前端 + 后端 | 3-4 h |
| 2 | 为所有 SWR 消费组件添加 error 状态 UI（错误提示 + 重试） | 前端工程师 | 2-3 h |
| 3 | 修复 `positions-table.tsx` 表头与数据列不对齐的 bug | 前端工程师 | 15 min |

### P1 — Sprint 内完成

| # | 行动 | 负责方 | 预估 |
|---|------|--------|------|
| 4 | 添加 Content-Security-Policy 响应头 | 前端/安全 | 30 min |
| 5 | 修复 WebSocket 连接状态竞态（connect 前先关闭旧连接） | 前端工程师 | 15 min |
| 6 | 为每个路由添加 `error.tsx` + `loading.tsx` | 前端工程师 | 1 h |
| 7 | 生产环境强制 wss:// WebSocket 协议 | 前端工程师 | 10 min |
| 8 | 创建 ESLint 配置文件 | 前端工程师 | 30 min |
| 9 | "停止策略"操作添加确认对话框 | 前端工程师 | 20 min |

### P2 — 后续优化

| # | 行动 | 预估 |
|---|------|------|
| 10 | Orders 表格添加分页或虚拟滚动 | 1-2 h |
| 11 | 移除 `lib/mock-data.ts` 死代码 | 5 min |
| 12 | 修复 `fmtCompact` 负数 bug + 添加 NaN 守卫 | 15 min |
| 13 | `setStatus` 添加 `useCallback`，`asset-allocation` 添加 `useMemo` | 15 min |
| 14 | 补充可访问性（aria-current、aria-busy、aria-label、页面 h1） | 2 h |
| 15 | 统一 multi-strategy 类型的命名风格（全部 camelCase） | 30 min |

---

## 7. 结论

前端系统的架构选型和代码组织是成熟的——Next.js 16 App Router、TypeScript strict、SWR、shadcn/ui 的组合是当前 React 生态的最佳实践之一。组件拆分合理，WebSocket 实现质量高，Overview 页面的故障隔离设计值得推广到所有页面。

核心问题是**错误处理的系统性缺失**——5 个页面和大部分业务组件对 API 失败静默无视，这在交易场景中尤其危险。结合 `NEXT_PUBLIC_API_TOKEN` 的客户端暴露和 `positions-table` 的列错位 bug，建议修复 3 项 P0 后再进入上线评审。

预计 P0 修复工作量约 1 个工作日，P1 约 0.5 个工作日。

---

> 本报告基于 `frontend/` 目录全部 55 个源文件的逐项审查，覆盖 7 个页面、16 个业务组件、2 个 hooks、5 个 lib 模块和 6 个配置文件。
