// 领域模型类型定义 —— 前后端共享的数据契约
// 未来对接真实接口时，保持这些类型不变即可让 UI 无缝复用。

export type StrategyType = "grid" | "rsi" | "ma" | "buyhold" | "donchian" | "structure" | "supertrend" | "reversal" | "priceaction"
export type StrategyStatus = "running" | "paused" | "stopped"
export type Side = "buy" | "sell"
export type OrderStatus = "filled" | "open" | "partially_filled" | "canceled"

export interface AccountSummary {
  totalEquity: number // 账户总权益 (USDT)
  availableBalance: number // 可用余额
  positionValue: number // 持仓市值
  unrealizedPnl: number // 未实现盈亏
  todayPnl: number // 今日盈亏
  todayPnlPct: number // 今日收益率 %
  totalPnl: number // 累计盈亏
  totalPnlPct: number // 累计收益率 %
}

export interface Strategy {
  id: string
  name: string
  type: StrategyType
  symbol: string
  status: StrategyStatus
  pnl: number // 累计盈亏 USDT
  pnlPct: number // 收益率 %
  investment: number // 投入本金
  runningDays: number
  createdAt: string
  timeframe?: string
  // 网格参数（type === "grid" 时有效）
  grid?: GridParams
}

export interface GridParams {
  upperPrice: number
  lowerPrice: number
  gridCount: number
  perGridProfit: number // 每格利润率 %
  filledGrids: number // 已成交网格数
  arbitrageCount: number // 套利次数
}


export interface Position {
  id: string
  symbol: string
  side: Side
  size: number // 持仓数量
  entryPrice: number // 开仓均价
  markPrice: number // 标记价格
  leverage: number // 杠杆倍数
  margin: number // 占用资金
  liquidationPrice: number // 强平价（现货为 0）
  unrealizedPnl: number
  unrealizedPnlPct: number
  strategyName: string
}

export interface Order {
  id: string
  time: string
  symbol: string
  side: Side
  type: "limit" | "market"
  price: number
  amount: number
  filled: number // 已成交数量
  status: OrderStatus
  strategyName: string
  fee: number
}

/** 订单全量聚合统计（不随分页变化） */
export interface OrdersStats {
  total_orders: number
  filled_count: number
  open_count: number
  partially_filled_count: number
  canceled_count: number
  total_fee: number
}

/** 订单分页响应（GET /orders?limit=&offset=） */
export interface OrdersPage {
  items: Order[]
  total: number
  limit: number
  offset: number
  has_more: boolean
  stats: OrdersStats
}

export interface AssetBalance {
  asset: string
  total: number
  available: number
  inOrder: number
  valueUsdt: number
  allocationPct: number
}

export interface Ticker {
  symbol: string
  price: number
  changePct: number // 24h 涨跌幅 %
  volume: number // 24h 成交额
  high: number
  low: number
}

export interface PnlPoint {
  date: string
  equity: number // 账户权益
  pnl: number // 当日盈亏
  cumulativePnl: number // 累计盈亏
}

export interface StrategyPerformance {
  name: string
  pnl: number
  trades: number
  winRate: number // 胜率 %
}

// ---------------------------------------------------------------------------
// 多策略框架
// ---------------------------------------------------------------------------
export interface MultiStrategySummary {
  totalRealizedPnl: number
  totalClosedTrades: number
  strategiesCount: number
  strategies: MultiStrategySlot[]
}

export interface MultiStrategySlot {
  strategy_id: string
  symbol: string
  strategy_name: string
  realized_pnl: number
  open_lots: number
  open_position: number
  closed_trades: number
  bars_processed: number
}

export interface MultiStrategyDetail {
  strategyId: string
  symbol: string
  realizedPnl: number
  totalTrades: number
  winRate: number
  openLots: number
  closedTrades: number
}

// ---------------------------------------------------------------------------
// 单策略完整运行结果（GET /multi/strategy/{id}）
// 对应后端 src/execution/paper_trading_runner.py::_build_result
// ---------------------------------------------------------------------------
export interface StrategyStatistics {
  initial_balance: number
  current_balance: number
  total_trades: number
  total_commission: number
  total_slippage: number
  total_cost: number
  positions: Record<string, number>
}

/** 单笔已平仓交易（PaperTradingRunner.closed_trades） */
export interface ClosedTrade {
  tag: string
  time: string
  profit: number
}

/** 单笔成交记录（PaperBroker.orders 条目） */
export interface BrokerOrder {
  order_id: string
  timestamp: string
  symbol: string
  side: Side
  order_type: "market" | "limit"
  amount: number
  price: number
  commission: number
  slippage: number
  tag?: string
  status?: "filled" | "pending" | "canceled"
}

/** 策略产生的信号日志条目 */
export interface StrategySignal {
  timestamp: string
  action: "buy" | "sell" | "hold"
  reason?: string
  [key: string]: unknown
}

export interface MultiStrategyResult {
  symbol: string
  statistics: StrategyStatistics
  trade_history: BrokerOrder[]
  signals: StrategySignal[]
  open_lots: Record<string, number>
  realized_pnl: number
  closed_trades: ClosedTrade[]
}

// 创建策略请求参数
export interface CreateGridParams {
  symbol: string
  lowerPrice: number
  upperPrice: number
  gridCount: number
  investment: number
}

// ---------------------------------------------------------------------------
// AI Agent 分析（POST /agent/analyze, GET /agent/audit-logs, GET /agent/adoption-rate）
// 对应后端 src/agent/analyzer.py 与 src/agent/audit_log.py
// ---------------------------------------------------------------------------
export type AgentTask =
  | "backtest"
  | "trade_attribution"
  | "risk_checklist"
  | "param_sensitivity"
  | "weekly_review"

/** AI 分析统一返回结构（analyzer.py 顶部约定的输出格式） */
export interface AgentAnalysisResult {
  analysis: string
  reasoning: string
  recommendation: string
  risks?: string[]
  requires_human_approval: boolean
  confidence: number
  // 各 task 可能附带额外字段，保留透传
  [key: string]: unknown
}

/** 审计日志条目（AuditLog.record 写入结构） */
export interface AgentAuditLogEntry {
  id: string
  timestamp: string
  phase: string
  task: AgentTask
  input_summary: Record<string, unknown>
  output_summary: Record<string, unknown>
  model: string
  tokens_used: number
  human_approved: boolean
  action_taken: string | null
}

/** 采纳率统计（AuditLog.get_adoption_rate 返回结构） */
export interface AgentAdoptionRate {
  total_calls: number
  approved: number
  adoption_rate: number
  task: string
}

// ---------------------------------------------------------------------------
// 风险指标（GET /account/risk-metrics / /risk/drawdown-curve / /risk/status）
// 对应后端 src/api/service.py::risk_metrics / drawdown_curve / risk_status
// ---------------------------------------------------------------------------
export interface RiskMetrics {
  max_drawdown: number         // 最大回撤（小数，如 -0.12）
  max_drawdown_pct: number     // 最大回撤（%，如 -12.0）
  sharpe_ratio: number         // 年化夏普
  sortino_ratio: number        // 年化 Sortino
  volatility: number           // 年化波动率（%）
  annual_return: number        // 年化收益率（%）
  current_drawdown: number     // 当前回撤（%，相对峰值，<= 0）
  equity_peak: number          // 权益峰值
  equity_current: number       // 当前权益
  max_drawdown_duration: number // 最大回撤持续 bar 数
}

export interface DrawdownPoint {
  date: string
  equity: number
  peak: number
  drawdown: number  // %
}

export type RiskState = "ACTIVE" | "PAUSED" | "STOPPED"

export interface RiskEvent {
  type: string
  reason: string
  state: RiskState
}

export interface RiskLimits {
  max_daily_loss: number
  max_consecutive_losses: number
  max_total_position: number
  max_total_drawdown: number
}

export interface RiskStatus {
  state: RiskState
  can_trade: boolean
  daily_pnl: number
  daily_loss_limit_pct: number
  daily_loss_used_pct: number
  consecutive_losses: number
  max_consecutive_losses: number
  cumulative_pnl: number
  total_drawdown_pct: number
  max_total_drawdown_pct: number
  events: RiskEvent[]
  limits: RiskLimits
  note?: string
}

// ---------------------------------------------------------------------------
// 持仓历史 / 盈亏分布
// ---------------------------------------------------------------------------
export interface ClosedTradeHistory {
  id: string
  strategy_id: string
  strategy_name: string
  symbol: string
  tag: string
  open_time: string
  close_time: string
  profit: number
  profit_pct: number
  hold_bars: number
}

export interface PnlDistributionBin {
  range: string
  count: number
  label: string  // "盈利" | "亏损" | "混合"
}

export interface PnlDistributionStats {
  total: number
  wins: number
  losses: number
  win_rate: number       // %
  avg_profit: number
  avg_loss: number
  profit_factor: number  // 盈亏比，可能为 Infinity
  best: number
  worst: number
}

export interface PnlDistribution {
  bins: PnlDistributionBin[]
  stats: PnlDistributionStats
}

// ---------------------------------------------------------------------------
// 胜率趋势 / 策略相关性
// ---------------------------------------------------------------------------
export interface WinRateTrendPoint {
  index: number
  close_time: string
  win_rate: number   // %
  strategy_id: string
}

export interface StrategyCorrelation {
  strategies: string[]
  labels: string[]
  matrix: number[][]  // N×N
}

// ---------------------------------------------------------------------------
// 运行模式（GET /modes, POST /modes/{mode}/start, WS /ws/logs/{mode}）
// 对应后端 src/api/mode_manager.py
// ---------------------------------------------------------------------------
export type RunningMode = "data_download" | "replay_paper" | "live_paper" | "testnet_live"
export type ModeStatusValue = "idle" | "running" | "stopping" | "error"

export interface ModeState {
  mode: RunningMode
  status: ModeStatusValue
  pid: number | null
  startedAt: string | null
  uptimeSeconds: number | null
  exitCode: number | null
  lastLogLine: string | null
  params: Record<string, unknown> | null
}

export interface StartModeParams {
  symbol?: string
  timeframe?: string
  days?: number
  initialCapital?: number
  pollSeconds?: number
  replayCsv?: string
  fresh?: boolean
  strategies?: string[]
}

export interface TestnetValidationCheck {
  name: string
  status: "PASS" | "FAIL" | "WARN"
  detail: string
}

export interface TestnetValidationResult {
  ok: boolean
  checks: TestnetValidationCheck[]
}

// ---------------------------------------------------------------------------
// 策略 AI 进化（POST /agent/evolve, GET /agent/evolution-history, GET /agent/evolution-stats）
// 对应后端 src/agent/evolution_engine.py
// ---------------------------------------------------------------------------

export interface EvolutionResult {
  strategy_id: string
  strategy_name: string
  old_params: Record<string, number>
  new_params: Record<string, number> | null
  old_metrics: Record<string, number>
  new_metrics: Record<string, number> | null
  guardrail_passed: boolean
  guardrail_reasons: string[]
  llm_interpretation: {
    summary: string
    reasoning: string
    risks: string
    confidence: number
    recommendation: "apply" | "reject" | "caution"
    provider: string
  } | null
  applied: boolean
  timestamp: string
  walk_forward_windows: number
}

export interface EvolveRequest {
  strategy_ids?: string[]
  auto_apply: boolean
}

export interface EvolutionHistoryResponse {
  items: EvolutionResult[]
  total: number
  stats: EvolutionStats
}

export interface EvolutionStats {
  total_evolutions: number
  applied_count: number
  avg_sharpe_improvement: number
}

// ---------------------------------------------------------------------------
// 策略注册表 / 通用创建 / 运行历史
// ---------------------------------------------------------------------------

/** PARAM_SCHEMA 中单个参数的约束 */
export interface ParamConstraint {
  type?: string          // "int" | "float" | "bool"（后端序列化后的字符串）
  min?: number
  max?: number
}

/** 策略注册表中每个策略的注册信息 */
export interface StrategyRegistryEntry {
  key: StrategyType
  name: string           // 中文标签
  description: string
  param_schema: Record<string, ParamConstraint>
  defaults: Record<string, number | boolean>
  running: boolean
  instances: number
}

export interface StrategyRegistryResponse {
  strategies: StrategyRegistryEntry[]
}

/** 通用策略创建请求 */
export interface CreateStrategyParams {
  type: StrategyType
  symbol: string
  investment: number
  timeframe?: string
  params: Record<string, number | boolean>
}

/** 策略运行历史条目 */
export interface StrategyRunEntry {
  id: string
  strategy_id: string
  symbol: string
  mode: string
  timeframe: string
  initial_capital: number | null
  status: string
  started_at: string
  ended_at: string
  final_equity: number | null
  realized_pnl: number | null
  total_return: number | null
  config: Record<string, unknown>
}

export interface StrategyRunHistoryResponse {
  items: StrategyRunEntry[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

/** 数据清理响应 */
export interface DataCleanupResult {
  runs_deleted: number
  evolutions_deleted: number
  audit_deleted: number
  error?: string
}
