# v1.0 部署清单 — Testnet Paper Trading

**版本**：v1.0
**日期**：2026-06-27
**架构**：VPS 跑后端（Docker） + 本地跑前端（npm run dev）

---

## 一、VPS 后端部署

### 前置条件
- [ ] VPS 已安装 Docker + Docker Compose
- [ ] 已在 Binance Testnet 创建 API Key（禁提币权限）
- [ ] 已创建 Telegram Bot（可选，用于告警通知）

### 步骤 1：VPS 安全加固（首次部署）

```bash
# SSH 登录 VPS（端口 14159）
ssh -p 14159 root@<VPS_IP>

# 克隆代码
git clone https://github.com/Airdop2474/crypto-trading-system.git /root/crypto-trading-system
cd /root/crypto-trading-system

# 执行安全加固（iptables + fail2ban + SSH + Docker 加速器）
bash scripts/vps_hardening.sh
```

**验证**：
- [ ] `iptables -L INPUT -n --line-numbers` 显示仅放行 14159/8000/3000
- [ ] `fail2ban-client status sshd` 显示 sshd jail 已启用
- [ ] `ssh -p 14159 root@localhost` 可连接

### 步骤 2：配置 .env

```bash
cd /root/crypto-trading-system
cp .env.example .env
nano .env
```

**必填项**：
- [ ] `BINANCE_API_KEY=` — Binance testnet API key
- [ ] `BINANCE_SECRET=` — Binance testnet secret
- [ ] `BINANCE_TESTNET=true` — 必须为 true（防误触主网）
- [ ] `API_TOKEN=` — 自动生成（deploy.sh 会生成），或手动 `openssl rand -hex 16`
- [ ] `POSTGRES_PASSWORD=` — 自动生成或手动设置
- [ ] `REDIS_PASSWORD=` — 自动生成或手动设置
- [ ] `GRAFANA_ADMIN_PASSWORD=` — 自动生成或手动设置

**地域限制相关**（VPS 在美国必填，其他地区可留空）：
- [ ] `BINANCE_PROXY_URL=` — Cloudflare Worker 反代 URL，绕过美国 IP 451 限制
  - 部署方法见步骤 3
  - 留空 = 直连 Binance（非美国 VPS 用）
  - 填写格式：`https://binance-proxy.<子域名>.workers.dev`（不带尾部斜杠和路径前缀）

**可选项**：
- [ ] `TELEGRAM_BOT_TOKEN=` — Telegram Bot Token（告警通知）
- [ ] `TELEGRAM_CHAT_ID=` — Telegram Chat ID
- [ ] `LLM_API_KEY=` — LLM API key（AI 策略优化）
- [ ] `LLM_BASE_URL=` — LLM API base URL

**记录 API_TOKEN**：部署后需同步到本地前端，务必记录。

### 步骤 3：部署 Binance API 反代（仅美国 VPS 需要）

> **背景**：美国 IP 访问 Binance（含 testnet 和主网）返回 HTTP 451 地域限制。用 Cloudflare Worker 中转，CF 边缘节点出口 IP 不在美国。免费额度 10 万请求/天，足够个人交易系统使用。
>
> **判断是否需要**：
> - VPS 在美国 → **必做此步骤**
> - VPS 在非美国地区（香港/日本/新加坡等）→ **跳过此步骤**，`BINANCE_PROXY_URL` 留空

#### 3.1 创建 Cloudflare Worker

1. 浏览器访问 https://dash.cloudflare.com/login 登录（无账号先注册，免费）
2. 左侧菜单找 **Compute (Workers)** 或 **计算和 AI**（旧版叫 Workers & Pages）
3. 点击 **Create application** → 选 **Start with Hello World**
4. 命名 Worker（如 `binance-proxy`）→ 点击 **Deploy**（先创建 Hello World 模板）
5. 部署后复制 Worker URL，格式：`https://binance-proxy.<子域名>.workers.dev`

#### 3.2 编辑 Worker 代码

1. 在 Worker 概览页点击 **Edit code**
2. 全选删除默认代码（`Ctrl+A` → `Delete`）
3. 粘贴以下代码（第一行应为 `/**`，不是文件路径）：

```javascript
/**
 * Binance API 反代 Cloudflare Worker
 */

const UPSTREAM_MAP = {
  "testnet.binance.vision": "testnet.binance.vision",
  "api.binance.com": "api.binance.com",
  "testnet.binancefuture.com": "testnet.binancefuture.com",
};

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname === "/" || url.pathname === "/health") {
      return new Response(JSON.stringify({ status: "ok", service: "binance-proxy" }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    let upstreamHost = request.headers.get("x-upstream-host") || "api.binance.com";

    const pathParts = url.pathname.match(/^\/(testnet|main)(\/.*)?$/);
    if (pathParts) {
      upstreamHost = pathParts[1] === "testnet" ? "testnet.binance.vision" : "api.binance.com";
      url.pathname = pathParts[2] || "/";
    }

    if (!UPSTREAM_MAP[upstreamHost]) {
      return new Response(JSON.stringify({
        error: "unknown upstream",
        host: upstreamHost,
      }), { status: 400, headers: { "Content-Type": "application/json" } });
    }

    const upstreamUrl = `https://${upstreamHost}${url.pathname}${url.search}`;
    const headers = new Headers(request.headers);
    headers.delete("x-upstream-host");
    headers.set("Host", upstreamHost);

    const upstreamReq = new Request(upstreamUrl, {
      method: request.method,
      headers: headers,
      body: request.method !== "GET" && request.method !== "HEAD" ? request.body : undefined,
      redirect: "manual",
    });

    try {
      const resp = await fetch(upstreamReq);
      const respHeaders = new Headers(resp.headers);
      respHeaders.set("Access-Control-Allow-Origin", "*");
      return new Response(resp.body, {
        status: resp.status,
        statusText: resp.statusText,
        headers: respHeaders,
      });
    } catch (e) {
      return new Response(JSON.stringify({
        error: "upstream_fetch_failed",
        detail: String(e),
      }), { status: 502, headers: { "Content-Type": "application/json" } });
    }
  },
};
```

4. 点击右上角 **Deploy**

#### 3.3 验证 Worker

浏览器访问以下三个 URL（替换为你的实际 URL），全部正确才说明反代生效：

| URL | 期望返回 |
|---|---|
| `https://<worker>.workers.dev/health` | `{"status":"ok","service":"binance-proxy"}` |
| `https://<worker>.workers.dev/testnet/api/v3/ping` | `{}` |
| `https://<worker>.workers.dev/main/api/v3/ping` | `{}` |

#### 3.4 配置 .env 并重启

回到 VPS：

```bash
cd /root/crypto-trading-system

# 写入 Worker URL（替换为你的实际 URL）
echo "BINANCE_PROXY_URL=https://binance-proxy.<子域名>.workers.dev" >> .env

# 验证写入
grep BINANCE_PROXY_URL .env
```

**验证**：
- [ ] Worker `/health` 返回 `{"status":"ok",...}`
- [ ] Worker testnet/main ping 都返回 `{}`
- [ ] VPS `.env` 中 `BINANCE_PROXY_URL` 已设置（不带尾部斜杠）
- [ ] VPS `.env` 中 `BINANCE_PROXY_URL` 不含 `/testnet` 或 `/main` 后缀（代码自动拼接）

**原理说明**：
- Worker 用路径前缀区分上游：`/testnet/*` → testnet.binance.vision，`/main/*` → api.binance.com
- ccxt 的 `urls["api"]` 被 [src/execution/exchange_broker.py](file:///c:/Github/crypto-trading-system/src/execution/exchange_broker.py) 改写为 `Worker URL + /testnet + 原路径`
- 公共行情走主网，用 `/main` 前缀（[src/api/market.py](file:///c:/Github/crypto-trading-system/src/api/market.py)）
- `BINANCE_PROXY_URL` 留空时保持直连，向后兼容

详细文档：[docs/BINANCE_PROXY_SETUP.md](file:///c:/Github/crypto-trading-system/docs/BINANCE_PROXY_SETUP.md)

### 步骤 4：启动后端服务

```bash
cd /root/crypto-trading-system

# 构建并启动所有服务
docker compose build
docker compose up -d

# 等待服务就绪（最多 60 秒）
sleep 10
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "✓ 后端服务已就绪"
        break
    fi
    sleep 2
done
```

**验证**：
- [ ] `docker compose ps` 显示 5 个服务全部 Up（trading_system + paper_daemon + timescaledb + redis + grafana）
- [ ] `curl http://localhost:8000/health` 返回 `{"status":"ok",...}`
- [ ] `curl http://localhost:8000/health/detailed -H "Authorization: Bearer <API_TOKEN>"` 返回详细状态
- [ ] 访问 `http://<VPS_IP>:3000` 看到 Grafana 登录页（用户名 admin，密码为 GRAFANA_ADMIN_PASSWORD）

### 步骤 5：启动 Paper Trading Daemon

```bash
# 通过 API 启动 paper trading 模式（推荐）
curl -X POST http://localhost:8000/modes/start \
  -H "Authorization: Bearer <API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"mode": "live_paper", "symbol": "BTC/USDT", "interval": "4h"}'
```

或通过 docker compose 直接启动 paper_daemon（已在 docker-compose.yml 中配置）。

**验证**：
- [ ] `docker compose logs paper_daemon -f --tail 20` 显示 daemon 正在运行
- [ ] `curl http://localhost:8000/modes/status -H "Authorization: Bearer <API_TOKEN>"` 显示 `live_paper` running
- [ ] 等待第一根 4h K 线收盘后，检查策略是否产生信号

---

## 二、本地前端配置

### 步骤 1：克隆代码

```bash
git clone https://github.com/Airdop2474/crypto-trading-system.git
cd crypto-trading-system/frontend
```

### 步骤 2：安装依赖

```bash
npm install
```

### 步骤 3：配置环境变量

创建 `frontend/.env.local`：

```env
NEXT_PUBLIC_API_BASE=http://<VPS_IP>:8000
NEXT_PUBLIC_API_TOKEN=<与 VPS .env 中 API_TOKEN 一致>
```

**关键**：`API_TOKEN` 必须与 VPS 后端 `.env` 中的 `API_TOKEN` 完全一致，否则前端请求会被 401 拒绝。

### 步骤 4：启动前端

```bash
npm run dev
```

**验证**：
- [ ] 访问 `http://localhost:3001` 看到仪表盘
- [ ] 仪表盘能加载策略列表（非空）
- [ ] 策略页面显示运行状态（绿色"运行中"标签）
- [ ] Portfolio Heat 卡片显示风控状态
- [ ] 下单/风控控制按钮可点击

---

## 三、上线后验证清单

### 核心功能
- [ ] 后端 `/health` 返回 ok
- [ ] 前端可加载策略列表
- [ ] Paper Trading daemon 正在运行
- [ ] 策略页面显示"运行中"
- [ ] Grafana 可访问且数据源已配置
- [ ] Telegram 告警可达（若配置了 bot）

### 风控验证
- [ ] `curl http://<VPS_IP>:8000/risk/status -H "Authorization: Bearer <TOKEN>"` 返回风控状态
- [ ] 测试急停：`POST /risk/control -d '{"action":"emergency_stop"}'`，确认 daemon 停止
- [ ] 测试恢复：`POST /risk/control -d '{"action":"resume"}'`，确认 daemon 恢复

### 资金安全验证（testnet）
- [ ] 检查 daemon 日志无"重复下单"告警
- [ ] 检查 `docker compose logs paper_daemon | grep "pending_query"` 无异常累积
- [ ] 检查持仓漂移对账：`docker compose logs paper_daemon | grep "持仓漂移"` 无熔断

---

## 四、常用运维命令

```bash
# 服务管理
docker compose ps                          # 查看服务状态
docker compose logs -f trading_system      # 实时日志
docker compose logs -f paper_daemon        # daemon 日志
docker compose restart trading_system      # 重启后端
docker compose down                        # 停止所有服务
docker compose up -d                       # 启动所有服务

# 更新代码
cd /root/crypto-trading-system
git pull origin master
docker compose up -d --build               # 重建并启动

# 数据库备份
bash scripts/backup_db.sh                  # 手动备份
# 或加到 crontab：0 3 * * * /root/crypto-trading-system/scripts/backup_db.sh

# 查看风控状态
curl http://localhost:8000/risk/status -H "Authorization: Bearer <TOKEN>"

# 紧急停止
curl -X POST http://localhost:8000/risk/control \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"action":"emergency_stop"}'
```

---

## 五、回滚步骤

### 代码回滚
```bash
cd /root/crypto-trading-system
git log --oneline -10                      # 查看最近提交
git checkout <previous_commit_hash>        # 回滚到上一个版本
docker compose up -d --build               # 重建
```

### 服务回滚（不回滚代码）
```bash
docker compose down                        # 停止所有服务
docker compose up -d                       # 用上一个镜像启动
```

### 数据回滚
```bash
# 从备份恢复
docker compose exec timescaledb psql -U postgres -d crypto_trading \
  -c "RESTORE DATABASE crypto_trading FROM '/backup/xxx.sql'"
```

---

## 六、故障排查

| 症状 | 可能原因 | 解决方案 |
|------|----------|----------|
| 前端 401 | API_TOKEN 不一致 | 检查 VPS .env 和本地 .env.local 的 API_TOKEN |
| 前端无法连接 | iptables 未开 8000 | `iptables -A INPUT -p tcp --dport 8000 -j ACCEPT` |
| daemon 不启动 | Binance Key 无效 | 检查 .env 中 BINANCE_API_KEY/SECRET |
| 仍报 HTTP 451 | 反代未配置或未生效 | 美国VPS必做步骤3，检查 BINANCE_PROXY_URL 和 Worker 健康状态 |
| ccxt DNS 错误 | BINANCE_PROXY_URL 格式错 | 不带尾部斜杠和 /testnet、/main 后缀 |
| Grafana 无数据 | 数据源未配置 | 检查 config/grafana/provisioning/datasources/ |
| 持仓漂移熔断 | 网络延迟导致订单未确认 | 检查 _unconfirmed 队列，等待对账 |
| 日志填满磁盘 | 日志轮转未生效 | 确认 loguru rotation=50MB，docker json-file 10m×3 |

---

## 七、联系方式与文档

- **部署文档**：`docs/DEPLOYMENT.md`
- **运维手册**：`docs/OPERATIONS_MANUAL.md`
- **故障排查**：`docs/TROUBLESHOOTING.md`
- **实盘清单**：`docs/LIVE_TRADING_CHECKLIST.md`
- **审查报告**：`deliverables/reviews/v1.0-testnet-paper-launch-review.md`
