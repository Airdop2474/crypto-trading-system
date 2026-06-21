/** @type {import('next').NextConfig} */

// 后端 API 基址，CSP connect-src 需要放行其 REST 与 WS 升级端点。
// 默认 http://localhost:8000（与代码内 fallback 一致）。
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"

/**
 * 解析 API_BASE 的 origin（去掉路径），用于 CSP connect-src。
 * 例如 http://localhost:8000 -> http://localhost:8000
 */
function apiOrigin(base) {
  try {
    return new URL(base).origin
  } catch {
    return base
  }
}

/**
 * 由 API origin 推导对应的 WS origin（http <-> ws, https <-> wss）。
 */
function wsOrigin(httpOrigin) {
  return httpOrigin.replace(/^http/, "ws")
}

const REST_ORIGIN = apiOrigin(API_BASE)
const WS_ORIGIN = wsOrigin(REST_ORIGIN)
const isDev = process.env.NODE_ENV !== "production"

// connect-src 放行：自身（'self'）、后端 REST、后端 WS、以及开发期 Next.js HMR。
const connectSrc = [
  "'self'",
  REST_ORIGIN,
  WS_ORIGIN,
  // Next.js dev server HMR（仅开发期需要）
  ...(isDev ? ["ws://localhost:3000", "http://localhost:3000"] : []),
].join(" ")

const nextConfig = {
  typescript: {
    ignoreBuildErrors: false,
  },
  images: {
    unoptimized: true, // 纯仪表盘应用，无外部图片加载
  },
  // 安全响应头
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'X-DNS-Prefetch-Control', value: 'on' },
          // F-04: Content-Security-Policy —— XSS 防线核心
          // - default-src 'self'：默认仅允许同源
          // - script-src 'self' + 'unsafe-inline'：Next.js 运行时需要 inline 脚本
          // - style-src 'self' 'unsafe-inline'：Tailwind / CSS-in-JS 内联样式
          // - img-src 'self' data:：允许 data URI 图标/占位图
          // - connect-src：REST + WS（见上方 connectSrc 构造）
          // - font-src 'self'：next/font 自托管字体
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data:",
              `connect-src ${connectSrc}`,
              "font-src 'self'",
              "frame-ancestors 'none'",
              "base-uri 'self'",
              "form-action 'self'",
            ].join('; '),
          },
        ],
      },
    ]
  },
}

export default nextConfig
