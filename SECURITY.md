# 安全策略

本文档说明 crypto-trading-system 的安全策略、已实现的安全控制，以及漏洞报告流程。

## 支持的版本

项目目前处于 Paper Trading 阶段（实盘 Live Broker 尚未实现），主线开发在 `master` 分支。安全修复仅针对 `master` 最新提交。

## 报告漏洞

如发现安全漏洞，请**不要**公开提交 issue。请通过以下方式私下报告：

- 在 GitHub 仓库使用 **Security Advisory**（Security → Report a vulnerability），或
- 直接联系仓库维护者（见仓库 collaborator 列表）

报告请尽量包含：受影响的文件/端点、复现步骤、潜在影响。维护者会在确认后协调修复与披露时间。

## 已实现的安全控制

以下控制已在代码中落地（截至 2026-06-20）：

| 领域 | 控制 | 位置 |
|------|------|------|
| API 认证 | 所有受保护端点要求 `X-API-Token`；`config.validate()` 中空 `API_TOKEN` 触发 CRITICAL | `src/api/app.py`、`src/utils/config.py` |
| WebSocket 认证 | 首条消息认证（10s 超时 + `secrets.compare_digest` 常量时间比较） | `src/api/app.py`、`src/api/ws_feed.py` |
| 限流 | 全局 slowapi 限速 + Agent 端点更严格配额 | `src/api/app.py` |
| 传输安全头 | `Content-Security-Policy`、`Strict-Transport-Security`（HSTS） | `src/api/app.py` |
| 实盘门禁 | `LIVE_TRADING_ENABLED` 默认 `false`；开发环境启用实盘直接拒启 | `src/utils/config.py`、`scripts/start_live_trading.py` |
| 交易所沙盒 | `BINANCE_TESTNET=true` 时强制 `set_sandbox_mode`，请求打 testnet 而非主网 | `src/execution/exchange_broker.py` |
| 订单护栏 | 单笔名义额上限 / 最小下单间隔 / 日订单数限制 | `src/execution/order_guard.py` |
| AI 边界 | Agent 为纯规则引擎，无外呼、无 API key、不自动执行交易 | `src/agent/analyzer.py`、`docs/standards/AI_USAGE_BOUNDARIES.md` |
| 并发安全 | RiskManager 与 psycopg2 游标加锁 | `src/execution/risk_manager.py`、`src/utils/database.py` |

## 密钥与凭据管理

- **切勿提交 `.env`**：仅提交 `.env.example` 模板；`.env` 已在 `.gitignore` 中。CI 含 gitleaks 扫描与 `.env` 未提交检查。
- **API Key 权限最小化**：交易所 API key 必须禁用提币权限；接主网前用 `scripts/verify_api_key_permissions.py` 校验。
- **生产密码**：`POSTGRES_PASSWORD` / `TIMESCALE_PASSWORD` / `REDIS_PASSWORD` 等必须改掉默认占位值（详见 `docs/reference/ENV_VARIABLE_REFERENCE.md`）。

## 已知限制

- **前端 `NEXT_PUBLIC_API_TOKEN` 客户端可见**：浏览器 DevTools 可读取，仅适用于 localhost / 受信网络部署；公网部署需改用服务端代理或会话方案。
- **`/health` 与 `/ws/tickers` 未鉴权**：分别用于存活探针和公开行情推送，不暴露敏感数据。
- **生产 TLS**：应用本身以 HTTP 监听，生产环境须在反向代理（Nginx/Caddy）层终止 TLS（见 `docs/DEPLOYMENT.md`）。

## 安全审计

项目已进行 OWASP + STRIDE 维度的安全审查，审查产物见 `deliverables/` 与 `.gstack/` 目录。
