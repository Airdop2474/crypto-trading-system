/**
 * 自定义 404 页面（Next.js App Router 约定文件）。
 *
 * 替代 Next.js 默认 404，提供与系统一致的暗色主题风格。
 * 参考：https://nextjs.org/docs/app/api-reference/file-conventions/not-found
 */

import Link from "next/link"
import { Button } from "@/components/ui/button"

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
      <p className="font-mono text-6xl font-bold text-muted-foreground">404</p>
      <div className="space-y-1">
        <h1 className="text-xl font-semibold text-foreground">页面不存在</h1>
        <p className="text-sm text-muted-foreground">
          您访问的页面可能已被移除或地址有误。
        </p>
      </div>
      <Button render={<Link href="/" />}>返回首页</Button>
    </div>
  )
}
