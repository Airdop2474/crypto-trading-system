# 前后端功能差距分析报告

> 生成日期：2026-06-22
> 范围：后端 FastAPI 端点 vs. 前端 Next.js 页面/组件

---

## 一、后端存在但前端完全未调用的端点

| # | 端点 | 方法 | 用途 | 影响 |
|---|------|------|------|------|
| 1 | `/health` | GET | 基础健康检查（`{"status":"ok"}`） | 低——前端用 `/health/detailed`，基础检查冗余未暴露 |
| 2 | `/strategies/configs` | GET | 已保存的策略参数配置文件 | **中**——前端 `api.ts` 导出了 `getStrategyConfigs()` 但**没有任何组件调用它**，导致策略配置无法加载/管理 |
| 3 | `/modes/{mode}/status` | GET | 单个运行模式的详细状态 | **低**——已有 `GET /modes` 聚合数据，但单个模式详情页缺失 |
| 4 | `/admin/start-trading` | POST | 手动启动模拟盘引擎 | **高**——没有前端入口控制交易引擎启停 |

---

## 二、前端存在但功能残缺/不可操作的区域

### 2.1 策略详情页（`/strategy/[id]`）

| 问题 | 位置 | 描述 |
|------|------|------|
| **「暂停」按钮无功能** | `page.tsx:120-123` | 渲染了 `<Button variant="secondary"><Pause />暂停</Button>`，但**没有绑定任何 `onClick` 处理函数**，点击无反应 |
| **「参数」按钮跳转错误** | `page.tsx:114-118` | 按钮本应弹出参数修改对话框，实际却 `<Link href="/strategies">` 跳转到策略列表页 |
| **缺少「启停」联动** | 整页 | 调用 `PATCH /strategies/{id}/status` 可以暂停/恢复策略，但详情页完全没有实现此交互 |

### 2.2 设置页（`/settings`）

| 问题 | 位置 | 描述 |
|------|------|------|
| **偏好设置不生效** | 全页面 | `refreshInterval`、`ordersPageSize`、`compactMode`、`showTooltips` 保存到 `localStorage`，但**没有任何组件读取这些配置**，纯属摆设 |
| **API 密钥管理缺失** | 底部说明 | 页面明确标注"API 密钥管理、通知配置等敏感设置暂未开放" |
| **通知配置缺失** | 底部说明 | 同上 |

### 2.3 通知铃铛

| 问题 | 位置 | 描述 |
|------|------|------|
| **通知按钮无交互** | `top-bar.tsx` | 顶部栏铃铛图标 `<Button aria-label="通知">` 没有 `onClick`、没有下拉、没有未读计数、完全没有功能 |

### 2.4 移动端导航

| 问题 | 位置 | 描述 |
|------|------|------|
| **5 个页面在移动端不可达** | `mobile-nav.tsx` | 底部导航只包含 6 项，缺少 `/strategies`、`/risk`、`/agent`、`/system`、`/settings`，移动端用户无法访问这些页面 |

---

## 三、后端有完整功能但前端无对应页面的特性

### 3.1 交易引擎控制

后端有完整的 `POST /admin/start-trading`（启动模拟盘交易引擎），但前端**没有任何按钮或 UI** 来触发它。系统页（`/system`）有启动/停止 mode 的功能，但没有"启动交易引擎"的入口。

### 3.2 策略配置管理

后端 `GET /strategies/configs` 返回已保存的策略参数 JSON 配置文件，但前端：
- `api.ts` 导出了 `getStrategyConfigs()` 
- 没有任何组件调用它

策略的配置导入/导出/模板管理功能完全缺失。

### 3.3 风险控制的细粒度操作

后端 `GET /risk/status` 返回完整风控状态（风控状态机状态、日亏损、连续亏损、回撤、API 失败计数），前端 `RiskStatusCard` 已消费该数据，但**缺少任何重置/解除风控的操作按钮**。

### 3.4 AI Agent 分析结果联动

后端支持 5 种分析任务类型（`backtest`、`trade_attribution`、`risk_checklist`、`param_sensitivity`、`weekly_review`），前端触发面板已覆盖，但**分析结果无法一键应用到策略参数**——缺少"应用建议"→`PATCH /strategies/{id}/params` 的闭环。

### 3.5 订单取消功能

后端可能支持订单取消（订单系统有 `cancel` 概念），但前端订单页（`/orders`）只有查看和导出，**无取消/撤单操作按钮**。

---

## 四、前端无用代码/死代码

| 文件 | 函数/变量 | 说明 |
|------|-----------|------|
| `lib/api.ts` | `getModeStatus(mode)` | 定义了 `GET /modes/{mode}/status` 调用，但**没有任何组件使用** |
| `lib/api.ts` | `getStrategyConfigs()` | 定义了 `GET /strategies/configs` 调用，但**没有任何组件使用** |
| `lib/api.ts` | `getEvolutionStats()` | 仅作为 SWR mutate key（从未直接 `fetcher` 调用），代码可能存在 |

---

## 五、质量与体验问题

| 问题 | 严重程度 | 说明 |
|------|---------|------|
| 无登录页 | **高** | API token 只读环境变量，无登录/登出/API Key 管理 UI |
| 后端地址硬编码 | **中** | 前端 `api.ts` 中 `API_BASE_URL` 硬编码为 `http://localhost:8000`，无环境配置灵活切换 |
| 无 404 页产品化 | **低** | `not-found.tsx` 存在但内容极简 |
| 无全局错误边界 | **中** | 只在页面级有 `error.tsx`，无根布局级错误边界兜底 |
| 无数据空状态 | **中** | 部分表格在空数据时只显示"暂无数据"文本，缺少图示引导 |

---

## 六、优先修复建议

### P0 — 必须立即修复

1. **策略详情页「暂停」按钮绑定 `onClick`** → 调用 `PATCH /strategies/{id}/status`（`updateStrategyStatus`）
2. **策略详情页「参数」按钮改为弹出参数编辑对话框**（复用 `StrategyParamsDialog`），而非跳转列表页
3. **移动端导航补全 5 个缺失页面的入口**

### P1 — 应尽快修复

4. **设置页偏好值接入对应组件**（`refreshInterval` 接入 SWR `refreshInterval`，`ordersPageSize` 接入订单页分页，`compactMode` 接入全局 CSS class）
5. **通知铃铛绑定交互或移除**
6. **添加交易引擎启动按钮**（`POST /admin/start-trading`）

### P2 — 有则更好

7. 清理 `api.ts` 中的死函数（`getModeStatus`、`getStrategyConfigs`）
8. AI 分析结果一键应用建议
9. 订单撤单功能
