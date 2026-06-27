/**
 * Binance API 反代 Cloudflare Worker
 *
 * 用途：美国 IP 访问 Binance 被地域限制（HTTP 451），用 Cloudflare Worker 中转。
 * Cloudflare 出口 IP 不在美国，且全球边缘节点就近访问。
 *
 * 部署方法见 docs/BINANCE_PROXY_SETUP.md
 *
 * 支持两类流量：
 * 1. REST API（ccxt 覆盖 urls["api"]）
 *    - /testnet/* → testnet.binance.vision/*  (testnet 私有接口，带 API Key)
 *    - /main/*    → api.binance.com/*          (主网公开行情/私有接口)
 * 2. WebSocket 实时行情
 *    - /main/ws/* → wss://stream.binance.com:9443/ws/*  (Cloudflare 原生支持 WS 代理)
 *
 * 注意：ccxt set_sandbox_mode(true) 会把 urls["api"] 设为 testnet 的域名路径，
 * 我们再覆盖为 Worker URL + 原路径，所以 Worker 只需透传即可。
 */

const UPSTREAM_MAP = {
  "testnet.binance.vision": "testnet.binance.vision",
  "api.binance.com": "api.binance.com",
  "testnet.binancefuture.com": "testnet.binancefuture.com",
  // WebSocket 上游
  "stream.binance.com": "stream.binance.com",
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

    // WebSocket 升级请求：/main/ws/* → wss://stream.binance.com:9443/ws/*
    // Cloudflare Worker 原生支持 WebSocket 代理，只需返回 fetch 结果即可
    const wsMatch = url.pathname.match(/^\/(testnet|main)\/ws\/(.*)$/);
    if (wsMatch && request.headers.get("upgrade") === "websocket") {
      const wsPath = "/ws/" + wsMatch[2];
      const upstreamWsUrl = `wss://stream.binance.com:9443${wsPath}`;
      // Cloudflare Worker 通过 fetch websocket 升级自动代理 WS
      const resp = await fetch(upstreamWsUrl, request);
      return resp;
    }

    // REST API 透传
    let upstreamHost = request.headers.get("x-upstream-host") || "api.binance.com";

    // 按路径前缀判断上游：/testnet/* → testnet.binance.vision，/main/* → api.binance.com
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
