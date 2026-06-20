# 前端架构文档

**文档版本：** v1.0  
**创建日期：** 2026-06-20  
**状态：** ✅ 基于实际源码生成  
**构建工具：** npm（`package-lock.json` 为依赖锁定源）

---

## 1. 技术栈

| 层级 | 技术 | 版本 | 用途 |
|------|------|------|------|
| **框架** | Next.js (App Router) | 16.2.6 | 服务端渲染 / 静态生成 / 路由 |
| **UI 库** | React | 19.x | 组件化视图 |
| **语言** | TypeScript | 5.7.3 | 类型安全 |
| **样式** | Tailwind CSS | 4.2.0 | 原子化 CSS |
| **组件库** | shadcn/ui | 4.8.0 | 无依赖 UI 组件（button, card, table, dialog 等） |
| **图表** | Recharts | 3.8.0 | 权益曲线、收益统计图表 |
| **数据请求** | SWR | 2.4.1 | 客户端数据获取、缓存、自动刷新 |
| **图标** | Lucide React | 1.16.0 | SVG 图标 |
| **主题** | next-themes | 0.4.6 | 暗色/亮色模式切换 |
| **Toast** | Sonner | 2.0.7 | 操作反馈通知 |
| **工具函数** | clsx + tailwind-merge + class-variance-authority | — | 样式组合与条件渲染 |
| **分析** | @vercel/analytics | 1.6.1 | 生产环境用户分析（可选） |
| **字型** | Geist + Geist Mono | — | Google Fonts 无衬线 + 等宽 |

### 依赖锁定

- **包管理器：** npm（`package-lock.json` 为权威锁定文件）
- **注意：** 项目中 `pnpm-lock.yaml` 已过期（`react-is` 版本不一致），统一使用 npm

---

## 2. 目录结构

```
frontend/
├── package.json                  # 依赖与脚本
├── package-lock.json             # npm 锁定（权威）
├── tsconfig.json                 # TypeScript 配置 (strict: true)
├── postcss.config.mjs            # PostCSS（Tailwind 编译）
├── components.json               # shadcn/ui 配置
├── .env.local.example            # 前端环境变量模板
│
├── app/                          # Next.js App Router 页面
│   ├── layout.tsx                # 根布局 (SWR + ErrorBoundary + Shell + Toaster)
│   ├── page.tsx                  # 首页 → 总览仪表盘
│   ├── globals.css               # 全局样式 + Tailwind 指令
│   ├── grid/
│   │   └── page.tsx              # /grid → 网格交易
│   ├── price-action/
│   │   └── page.tsx              # /price-action → 价格行为策略
│   ├── positions/
│   │   └── page.tsx              # /positions → 持仓与资产
│   ├── orders/
│   │   └── page.tsx              # /orders → 订单与成交
│   └── analytics/
│       └── page.tsx              # /analytics → 收益统计
│
├── components/                   # 组件（按领域分组）
│   ├── shell.tsx                 # 根布局壳子 (AppSidebar + TopBar + Main + MobileNav)
│   ├── app-sidebar.tsx           # 桌面端侧边导航
│   ├── mobile-nav.tsx            # 移动端底部导航
│   ├── stat-card.tsx             # 统计卡片通用组件
│   ├── status-badge.tsx          # 策略状态徽章 (running/paused/stopped)
│   ├── strategy-controls.tsx     # 策略启停控制
│   ├── swr-provider.tsx          # SWR 全局配置 (Client Component)
│   ├── error-boundary.tsx        # React Error Boundary 降级 UI
│   │
│   ├── overview/                 # 首页仪表盘组件
│   │   ├── account-cards.tsx     # 账户总权益/今日盈亏/未实现盈亏/累计盈亏
│   │   ├── active-strategies.tsx # 运行中策略列表
│   │   ├── equity-chart.tsx      # 权益曲线图表
│   │   ├── market-watch.tsx      # 市场行情 (BTC/ETH)
│   │   ├── multi-strategy-panel.tsx # 多策略运行汇总
│   │   └── strategy-performance.tsx # 策略绩效看板
│   │
│   ├── grid/                     # 网格交易组件
│   │   ├── grid-card.tsx         # 单个网格策略卡片
│   │   └── grid-visual.tsx       # 网格可视化
│   │
│   ├── price-action/             # 价格行为策略组件
│   │   └── pa-card.tsx           # PA 策略卡片
│   │
│   ├── orders/                   # 订单组件
│   │   └── orders-table.tsx      # 订单列表表格
│   │
│   ├── positions/                # 持仓组件
│   │   ├── assets-table.tsx      # 资产列表表格
│   │   └── asset-allocation.tsx  # 资产分配饼图
│   │
│   ├── analytics/                # 分析组件
│   │   ├── cumulative-pnl.tsx    # 累计盈亏图
│   │   ├── daily-pnl.tsx         # 每日盈亏图
│   │   └── strategy-comparison.tsx # 策略对比图
│   │
│   └── ui/                       # shadcn/ui 基础组件 (17 个)
│       ├── badge.tsx, button.tsx, card.tsx, chart.tsx,
│       ├── dialog.tsx, dropdown-menu.tsx, input.tsx, label.tsx,
│       ├── progress.tsx, scroll-area.tsx, select.tsx, separator.tsx,
│       ├── sonner.tsx, switch.tsx, table.tsx, tabs.tsx, tooltip.tsx
│
├── hooks/
│   └── use-strategies.ts         # 策略 SWR hook (含乐观更新)
│
├── lib/
│   ├── api.ts                    # 数据服务层 (14 个 API 函数)
│   ├── types.ts                  # 领域模型类型 (14 个 interface/type)
│   ├── format.ts                 # 数字/百分比格式化
│   ├── utils.ts                  # cn() 样式工具函数
│   └── mock-data.ts              # 开发占位数据 (8 策略 × 示例)
│
└── public/                       # 静态资源
    ├── icon.svg, icon-light-32x32.png, icon-dark-32x32.png
    ├── apple-icon.png
    └── placeholder-*.jpg/svg
```

---

## 3. 组件树

```
<html lang="zh-CN">
  <body>
    <ErrorBoundary>                        ← 全局错误捕获
      <SWRProvider>                        ← SWR 配置 (30s 自动刷新)
        <Shell>                            ← 布局壳子
          ├── <AppSidebar />               ← 桌面端侧边栏 (6 个路由)
          ├── <TopBar />                   ← 顶部栏 (面包屑 / 用户信息)
          ├── <main>
          │   └── {children}              ← 页面内容 (由 App Router 注入)
          └── <MobileNav />               ← 移动端底部导航
      </SWRProvider>
    </ErrorBoundary>
    <Toaster position="top-right" />       ← Sonner 通知容器
    <Analytics />                          ← Vercel Analytics (仅 production)
  </body>
</html>
```

**页面级组件树**（以首页为例）：

```
OverviewPage
├── <ErrorBoundary>
│   └── <AccountCards />                  ← 4 个 StatCard (SWR: "account")
├── <ErrorBoundary>
│   └── <EquityChart />                   ← Recharts AreaChart (SWR: pnl-history)
├── <ErrorBoundary>
│   └── <MarketWatch />                   ← BTC/ETH 实时行情 (SWR: tickers)
├── <ErrorBoundary>
│   └── <ActiveStrategies />              ← 策略列表 + 启停控制 (SWR: strategies)
├── <ErrorBoundary>
│   └── <StrategyPerformanceDashboard />  ← 策略绩效 (SWR: strategy-performance)
└── <ErrorBoundary>
    └── <MultiStrategyPanel />            ← 多策略汇总 (SWR: multi/summary)
```

> **设计原则：** 每个数据区块用独立的 `<ErrorBoundary>` 包裹，单个区块崩溃不影响其他区块。

---

## 4. 路由表

**定义来源：** `components/app-sidebar.tsx` 的 `nav` 数组

| 路径 | 页面标题 | 图标 | 说明 |
|------|----------|------|------|
| `/` | 总览仪表盘 | `LayoutDashboard` | 账户概览 + 权益曲线 + 策略列表 + 多策略面板 |
| `/grid` | 网格交易 | `Grid3x3` | 网格策略管理 (BTC/USDT + ETH/USDT) |
| `/price-action` | 价格行为策略 | `CandlestickChart` | Donchian / Structure / SuperTrend / Reversal 四策略 |
| `/positions` | 持仓与资产 | `Wallet` | 当前持仓 + 资产分配 |
| `/orders` | 订单与成交 | `ListOrdered` | 历史订单列表 |
| `/analytics` | 收益统计 | `LineChart` | 累计 PnL + 每日 PnL + 策略对比 |

**导航分组：**
- "交易管理" → 全部 6 个路由
- `/grid` 和 `/price-action` 按策略类型拆分展示（网格类 vs PA 类）

---

## 5. SWR 数据流

### 5.1 数据获取架构

```
┌──────────────────────────────────────────────────────┐
│  SWRProvider (swr-provider.tsx)                      │
│  • refreshInterval: 30,000ms                         │
│  • revalidateOnFocus: true                           │
│  • errorRetryCount: 3                                │
│  • dedupingInterval: 2,000ms                         │
│  • keepPreviousData: true (切换时不闪烁)              │
└──────────────┬───────────────────────────────────────┘
               │ fetcher(url) → fetchWithTimeout(url)
               │     ↓ X-API-Token header
┌──────────────▼───────────────────────────────────────┐
│  lib/api.ts (数据服务层)                              │
│  • API_BASE = NEXT_PUBLIC_API_BASE || localhost:8000  │
│  • 14 个类型安全函数                                  │
│  • 统一使用 X-API-Token 认证                          │
└──────────────┬───────────────────────────────────────┘
               │ HTTP fetch
┌──────────────▼───────────────────────────────────────┐
│  FastAPI Backend (src/api/app.py)                    │
│  • /account/summary  • /market/tickers               │
│  • /strategies        • /positions                   │
│  • /assets            • /orders                      │
│  • /analytics/pnl-history                            │
│  • /analytics/strategy-performance                   │
│  • /multi/summary     • /multi/details               │
│  • PATCH /strategies/:id/status                      │
│  • POST /strategies/create-grid                      │
└──────────────────────────────────────────────────────┘
```

### 5.2 SWR Key 与 API 映射

| SWR Key | API 函数 | 端点 | 消费组件 |
|---------|----------|------|----------|
| `"account"` | `api.getAccountSummary()` | GET `/account/summary` | `AccountCards` |
| `"tickers"` | `api.getTickers()` | GET `/market/tickers` | `MarketWatch` |
| `"strategies"` | `api.getStrategies()` | GET `/strategies` | `ActiveStrategies`, `useStrategies` hook |
| `"positions"` | `api.getPositions()` | GET `/positions` | `AssetsTable` |
| `"assets"` | `api.getAssets()` | GET `/assets` | `AssetAllocation` |
| `"orders"` | `api.getOrders()` | GET `/orders` | `OrdersTable` |
| `"pnl-history"` | `api.getPnlHistory()` | GET `/analytics/pnl-history` | `EquityChart` |
| `"strategy-performance"` | `api.getStrategyPerformance()` | GET `/analytics/strategy-performance` | `StrategyPerformanceDashboard` |
| `"multi-summary"` | `api.getMultiSummary()` | GET `/multi/summary` | `MultiStrategyPanel` |
| `"multi-details"` | `api.getMultiDetails()` | GET `/multi/details` | `MultiStrategyPanel` |

### 5.3 乐观更新模式

`useStrategies()` hook 在启停策略时使用 SWR `mutate()` 实现**乐观更新**：

```typescript
mutate(
  (prev) => prev?.map((s) => (s.id === id ? { ...s, status } : s)),
  { revalidate: false }  // 先不重新请求，立即更新 UI
)
// ... 调用 API
// 成功 → toast.success()
// 失败 → mutate() 回滚 + toast.error()
```

---

## 6. 领域类型 (`lib/types.ts`)

| 类型 | 字段数 | 说明 |
|------|--------|------|
| `StrategyType` | 8 值联合 | `"grid" \| "rsi" \| "ma" \| "buyhold" \| "donchian" \| "structure" \| "supertrend" \| "reversal"` |
| `StrategyStatus` | 3 值联合 | `"running" \| "paused" \| "stopped"` |
| `AccountSummary` | 8 字段 | 总权益 / 可用余额 / 持仓市值 / 未实现盈亏 / 今日盈亏 / 累计盈亏 |
| `Strategy` | 10 字段 | id / name / type / symbol / status / pnl / grid 参数 |
| `GridParams` | 6 字段 | 上下限价 / 网格数 / 每格利润率 / 成交网格数 |
| `Position` | 10 字段 | 开仓均价 / 标记价格 / 未实现盈亏 / 策略名 |
| `Order` | 10 字段 | 方向 / 类型 / 价格 / 数量 / 手续费 |
| `Ticker` | 6 字段 | 价格 / 24h 涨跌幅 / 成交量 |
| `AssetBalance` | 6 字段 | 总 / 可用 / 委托中 / USDT 估值 |
| `PnlPoint` | 4 字段 | 日期 / 权益 / 日盈亏 / 累计盈亏 |
| `StrategyPerformance` | 4 字段 | 名称 / pnl / 成交笔数 / 胜率 |
| `MultiStrategySummary` | 4 字段 | 总 pnl / 总成交 / 策略数 / 插槽列表 |
| `MultiStrategyDetail` | 7 字段 | 策略 id / 品种 / pnl / 胜率 |
| `CreateGridParams` | 5 字段 | 创建网格请求体 |

> **类型即契约：** 前后端共享此类型定义。后端返回 JSON 必须与此结构匹配。

---

## 7. 认证机制

- **方式：** HTTP Header `X-API-Token`
- **Token 来源：** 环境变量 `NEXT_PUBLIC_API_TOKEN`
- **注入位置：**
  - `lib/api.ts` → `get()` / `fetch()` 的 headers
  - `swr-provider.tsx` → `fetchWithTimeout()` 的 headers
- **后端验证：** `src/api/app.py` 中间件检查 `X-API-Token` 是否为有效值（与 `API_TOKEN` 环境变量比较）

---

## 8. 已知限制

| # | 限制 | 影响 | 优先级 |
|---|------|------|--------|
| 1 | **无前端测试** | QA 报告标记前端测试覆盖率为 0%。无 Jest / React Testing Library / Cypress 测试。 | 🟠 HIGH |
| 2 | **无 ESLint 配置** | `package.json` 有 `"lint": "eslint ."` 但未安装 ESLint 依赖，命令不可执行。 | 🟡 MEDIUM |
| 3 | **无 CI/CD 前端步骤** | 前端构建 (`next build`) 未纳入自动化流水线。 | 🟡 MEDIUM |
| 4 | **mock-data.ts 残留** | `lib/mock-data.ts` 定义了完整的 mock 数据（8 策略、60 日 PnL 历史等），虽然当前 API 层已切换到真实后端，但 mock 文件未删除，可能误导维护者。 | 🟡 MEDIUM |
| 5 | **pnpm-lock.yaml 过期** | `pnpm-lock.yaml` 与 `package-lock.json` 并存且不一致。`install.cmd` 强制使用 npm。 | 🟡 MEDIUM |
| 6 | **固定端口 3001** | 前端 dev server 固定 `--port 3001`（因 Grafana 占 3000），无法通过 env 配置。 | 🟢 LOW |
| 7 | **无暗色/亮色切换 UI** | `next-themes` 已安装但未见主题切换按钮实现。 | 🟢 LOW |
| 8 | **无 i18n 支持** | 所有文案硬编码为中文。 | 🟢 LOW |

---

**文档状态：** ✅ 基于源码生成  
**待验证项：** `TopBar` 组件完整实现（当前仅从 Shell 引用推断）；暗色模式实际状态  
**更新日期：** 2026-06-20
