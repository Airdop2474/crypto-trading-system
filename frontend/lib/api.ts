// ============================================================================
// 数据服务层 (Data Service Layer)
// ----------------------------------------------------------------------------
// 这是 UI 与「数据来源」之间唯一的边界。现已对接后端 FastAPI（src/api）。
//
// 后端地址通过环境变量 NEXT_PUBLIC_API_BASE 配置，默认 http://localhost:8000。
// 后端数据来自 Paper Trading 引擎的真实运行结果（见 src/api/service.py）。
//
// 所有页面通过 SWR 调用这些 key 化的函数，便于缓存与跨组件状态同步。
// UI 层 (SWR) 无需改动，仅本文件从 mock 切换为真实请求。
// ============================================================================

import type {
  AccountSummary,
  AssetBalance,
  CreateGridParams,
  MultiStrategyDetail,
  MultiStrategySummary,
  Order,
  PnlPoint,
  Position,
  Strategy,
  StrategyPerformance,
  Ticker,
} from "./types"

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"

const API_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN || ""

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "X-API-Token": API_TOKEN },
  })
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  // GET /account/summary
  getAccountSummary: (): Promise<AccountSummary> => get("/account/summary"),

  // GET /market/tickers
  getTickers: (): Promise<Ticker[]> => get("/market/tickers"),

  // GET /strategies
  getStrategies: (): Promise<Strategy[]> => get("/strategies"),

  // GET /positions
  getPositions: (): Promise<Position[]> => get("/positions"),

  // GET /assets
  getAssets: (): Promise<AssetBalance[]> => get("/assets"),

  // GET /orders
  getOrders: (): Promise<Order[]> => get("/orders"),

  // GET /analytics/pnl-history
  getPnlHistory: (): Promise<PnlPoint[]> => get("/analytics/pnl-history"),

  // GET /analytics/strategy-performance
  getStrategyPerformance: (): Promise<StrategyPerformance[]> =>
    get("/analytics/strategy-performance"),

  // PATCH /strategies/:id/status —— 启停策略（Paper 模式为 no-op 回显）
  updateStrategyStatus: async (
    id: string,
    status: Strategy["status"],
  ): Promise<{ id: string; status: Strategy["status"] }> => {
    const res = await fetch(`${API_BASE}/strategies/${id}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", "X-API-Token": API_TOKEN },
      body: JSON.stringify({ status }),
    })
    if (!res.ok) {
      throw new Error(`PATCH status failed: ${res.status}`)
    }
    return res.json()
  },

  // --------------------------------------------------------------------------
  // 多策略 API
  // --------------------------------------------------------------------------
  // GET /multi/summary
  getMultiSummary: (): Promise<MultiStrategySummary> =>
    get("/multi/summary"),

  // GET /multi/details
  getMultiDetails: (): Promise<MultiStrategyDetail[]> =>
    get("/multi/details"),

  // GET /multi/strategy/:id
  getMultiStrategy: (id: string): Promise<unknown> =>
    get(`/multi/strategy/${id}`),

  // --------------------------------------------------------------------------
  // 创建策略（Paper 模式为本地回显）
  // --------------------------------------------------------------------------
  createGridStrategy: async (params: CreateGridParams): Promise<Strategy> => {
    const res = await fetch(`${API_BASE}/strategies/create-grid`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Token": API_TOKEN },
      body: JSON.stringify(params),
    })
    if (!res.ok) {
      throw new Error(`POST create-grid failed: ${res.status}`)
    }
    return res.json()
  },
}

// SWR fetcher：以函数 key 直接调用对应的服务方法
export type ApiKey = keyof typeof api
