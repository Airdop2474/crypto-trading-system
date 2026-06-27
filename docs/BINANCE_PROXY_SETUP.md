# Binance API 反代部署指南（Cloudflare Worker）

## 背景

美国 IP 访问 Binance（含 testnet `testnet.binance.vision` 和主网 `api.binance.com`）会被地域限制，返回 HTTP 451。

**解决方案**：用 Cloudflare Worker 做反代中转。CF 边缘节点出口 IP 不在美国，且免费额度（10万请求/天）足够个人交易系统使用。

---

## 架构

```
VPS (美国 IP) → Cloudflare Worker → Binance API (testnet/主网)
                   (非美国出口)
```

Worker 用路径前缀区分上游：
- `https://<worker>.workers.dev/testnet/*` → `testnet.binance.vision/*`
- `https://<worker>.workers.dev/main/*` → `api.binance.com/*`

---

## 部署步骤

### 1. 注册 Cloudflare 账号（免费）

访问 https://dash.cloudflare.com/sign-up 注册，无需绑定信用卡。

### 2. 创建 Worker

1. 登录 Cloudflare Dashboard → 左侧菜单 **Workers & Pages**
2. 点击 **Create application** → **Create Worker**
3. 命名（如 `binance-proxy`）→ 点击 **Deploy**
4. 部署后点击 **Edit code**

### 3. 粘贴 Worker 代码

把仓库中 `scripts/cloudflare/binance-proxy-worker.js` 的全部内容粘贴到编辑器，覆盖默认代码。

点击右上角 **Save and deploy**。

### 4. 获取 Worker URL

部署成功后，Worker URL 格式为：
```
https://binance-proxy.<你的子域名>.workers.dev
```

### 5. 验证 Worker

在浏览器或 curl 访问：
```bash
# 健康检查
curl https://binance-proxy.<你的子域名>.workers.dev/health
# 应返回: {"status":"ok","service":"binance-proxy"}

# 测试 testnet 透传
curl https://binance-proxy.<你的子域名>.workers.dev/testnet/api/v3/ping
# 应返回: {}

# 测试主网透传
curl https://binance-proxy.<你的子域名>.workers.dev/main/api/v3/ping
# 应返回: {}
```

### 6. 配置 .env

在 VPS 的 `/root/crypto-trading-system/.env` 中添加：

```env
BINANCE_PROXY_URL=https://binance-proxy.<你的子域名>.workers.dev
```

**注意**：URL 不要带尾部斜杠，不要带 `/testnet` 或 `/main` 后缀（代码会自动拼接）。

### 7. 重启服务

```bash
cd /root/crypto-trading-system
docker compose restart trading_system paper_daemon
```

### 8. 验证连通性

```bash
# 检查日志确认走了反代
docker compose logs trading_system | grep "反代"

# 测试 API 健康检查
curl http://localhost:8000/health/detailed -H "Authorization: Bearer <API_TOKEN>"
# 应看到 connectivity: PASS
```

---

## 工作原理

### ccxt URL 覆盖

ccxt 的 `exchange.urls["api"]` 是一个 dict，包含各 API 端点路径：
```python
{
    "public": "/api/v3",
    "private": "/sapi/v1",
    ...
}
```

设置 `set_sandbox_mode(True)` 后，ccxt 会把这些路径指向 testnet 域名。

我们在 `exchange_broker.py` 中把 `urls["api"]` 的每个值改为：
```
https://<worker>/testnet/api/v3
https://<worker>/testnet/sapi/v1
...
```

这样所有 ccxt 请求都会发到 Worker，Worker 再转发到 testnet.binance.vision。

### market.py 公共行情

公共行情不需要 API Key，走主网拿真实价格，所以用 `/main` 前缀。

---

## 免费额度说明

- Cloudflare Workers 免费版：**10万请求/天**
- Paper Trading daemon 每根 4h K 线触发一次，一天约 6 次
- 每次 daemon 调用约 5-10 个 API 请求（查余额/下单/查单）
- 一天约 60 请求，远低于限额
- 前端行情查询有 15 秒缓存，也不会超限

**结论**：免费额度完全够用。

---

## 故障排查

| 症状 | 可能原因 | 解决方案 |
|------|----------|----------|
| Worker 返回 502 | 上游 Binance 不可达 | 检查 Worker 代码是否最新，重试 |
| ccxt 报 DNS 错误 | Worker URL 错误 | 确认 URL 格式 `https://xxx.workers.dev`，无尾部斜杠 |
| 连接 testnet 但用主网 key | 反代前缀配错 | 确认 broker 用 `/testnet`，market 用 `/main` |
| 仍然 451 | Worker 未生效 | 检查 .env 的 BINANCE_PROXY_URL 是否正确，重启服务 |
| API 认证失败 | X-MBX-APIKEY 头未转发 | Worker 代码已处理，确认用最新版 |

---

## 安全说明

- Worker 不记录请求内容，只透传
- API Key 通过 HTTPS 传输，CF 不解密
- Worker URL 公开但无害（无 Key 无法操作账户）
- 如需进一步限制，可在 Worker 代码中加 `AUTH_TOKEN` 校验

---

## 备选方案（如有非美国 VPS）

如果有香港/日本/新加坡等地的 VPS，也可用 nginx 反代：
```nginx
location /binance/ {
    proxy_pass https://testnet.binance.vision/;
    proxy_set_header Host testnet.binance.vision;
}
```

但 Cloudflare Worker 方案更简单（无需额外服务器），推荐优先使用。
