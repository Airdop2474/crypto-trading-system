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

## 部署步骤（浏览器操作）

### 步骤 1：登录 Cloudflare

1. 浏览器访问 https://dash.cloudflare.com/login
2. 输入邮箱和密码登录
3. 如无账号，先访问 https://dash.cloudflare.com/sign-up 注册（只需邮箱+密码，无需信用卡）

### 步骤 2：进入 Workers 创建页面

1. 登录后，左侧主菜单找到 **Compute (Workers)** 或 **计算和 AI**（2026 新版菜单名）
   - 旧版菜单名为 **Workers & Pages**
2. 点击进入该板块
3. 点击页面右上角 **Create application** / **创建应用程序** 按钮
4. 弹出页面会显示多个选项：
   - Connect to GitHub
   - Connect to GitLab
   - **Start with Hello World** ← 选这个
   - Select a template
   - Upload your static files
5. 点击 **Start with Hello World**

### 步骤 3：创建 Worker（第一次 Deploy）

1. 进入创建页面后，会看到 Worker 名称输入框
2. 修改名称为 `binance-proxy`（或任意名字，仅影响 URL 子域名）
3. **直接点击 Deploy 按钮**（这次只创建 Hello World 模板，不改代码）
4. 等待几秒，看到 "Deployment successful" / "部署成功" 提示
5. 此时 Worker URL 已生成，格式为：`https://binance-proxy.<你的子域名>.workers.dev`
6. **复制并保存这个 URL**（下一步要用）

### 步骤 4：编辑代码（关键步骤）

1. 部署成功后，在 Worker 概览页找 **Edit code** / **编辑代码** 按钮
   - 通常在页面右上角或顶部
   - 也可能叫 **Quick edit** / **快速编辑**
2. 点击进入在线代码编辑器
3. 编辑器左侧会看到默认的 Hello World 代码（通常是 `worker.js` 文件）
4. **全选删除**编辑器里的默认代码：
   - Windows：`Ctrl+A` 然后 `Delete`
   - Mac：`Cmd+A` 然后 `Delete`
5. **粘贴下面的反代代码**（完整复制，从 `/**` 到 `};` 结束）：

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

6. 粘贴后**检查编辑器第一行**，应该是 `/**`，**不应该是** `scripts/cloudflare/...`
7. 点击右上角 **Deploy** / **Save and deploy** 按钮
8. 等待几秒，看到部署成功提示

### 步骤 5：验证 Worker

在浏览器新标签页访问以下地址（替换为你的实际 URL）：

**5.1 健康检查**
```
https://binance-proxy.<你的子域名>.workers.dev/health
```
期望返回：
```json
{"status":"ok","service":"binance-proxy"}
```

**5.2 测试 testnet 透传**
```
https://binance-proxy.<你的子域名>.workers.dev/testnet/api/v3/ping
```
期望返回：`{}`（Binance testnet ping 响应）

**5.3 测试主网透传**
```
https://binance-proxy.<你的子域名>.workers.dev/main/api/v3/ping
```
期望返回：`{}`（Binance 主网 ping 响应）

如果 5.2 和 5.3 都返回 `{}`，说明反代工作正常。如果返回 451 或 502，检查 Worker 代码是否完整粘贴。

### 步骤 6：配置 VPS .env

SSH 登录 VPS 后：

```bash
cd /root/crypto-trading-system
git pull origin master
nano .env
```

在 `.env` 文件末尾添加一行（替换为你的实际 Worker URL）：

```env
BINANCE_PROXY_URL=https://binance-proxy.<你的子域名>.workers.dev
```

**注意事项**：
- URL 不要带尾部斜杠 `/`
- 不要带 `/testnet` 或 `/main` 后缀（代码会自动拼接）
- 保存退出 nano：`Ctrl+O` 回车 `Ctrl+X`

### 步骤 7：重启服务并验证

```bash
# 重启后端服务
docker compose restart trading_system paper_daemon

# 检查日志确认走了反代
docker compose logs --tail 50 trading_system | grep "反代"
```

期望看到日志：
```
Binance API 通过反代访问: https://binance-proxy.xxx.workers.dev/testnet
```

### 步骤 8：测试 API 连通性

```bash
# API 健康检查（替换 <API_TOKEN> 为 .env 中的值）
curl http://localhost:8000/health/detailed -H "X-API-Token: <API_TOKEN>"
```

期望看到 connectivity 字段为 PASS。

---

## 完整 Worker 代码（备份）

如需本地查看完整代码，见仓库文件：[scripts/cloudflare/binance-proxy-worker.js](file:///c:/Github/crypto-trading-system/scripts/cloudflare/binance-proxy-worker.js)

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

我们在 [src/execution/exchange_broker.py](file:///c:/Github/crypto-trading-system/src/execution/exchange_broker.py) 中把 `urls["api"]` 的每个值改为：
```
https://<worker>/testnet/api/v3
https://<worker>/testnet/sapi/v1
...
```

这样所有 ccxt 请求都会发到 Worker，Worker 再转发到 testnet.binance.vision。

### market.py 公共行情

[src/api/market.py](file:///c:/Github/crypto-trading-system/src/api/market.py) 的公共行情不需要 API Key，走主网拿真实价格，所以用 `/main` 前缀。

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
| `scripts is not defined` | 把文件路径当代码粘贴 | 复制代码内容本身，不是文件路径 |

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
