import Link from "next/link"

import { MobileNav } from "@/components/app-shell/mobile-nav"
import { SidebarNav } from "@/components/app-shell/sidebar-nav"
import { UserMenu } from "@/components/app-shell/user-menu"
import { RivonLogo } from "@/components/brand/logo"
import { getMe, getProfile } from "@/lib/api/server"

export default async function AppLayout({ children }: LayoutProps<"/">) {
  const [me, profile] = await Promise.all([getMe(), getProfile()])
  const businessName = profile?.name ?? "Your business"

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[256px_1fr]">
      <aside className="sticky top-0 hidden h-screen flex-col border-r bg-sidebar px-3 py-4 lg:flex">
        <Link href="/dashboard" className="mb-6 px-2">
          <RivonLogo />
        </Link>
        <p className="mb-4 truncate px-3 text-sm font-medium" title={businessName}>
          {businessName}
        </p>
        <div className="flex-1 overflow-y-auto">
          <SidebarNav />
        </div>
        <div className="border-t pt-3">
          <UserMenu me={me} />
        </div>
      </aside>

      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-40 flex h-14 items-center gap-2 border-b bg-background/95 px-4 backdrop-blur lg:hidden">
          <MobileNav />
          <Link href="/dashboard">
            <RivonLogo markClassName="size-7" />
          </Link>
        </header>
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-10">
          <div className="mx-auto w-full max-w-5xl">{children}</div>
        </main>
      </div>
    </div>
  )
}
