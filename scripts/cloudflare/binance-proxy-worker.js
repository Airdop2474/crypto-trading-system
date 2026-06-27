/**
 * Binance API 反代 Cloudflare Worker
 *
 * 用途：美国 IP 访问 Binance 被地域限制（HTTP 451），用 Cloudflare Worker 中转。
 * Cloudflare 出口 IP 不在美国，且全球边缘节点就近访问。
 *
 * 部署方法见 docs/BINANCE_PROXY_SETUP.md
 *
 * 原理：
 * - ccxt 把 self.exchange.urls["api"] 改为 https://<worker>.workers.dev + 原路径
 * - Worker 收到请求后，按路径前缀判断上游域名（testnet 还是主网），转发请求
 * - testnet 路径含 /api/v3 或 /sapi/v1 或 /wapi/v3 → testnet.binance.vision
 * - 主网路径同前缀 → api.binance.com
 *
 * 注意：ccxt set_sandbox_mode(true) 会把 urls["api"] 设为 testnet 的域名路径，
 * 我们再覆盖为 Worker URL + 原路径，所以 Worker 只需透传即可。
 */

const UPSTREAM_MAP = {
  // testnet（set_sandbox_mode(true) 后 ccxt 用的域名）
  "testnet.binance.vision": "testnet.binance.vision",
  // 主网
  "api.binance.com": "api.binance.com",
  // testnet futures/data
  "testnet.binancefuture.com": "testnet.binancefuture.com",
};

export default {
  async fetch(request) {
    const url = new URL(request.url);

    // 健康检查（无需转发）
    if (url.pathname === "/" || url.pathname === "/health") {
      return new Response(JSON.stringify({ status: "ok", service: "binance-proxy" }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    // 从查询参数 target 提取上游域名（ccxt 反代 URL 配置时拼接），
    // 或默认走主网。实际部署中 ccxt 会把完整路径发过来，
    // 我们用请求头 x-upstream-host 指定上游（在 exchange_broker.py 中设置）。
    // 简化方案：直接按 path 判断，所有请求默认转发到主网。
    let upstreamHost = request.headers.get("x-upstream-host") || "api.binance.com";

    // testnet 标识：ccxt set_sandbox_mode 不会改 path，但 exchange.urls["api"]
    // 在 broker 中被覆盖前已是 testnet 路径。我们无法仅凭 path 区分，
    // 所以采用更可靠方案：在 Worker 路径中编码上游。
    // 见 docs/BINANCE_PROXY_SETUP.md，broker 配置时传 https://worker/testnet/ 或 https://worker/main/
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

    // 构造上游请求
    const upstreamUrl = `https://${upstreamHost}${url.pathname}${url.search}`;
    const headers = new Headers(request.headers);
    headers.delete("x-upstream-host");
    headers.set("Host", upstreamHost);
    // 保留 X-MBX-APIKEY（Binance API 认证头）
    // headers 已自动复制

    const upstreamReq = new Request(upstreamUrl, {
      method: request.method,
      headers: headers,
      body: request.method !== "GET" && request.method !== "HEAD" ? request.body : undefined,
      redirect: "manual",
    });

    try {
      const resp = await fetch(upstreamReq);
      // 转发响应，移除可能引起 CORS 问题的头
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
