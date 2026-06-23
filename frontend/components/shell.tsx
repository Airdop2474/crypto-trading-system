import type { ReactNode } from "react"
import { AppSidebar } from "@/components/app-sidebar"
import { MobileNav } from "@/components/mobile-nav"
import { TopBar } from "@/components/top-bar"

export function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-svh overflow-hidden">
      <AppSidebar />
      <div className="flex min-w-0 flex-1 flex-col overflow-y-auto">
        <TopBar />
        <main className="flex-1 p-4 md:p-6">{children}</main>
      </div>
      <MobileNav />
    </div>
  )
}
