/**
 * 路由级加载占位（Next.js App Router 约定文件）。
 *
 * 在路由段加载期间（包括首次进入与刷新）显示骨架屏，避免白屏。
 * 复用项目已有的 PageSkeleton 组件，与 Overview 等页面加载风格一致。
 *
 * 参考：https://nextjs.org/docs/app/api-reference/file-conventions/loading
 */

import { PageSkeleton } from "@/components/skeleton"

export default function Loading() {
  return (
    <div className="p-4">
      <PageSkeleton statCards={4} charts={2} tableRows={5} />
    </div>
  )
}
