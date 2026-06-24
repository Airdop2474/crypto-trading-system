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
  AgentAdoptionRate,
  AgentAnalysisResult,
  AgentAuditLogEntry,
  AgentTask,
  AssetBalance,
  ClosedTradeHistory,
  CreateGridParams,
  CreateStrategyParams,
  DataCleanupResult,
  DrawdownPoint,
  EvolutionResult,
  EvolutionHistoryResponse,
  EvolutionStats,
  EvolveRequest,
  HermesStatus,
  MonteCarloRequest,
  MonteCarloResult,
  MultiStrategyDetail,
  MultiStrategyResult,
  MultiStrategySummary,
  OrdersPage,
  PnlDistribution,
  PnlPoint,
  PortfolioHeat,
  Position,
  RiskMetrics,
  RiskStatus,
  Strategy,
  StrategyCorrelation,
  StrategyEvaluation,
  StrategyEvaluationRequest,
  StrategyPerformance,
  StrategyRegistryResponse,
  StrategyRunHistoryResponse,
  Ticker,
  TelegramConfig,
  TelegramConfigUpdate,
  TelegramTestResult,
  WinRateTrendPoint,
  ModeResult,
  ModeState,
  StartModeParams,
  RunningMode,
  TestnetValidationResult,
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

  // GET /orders?limit=&offset=
  // 返回分页结构 { items, total, limit, offset, has_more }
  getOrders: (limit: number = 100, offset: number = 0): Promise<OrdersPage> =>
    get(`/orders?limit=${limit}&offset=${offset}`),

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
  getMultiStrategy: (id: string): Promise<MultiStrategyResult> =>
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

  // --------------------------------------------------------------------------
  // AI Agent 分析（只分析，不执行）
  // --------------------------------------------------------------------------
  // POST /agent/analyze
  runAgentAnalysis: async (
    task: AgentTask,
    phase: string = "Phase 6",
  ): Promise<AgentAnalysisResult> => {
    const res = await fetch(`${API_BASE}/agent/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Token": API_TOKEN },
      body: JSON.stringify({ task, phase }),
    })
    if (!res.ok) {
      throw new Error(`POST /agent/analyze failed: ${res.status}`)
    }
    return res.json()
  },

  // GET /agent/audit-logs?task=&limit=
  getAgentAuditLogs: (
    task?: AgentTask,
    limit: number = 50,
  ): Promise<AgentAuditLogEntry[]> =>
    get(
      `/agent/audit-logs?limit=${limit}${task ? `&task=${task}` : ""}`,
    ),

  // GET /agent/adoption-rate?task=
  getAgentAdoptionRate: (task?: AgentTask): Promise<AgentAdoptionRate> =>
    get(`/agent/adoption-rate${task ? `?task=${task}` : ""}`),

  // GET /health/detailed
  getHealthDetailed: (): Promise<{
    status: string
    ws_connected: boolean
    ws_clients: number
    cache_backend: string
    cache_available: boolean
  }> => get("/health/detailed"),

  // --------------------------------------------------------------------------
  // 风险指标
  // --------------------------------------------------------------------------
  // GET /account/risk-metrics
  getRiskMetrics: (): Promise<RiskMetrics> => get("/account/risk-metrics"),

  // GET /risk/drawdown-curve
  getDrawdownCurve: (): Promise<DrawdownPoint[]> => get("/risk/drawdown-curve"),

  // GET /risk/status
  getRiskStatus: (): Promise<RiskStatus> => get("/risk/status"),

  // --------------------------------------------------------------------------
  // 持仓历史 / 盈亏分布
  // --------------------------------------------------------------------------
  // GET /positions/history?limit=
  getPositionsHistory: (limit: number = 200): Promise<ClosedTradeHistory[]> =>
    get(`/positions/history?limit=${limit}`),

  // GET /analytics/pnl-distribution?bins=
  getPnlDistribution: (bins: number = 10): Promise<PnlDistribution> =>
    get(`/analytics/pnl-distribution?bins=${bins}`),

  // GET /analytics/win-rate-trend?window=
  getWinRateTrend: (window: number = 20): Promise<WinRateTrendPoint[]> =>
    get(`/analytics/win-rate-trend?window=${window}`),

  // GET /analytics/strategy-correlation
  getStrategyCorrelation: (): Promise<StrategyCorrelation> =>
    get("/analytics/strategy-correlation"),

  // --------------------------------------------------------------------------
  // 运行模式管理
  // --------------------------------------------------------------------------
  // GET /modes
  getModes: (): Promise<ModeState[]> => get("/modes"),

  // GET /modes/{mode}/status
  getModeStatus: (mode: RunningMode): Promise<ModeState> =>
    get(`/modes/${mode}/status`),

  // POST /modes/{mode}/start
  startMode: async (mode: RunningMode, params: StartModeParams): Promise<ModeState> => {
    const res = await fetch(`${API_BASE}/modes/${mode}/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Token": API_TOKEN },
      body: JSON.stringify(params),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `启动模式失败: ${res.status}`)
    }
    return res.json()
  },

  // POST /modes/{mode}/stop
  stopMode: async (mode: RunningMode): Promise<ModeState> => {
    const res = await fetch(`${API_BASE}/modes/${mode}/stop`, {
      method: "POST",
      headers: { "X-API-Token": API_TOKEN },
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `停止模式失败: ${res.status}`)
    }
    return res.json()
  },

  // POST /modes/testnet_live/validate
  validateTestnet: async (): Promise<TestnetValidationResult> => {
    const res = await fetch(`${API_BASE}/modes/testnet_live/validate`, {
      method: "POST",
      headers: { "X-API-Token": API_TOKEN },
    })
    if (!res.ok) throw new Error(`验证失败: ${res.status}`)
    return res.json()
  },

  // GET /modes/{mode}/logs?limit=
  getModeLogs: (mode: RunningMode, limit: number = 200): Promise<string[]> =>
    get(`/modes/${mode}/logs?limit=${limit}`),

  // GET /modes/{mode}/result
  getModeResult: (mode: RunningMode): Promise<ModeResult> =>
    get(`/modes/${mode}/result`),

  // --------------------------------------------------------------------------
  // 管理 / 急停
  // --------------------------------------------------------------------------
  // POST /admin/emergency-stop
  emergencyStop: async (): Promise<{
    ok: boolean
    previous_state: string
    current_state: string
    message: string
  }> => {
    const res = await fetch(`${API_BASE}/admin/emergency-stop`, {
      method: "POST",
      headers: { "X-API-Token": API_TOKEN },
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `急停失败: ${res.status}`)
    }
    return res.json()
  },

  // --------------------------------------------------------------------------
  // 策略 AI 进化
  // --------------------------------------------------------------------------
  // POST /agent/evolve
  runEvolution: async (req: EvolveRequest): Promise<EvolutionResult[]> => {
    const res = await fetch(`${API_BASE}/agent/evolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Token": API_TOKEN },
      body: JSON.stringify(req),
    })
    if (!res.ok) {
      throw new Error(`POST /agent/evolve failed: ${res.status}`)
    }
    return res.json()
  },

  // GET /agent/evolution-history?strategy_id=&limit=
  getEvolutionHistory: (
    strategyId?: string,
    limit: number = 50,
  ): Promise<EvolutionHistoryResponse> =>
    get(
      `/agent/evolution-history?limit=${limit}${strategyId ? `&strategy_id=${strategyId}` : ""}`,
    ),

  // GET /agent/evolution-stats
  getEvolutionStats: (): Promise<EvolutionStats> =>
    get("/agent/evolution-stats"),

  // --------------------------------------------------------------------------
  // Hermes 外部 Agent
  // --------------------------------------------------------------------------
  // GET /agent/hermes/status
  getHermesStatus: (): Promise<HermesStatus> =>
    get("/agent/hermes/status"),

  // --------------------------------------------------------------------------
  // 策略注册表 / 通用创建 / 参数更新 / 运行历史
  // --------------------------------------------------------------------------
  // GET /strategies/registry
  getStrategyRegistry: (): Promise<StrategyRegistryResponse> =>
    get("/strategies/registry"),

  // GET /strategies/configs
  getStrategyConfigs: (): Promise<Record<string, Record<string, number | boolean>>> =>
    get("/strategies/configs"),

  // POST /strategies/create
  createStrategy: async (params: CreateStrategyParams): Promise<Strategy> => {
    const res = await fetch(`${API_BASE}/strategies/create`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Token": API_TOKEN },
      body: JSON.stringify(params),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `创建策略失败: ${res.status}`)
    }
    return res.json()
  },

  // PATCH /strategies/{id}/params
  updateStrategyParams: async (
    id: string,
    params: Record<string, number | boolean>,
  ): Promise<{ strategy_id: string; updated: Record<string, number | boolean> }> => {
    const res = await fetch(`${API_BASE}/strategies/${id}/params`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", "X-API-Token": API_TOKEN },
      body: JSON.stringify({ params }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `更新参数失败: ${res.status}`)
    }
    return res.json()
  },

  // DELETE /strategies/configs/{strategy_type}
  deleteStrategyConfig: async (strategyType: string): Promise<void> => {
    const res = await fetch(`${API_BASE}/strategies/configs/${strategyType}`, {
      method: "DELETE",
      headers: { "X-API-Token": API_TOKEN },
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `删除配置失败: ${res.status}`)
    }
  },

  // PUT /strategies/configs/{strategy_type}/rename
  renameStrategyConfig: async (
    strategyType: string,
    newName: string,
  ): Promise<void> => {
    const res = await fetch(`${API_BASE}/strategies/configs/${strategyType}/rename`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-API-Token": API_TOKEN },
      body: JSON.stringify({ new_name: newName }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `重命名失败: ${res.status}`)
    }
  },

  // GET /strategies/history?strategy_id=&limit=&offset=
  getStrategyHistory: (
    strategyId?: string,
    limit: number = 50,
    offset: number = 0,
  ): Promise<StrategyRunHistoryResponse> =>
    get(
      `/strategies/history?limit=${limit}&offset=${offset}${strategyId ? `&strategy_id=${strategyId}` : ""}`,
    ),

  // --------------------------------------------------------------------------
  // 数据清理
  // --------------------------------------------------------------------------
  // POST /admin/data/cleanup
  cleanupData: async (
    scope: "all" | "runs" | "evolutions" = "all",
    keepLatest: boolean = false,
  ): Promise<DataCleanupResult> => {
    const res = await fetch(`${API_BASE}/admin/data/cleanup`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Token": API_TOKEN },
      body: JSON.stringify({ scope, keepLatest }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `清理数据失败: ${res.status}`)
    }
    return res.json()
  },

  clearCache: async (): Promise<{
    status: string
    cleared_keys: number
    db_rows_cleared: number
    files_cleared: number
    message: string
  }> => {
    const res = await fetch(`${API_BASE}/admin/clear-cache?confirm=true`, {
      method: "POST",
      headers: { "X-API-Token": API_TOKEN },
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `清除缓存失败: ${res.status}`)
    }
    return res.json()
  },

  // POST /admin/refresh-state
  refreshState: async (): Promise<{ status: string; message: string }> => {
    const res = await fetch(`${API_BASE}/admin/refresh-state`, {
      method: "POST",
      headers: { "X-API-Token": API_TOKEN },
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `刷新状态失败: ${res.status}`)
    }
    return res.json()
  },

  // POST /admin/generate-data
  generateData: async (marketType: string = "oscillating"): Promise<{ ok: boolean; message: string }> => {
    const res = await fetch(`${API_BASE}/admin/generate-data`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Token": API_TOKEN },
      body: JSON.stringify({ marketType }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `数据生成失败: ${res.status}`)
    }
    return res.json()
  },

  // --------------------------------------------------------------------------
  // 组合热力 Portfolio Heat（GET /risk/portfolio-heat）
  // --------------------------------------------------------------------------
  getPortfolioHeat: (): Promise<PortfolioHeat> => get("/risk/portfolio-heat"),

  // --------------------------------------------------------------------------
  // Monte Carlo 模拟（POST /analytics/monte-carlo）
  // --------------------------------------------------------------------------
  runMonteCarlo: async (req: MonteCarloRequest): Promise<MonteCarloResult> => {
    const res = await fetch(`${API_BASE}/analytics/monte-carlo`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Token": API_TOKEN },
      body: JSON.stringify(req),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `Monte Carlo 模拟失败: ${res.status}`)
    }
    return res.json()
  },

  // --------------------------------------------------------------------------
  // 策略评估（POST /analytics/strategy-evaluation）
  // --------------------------------------------------------------------------
  runStrategyEvaluation: async (req: StrategyEvaluationRequest = {}): Promise<StrategyEvaluation[]> => {
    const res = await fetch(`${API_BASE}/analytics/strategy-evaluation`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Token": API_TOKEN },
      body: JSON.stringify(req),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `策略评估失败: ${res.status}`)
    }
    return res.json()
  },

  // --------------------------------------------------------------------------
  // Telegram 通知配置
  // --------------------------------------------------------------------------
  getTelegramConfig: (): Promise<TelegramConfig> => get("/admin/telegram-config"),

  saveTelegramConfig: async (req: TelegramConfigUpdate): Promise<{ ok: boolean; enabled: boolean; message: string }> => {
    const res = await fetch(`${API_BASE}/admin/telegram-config`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Token": API_TOKEN },
      body: JSON.stringify(req),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `保存 Telegram 配置失败: ${res.status}`)
    }
    return res.json()
  },

  testTelegram: async (): Promise<TelegramTestResult> => {
    const res = await fetch(`${API_BASE}/admin/test-telegram`, {
      method: "POST",
      headers: { "X-API-Token": API_TOKEN },
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `Telegram 测试失败: ${res.status}`)
    }
    return res.json()
  },
}

// SWR fetcher：以函数 key 直接调用对应的服务方法
export type ApiKey = keyof typeof api
