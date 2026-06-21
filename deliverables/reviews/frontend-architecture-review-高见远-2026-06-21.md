## 前端系统架构审查 — 高见远

> 审查日期: 2026-06-21 | 源码阅读数: 54 个 .ts/.tsx 文件 | 审查范围: crypto-trading-system/frontend 完整前端

---

### 1. 总体架构评分 (82/100)

| 维度 | 得分 | 说明 |
|------|------|------|
| 数据流设计 | 18/20 | SWR + api 服务层边界清晰，但双 fetcher 路径有冗余 |
| 类型安全 | 17/20 | strict 模式，类型定义完整，但有 1 处 `unknown` 和表格结构不匹配 |
| 错误处理 | 15/20 | ErrorBoundary 分层到位，SWR error 传播正确，但 api.get() 缺少超时 |
| 加载/空态 | 16/20 | 大部分组件有 pulse skeleton，但 analytics 子组件未独立处理空态 |
| 代码规范 | 8/10 | 无 ESLint 配置，无测试 |
| 安全 | 8/10 | X-API-Token 已修复，安全响应头到位，但 .env.local 无示例 |

---

### 2. 🔴 CRITICAL（阻塞上线）

| # | 问题 | 文件:行 | 影响 | 建议 |
|---|------|---------|------|------|
| C1 | **无 ESLint 配置** | frontend/ (整个目录) | `pnpm lint` 脚本 `eslint .` 在没有配置文件时会直接报错退出，CI 流水线阻塞 | 添加 `eslint.config.mjs` 或 `.eslintrc.json`，至少包含 `next/core-web-vitals` 预设 |
| C2 | **Position 表格列数不匹配** | `components/positions/positions-table.tsx:27-38` header vs body | 表头有 10 列（含"杠杆""强平价"），body 仅 8 个 `<TableCell>`，列偏移导致保证金数据显示在"杠杆"列下，且 Position 类型中无 `leverage`/`liquidationPrice` 字段 | 移除"杠杆"和"强平价"表头列，或在 Position 类型中补充字段并渲染对应数据 |
| C3 | **零测试覆盖** | 整个项目 | 无 `__tests__/`、`.test.tsx`、`.spec.tsx`，回归风险极高 | 至少为 `lib/api.ts`、`hooks/use-strategies.ts`、`components/error-boundary.tsx` 添加单元测试 |

---

### 3. 🟠 HIGH（高优先级）

| # | 问题 | 文件:行 | 影响 | 建议 |
|---|------|---------|------|------|
| H1 | **api.get() 无超时保护** | `lib/api.ts:32-40` | `get<T>()` 的 `fetch()` 调用无 `AbortController` 超时，后端不可用时请求永久挂起；SWRProvider 的 `fetchWithTimeout` 虽有 10s 超时但实为死代码——所有 `useSWR` 调用传入 `api.getXxx` 作为显式 fetcher，**完全绕过了全局 fetcher** | 在 `get<T>()` 内部添加 `AbortController` + 超时，或统一让 useSWR 使用全局 fetcher（传 key 作为 URL 而非传函数） |
| H2 | **双 fetcher 路径架构冗余** | `lib/api.ts:32` vs `components/swr-provider.tsx:10-38` | `swr-provider.tsx` 定义了精细的全局 fetcher（超时 + 错误富化 + AbortError 处理），但所有 14 个 `useSWR` 调用都传入了自己的 fetcher 函数（`api.getXxx`），全局 fetcher 完全未被使用 | 二选一：(A) 让 `useSWR(key, url)` 走全局 fetcher，去掉 api.ts 的手动 fetch；(B) 将 swr-provider 的超时逻辑合并到 api.ts |
| H3 | **mock-data.ts 完全未引用** | `lib/mock-data.ts` (202行) | 定义了完整 mock 数据集，但没有任何组件导入使用——纯死代码，增加打包体积和维护负担 | 移除非必要代码；若需开发模式 fallback，在 `api.ts` 的 catch 分支中根据 `NODE_ENV` 降级到 mock |
| H4 | **strategy-performance.tsx SWR 模式不一致** | `components/overview/strategy-performance.tsx:39-47` | 使用 `() => api.getMultiSummary()` 箭头函数包装，与其他组件直接传 `api.getXxx` 不一致；箭头函数每次渲染创建新引用，SWR 无法利用函数引用做 dedup | 改为 `useSWR("multi-summary", api.getMultiSummary, { suspense: false })` |
| H5 | **`getMultiStrategy` 返回 `unknown`** | `lib/api.ts:96-97` | `Promise<unknown>` 丢失类型安全，如果未来被调用，数据将无类型检查 | 改为 `Promise<MultiStrategyDetail>` 或对应的正确类型 |

---

### 4. 🟡 MEDIUM

| # | 问题 | 文件 | 建议 |
|---|------|------|------|
| M1 | Analytics 子组件空数据处理交给父组件 | `app/analytics/page.tsx` | `CumulativePnl` 和 `DailyPnl` 直接接收 `data` prop 不做空数组检查，图表渲染空数组可能异常 |
| M2 | `EquityChart` 加载/空数据合并为同一分支 | `components/overview/equity-chart.tsx:28` | `isLoading \|\| !data` 无法区分"正在加载"和"加载完成但无数据" |
| M3 | `ActiveStrategies` 不显示 loading | `components/overview/active-strategies.tsx:12` | 未使用 `isLoading`，数据未到前显示空列表 |
| M4 | `AccountCards` 使用 `"--"` 作为无数据占位符而非 skeleton | `components/overview/account-cards.tsx:16-18` | `isLoading` 时 `StatCard` 显示 skeleton bar，但 fallback 用 `"--"` 文本不够语义化 |
| M5 | package.json 无 `description`/`repository` 字段 | `package.json` | 项目名为 `my-project`，发布到 npm 或内部 registry 时无法识别 |
| M6 | `@base-ui/react` 依赖但未发现使用 | `package.json:12` | 可能是 shadcn 内部依赖被显式列出，也可能是误依赖 |

---

### 5. 🟢 GOOD（做得好的）

1. **X-API-Token 修复已验证** ✅ — `api.ts` 中 `get<T>()`、`updateStrategyStatus`、`createGridStrategy` 全部携带 `X-API-Token` 请求头
2. **ErrorBoundary 设计优良** — 类组件实现的 ErrorBoundary 有 fallback prop、重试按钮、错误日志，`PageErrorFallback` 提供页面级降级 UI
3. **SWR 配置完善** — 30s 自动刷新、revalidateOnFocus/Reconnect、3 次错误重试、5s 重试间隔、keepPreviousData
4. **TypeScript strict 模式** — `tsconfig.json` 中 `"strict": true`，类型定义完整且前后端共享契约
5. **安全响应头** — `next.config.mjs` 中配置了 X-Frame-Options DENY、X-Content-Type-Options nosniff、Referrer-Policy
6. **乐观更新** — `useStrategies()` hook 实现了乐观更新 + 失败回滚模式
7. **WebSocket 优雅降级** — `useTickersWs` hook 有指数退避重连、REST 回退轮询、unmounted 防护
8. **组件 Props 类型完整** — 所有组件 Props 都有 `interface` 或内联类型定义
9. **移动端适配** — `MobileNav` + `Shell` 布局 + 响应式 grid 断点
10. **格式化工具函数纯函数** — `lib/format.ts` 中所有函数无副作用、类型明确

---

### 6. 路由表

| 路由路径 | 对应文件 | 数据源 | 状态 |
|----------|----------|--------|------|
| `/` | `app/page.tsx` → 多组件 | `api.getAccountSummary`, `api.getPnlHistory`, `api.getTickers` (WS), `api.getStrategies`, `api.getMultiSummary`, `api.getMultiDetails` | ✅ 完整 |
| `/grid` | `app/grid/page.tsx` | `useStrategies()` → `api.getStrategies` | ✅ 完整 |
| `/price-action` | `app/price-action/page.tsx` | `useStrategies()` → `api.getStrategies` | ✅ 完整 |
| `/positions` | `app/positions/page.tsx` | `api.getPositions`, `api.getAssets` | ⚠️ 表格列不匹配 |
| `/orders` | `app/orders/page.tsx` | `api.getOrders` | ✅ 完整 |
| `/analytics` | `app/analytics/page.tsx` | `api.getPnlHistory`, `api.getStrategyPerformance` | ✅ 完整 |

---

### 7. 数据流图

```
┌──────────────────────────────────────────────────────────────────┐
│                        数据流架构                                  │
│                                                                   │
│  .env.local          SWRProvider              useSWR              │
│  ┌──────────┐       ┌──────────────┐       ┌──────────────┐      │
│  │API_TOKEN │──────▶│ SWRConfig    │       │ useSWR(key,  │      │
│  │API_BASE  │       │ refresh:30s  │       │  api.getXxx) │      │
│  └──────────┘       │ retry:3      │       └──────┬───────┘      │
│                     └──────────────┘              │               │
│                                                    │               │
│  ┌──────────────────────────────────────────────────▼──────────┐ │
│  │                    lib/api.ts                                │ │
│  │                                                              │ │
│  │  get<T>(path) ──▶ fetch(API_BASE+path, {                    │ │
│  │                     headers: { "X-API-Token": API_TOKEN }     │ │
│  │                   })                                         │ │
│  │                                                              │ │
│  │  ❌ 无 AbortController 超时                                   │ │
│  │  ✅ X-API-Token 已携带                                        │ │
│  └──────────────────────────┬───────────────────────────────────┘ │
│                             │                                     │
│                    ┌────────▼────────┐                            │
│                    │  FastAPI 后端    │                            │
│                    │  localhost:8000  │                            │
│                    └────────┬────────┘                            │
│                             │                                     │
│              ┌──────────────┼──────────────┐                      │
│              ▼              ▼              ▼                      │
│        AccountCards   EquityChart    PositionsPage               │
│        (isLoading?)   (isLoading?)   (posLoading?)               │
│        (error→"--")   (error→空图)   (error→空列表)              │
│                                                                   │
│  ⚠️ 注意: SWRProvider 的全局 fetcher (fetchWithTimeout)          │
│     被所有 useSWR 调用的显式 fetcher 参数覆盖，实际上未使用       │
└──────────────────────────────────────────────────────────────────┘
```

**关键数据流路径**：
- **认证流**: `NEXT_PUBLIC_API_TOKEN` → `api.ts` get() headers → 后端 `X-API-Token` 验证
- **SWR 缓存**: key (如 "strategies") → SWR cache → 跨组件共享 (同一 key 的 useSWR 共享数据)
- **WebSocket 流**: `useTickersWs` → WebSocket auth (token in first message) → 实时 ticker 推送 → REST 回退 (10s 轮询)

---

### 8. 组件健康度

| 组件名 | 行数 | Props类型 | Loading | Error | Empty | 评级 |
|--------|------|-----------|---------|-------|-------|------|
| AccountCards | 48 | ✅ | ✅ pulse | ❌ | ✅ "--" | 🟢 |
| EquityChart | 72 | ✅ | ✅ pulse | ❌ (合并在 !data) | ❌ | 🟡 |
| ActiveStrategies | 60 | ✅ | ❌ (未使用 isLoading) | ❌ | ✅ [] fallback | 🟡 |
| MarketWatch | 57 | ✅ | ❌ | ❌ | ✅ [] fallback | 🟡 |
| MultiStrategyPanel | 99 | ✅ | ✅ pulse | ❌ | ✅ "暂无数据" | 🟢 |
| StrategyPerformance | 174 | ✅ | ✅ skeleton | ✅ | ✅ | 🟢 |
| GridCard | 76 | ✅ | ❌ (父级处理) | ❌ | ❌ | 🟡 |
| PaCard | 95 | ✅ | ❌ (父级处理) | ❌ | ❌ | 🟡 |
| OrdersTable | 132 | ✅ | ✅ pulse row | ❌ | ✅ "没有符合条件的订单" | 🟢 |
| PositionsTable | 71 | ⚠️ (列不匹配) | ✅ pulse row | ❌ | ❌ (无空态) | 🔴 |
| AssetsTable | 55 | ✅ | ✅ pulse row | ❌ | ❌ (无空态) | 🟡 |
| AssetAllocation | 56 | ✅ | ✅ pulse | ❌ | ❌ | 🟡 |
| CumulativePnl | 47 | ✅ | ✅ pulse | ❌ | ❌ | 🟡 |
| DailyPnl | 45 | ✅ | ✅ pulse | ❌ | ❌ | 🟡 |
| StrategyComparison | 109 | ✅ | ✅ pulse + row pulse | ❌ | ❌ | 🟡 |
| CreateGridDialog | 204 | ✅ | ✅ (loading state) | ✅ toast | N/A | 🟢 |
| ErrorBoundary | 87 | ✅ | N/A | ✅ (核心功能) | N/A | 🟢 |
| SWRProvider | 67 | ✅ | N/A | ✅ (retry config) | N/A | 🟢 |
| Shell | 17 | ✅ | N/A | ✅ (ErrorBoundary 包裹) | N/A | 🟢 |

**评级统计**: 🟢 7 | 🟡 11 | 🔴 1

---

### 9. 已知问题修复状态

| # | 原始 CRITICAL 问题 | 状态 | 详情 |
|---|-------------------|------|------|
| 1 | `api.ts` get() 是否携带 X-API-Token？ | ✅ **已修复** | `lib/api.ts:33` — `headers: { "X-API-Token": API_TOKEN }`，同时 `updateStrategyStatus`(L75) 和 `createGridStrategy`(L105) 也正确携带 |
| 2 | ESLint 配置文件是否存在？ | ❌ **未修复** | 整个 frontend/ 目录无 `.eslintrc.*` 或 `eslint.config.*`，但 `package.json` 有 `"lint": "eslint ."` 脚本 |
| 3 | 是否有测试文件？ | ❌ **未修复** | 无 `__tests__/` 目录，无 `.test.tsx`/`.spec.tsx` 文件 |
| 4 | pnpm-lock.yaml 与 package.json 一致性？ | ⚠️ **N/A** | 项目使用 `package-lock.json`（npm），非 pnpm。无 `pnpm-lock.yaml`。这与 package.json 一致 |

---

### 10. 依赖风险

| 风险 | 详情 |
|------|------|
| **next@16.2.6** | Next.js 16 是 pre-release/canary 版本，生产环境建议使用稳定版 15.x 或等待 16 正式发布。可能存在未发现的 bug 和 API 变更 |
| **react@^19 / react-dom@^19** | React 19 已正式发布，与 Next.js 16 搭配合理。但需注意 breaking changes（如 `forwardRef` 不再需要） |
| **@base-ui/react@^1.5.0** | 未在代码中发现显式使用（可能是 shadcn 间接依赖或 MUI Base UI 的残留），建议确认是否需要 |
| **recharts@3.8.0** | 大版本 3.x 有 breaking changes，确认图表渲染正常 |
| **shadcn@^4.8.0** | shadcn CLI 工具作为 dependency（不是 devDependency），应移至 devDependencies |
| **sonner@^2.0.7** | Toast 库，版本较新，与 React 19 兼容性需验证 |
| **缺少 @eslint/eslintrc** | `eslint .` 命令需要 ESLint 配置，否则失败 |
| **swr@^2.4.1** | 版本合理稳定。但架构上全局 fetcher 被绕过（见 H2） |

---

### 11. 修复优先级路线图

```
Week 1 ── 🔴 C1 (ESLint 配置) + C2 (PositionsTable 列数)
Week 2 ── 🟠 H1 (api.get 超时) + H4 (SWR 模式统一) + H3 (移除 mock-data)
Week 3 ── 🟡 M1-M6 杂项修复 + 为 api.ts/useStrategies/ErrorBoundary 添加测试
Week 4 ── 🟠 H2 (双 fetcher 路径重构，可选)
```
