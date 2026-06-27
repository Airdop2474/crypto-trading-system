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

// CORS headers applied to all REST responses
const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-MBX-APIKEY",
  "Access-Control-Max-Age": "86400",
};

/**
 * 清理转发给上游的 headers：移除 CF 注入头和 hop-by-hop 头，
 * 只保留业务相关头（Content-Type、X-MBX-APIKEY 等）。
 */
function cleanHeaders(originalHeaders, upstreamHost) {
  const h = new Headers();
  const BLOCKLIST = [
    // Cloudflare 注入头
    "cf-connecting-ip", "cf-ipcountry", "cf-ray", "cf-visitor",
    "cf-request-id", "cf-ew-via", "cdn-loop",
    // hop-by-hop 头
    "host", "connection", "upgrade",
    "sec-websocket-key", "sec-websocket-version",
    "sec-websocket-extensions", "sec-websocket-accept",
  ];
  for (const [key, value] of originalHeaders) {
    if (!BLOCKLIST.includes(key.toLowerCase())) {
      h.set(key, value);
    }
  }
  h.set("Host", upstreamHost);
  return h;
}

/**
 * WebSocket 代理：使用 WebSocketPair API 桥接客户端与上游。
 * 流程：接受客户端 WS → fetch 上游 WS → 管道双向数据转发。
 */
async function handleWebSocket(request, wsSubPath) {
  const upstreamUrl = `wss://stream.binance.com:9443/ws/${wsSubPath}`;
  const cleanH = cleanHeaders(request.headers, "stream.binance.com:9443");
  cleanH.set("Connection", "Upgrade");
  cleanH.set("Upgrade", "websocket");
  cleanH.set("Sec-WebSocket-Version", "13");
  // Sec-WebSocket-Key 由 fetch 自动生成

  // 1. 构造上游 WebSocket 连接
  const upstreamResp = await fetch(upstreamUrl, {
    headers: cleanH,
  });

  const upstreamWs = upstreamResp.webSocket;
  if (!upstreamWs) {
    return new Response("WebSocket proxy: upstream did not upgrade", { status: 502 });
  }

  // 2. 创建客户端 WebSocket 对
  const pair = new WebSocketPair();
  const [client, server] = [pair[0], pair[1]];

  // 3. 接受客户端连接
  server.accept();

  // 4. 双向管道：客户端 ↔ 上游
  //    任何一端出错只关闭，不抛异常（WS 代理常见断连场景）
  server.addEventListener("message", (event) => {
    try { upstreamWs.send(event.data); } catch (_) {}
  });
  server.addEventListener("close", () => {
    try { upstreamWs.close(); } catch (_) {}
  });
  server.addEventListener("error", () => {
    try { upstreamWs.close(); } catch (_) {}
  });

  upstreamWs.addEventListener("message", (event) => {
    try { server.send(event.data); } catch (_) {}
  });
  upstreamWs.addEventListener("close", () => {
    try { server.close(); } catch (_) {}
  });
  upstreamWs.addEventListener("error", () => {
    try { server.close(); } catch (_) {}
  });

  // 5. 返回客户端端 WebSocket（触发 HTTP 101 Switching Protocols）
  return new Response(null, {
    status: 101,
    webSocket: client,
  });
}

export default {
  async fetch(request) {
    // CORS preflight（浏览器跨域预检）
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    const url = new URL(request.url);

    // 健康检查（无需转发）
    if (url.pathname === "/" || url.pathname === "/health") {
      return new Response(JSON.stringify({ status: "ok", service: "binance-proxy" }), {
        headers: { "Content-Type": "application/json", ...CORS_HEADERS },
      });
    }

    // WebSocket 升级请求：/main/ws/* → wss://stream.binance.com:9443/ws/*
    const wsMatch = url.pathname.match(/^\/(testnet|main)\/ws\/(.*)$/);
    if (wsMatch && request.headers.get("upgrade") === "websocket") {
      return handleWebSocket(request, wsMatch[2]);
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
      }), { status: 400, headers: { "Content-Type": "application/json", ...CORS_HEADERS } });
    }

    // 构造上游请求（清理 CF 注入头，保留 X-MBX-APIKEY 认证头）
    const upstreamUrl = `https://${upstreamHost}${url.pathname}${url.search}`;
    const headers = cleanHeaders(request.headers, upstreamHost);

    const upstreamReq = new Request(upstreamUrl, {
      method: request.method,
      headers: headers,
      body: request.method !== "GET" && request.method !== "HEAD" ? request.body : undefined,
      redirect: "manual",
    });

    try {
      const resp = await fetch(upstreamReq);
      const respHeaders = new Headers(resp.headers);
      // 附加 CORS 头
      for (const [k, v] of Object.entries(CORS_HEADERS)) {
        respHeaders.set(k, v);
      }
      return new Response(resp.body, {
        status: resp.status,
        statusText: resp.statusText,
        headers: respHeaders,
      });
    } catch (e) {
      return new Response(JSON.stringify({
        error: "upstream_fetch_failed",
        detail: String(e),
      }), { status: 502, headers: { "Content-Type": "application/json", ...CORS_HEADERS } });
    }
  },
};
