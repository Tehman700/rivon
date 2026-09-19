"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

import { NAV_SECTIONS } from "./nav"

export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname()
  return (
    <nav aria-label="Main" className="space-y-6">
      {NAV_SECTIONS.map((section) => (
        <div key={section.title} className="space-y-1">
          <p className="px-3 pb-1 text-xs text-muted-foreground">{section.title}</p>
          {section.items.map(({ href, label, icon: Icon, soon }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`)
            if (soon) {
              return (
                <span
                  key={href}
                  aria-disabled
                  className="flex h-9 items-center gap-3 rounded-md px-3 text-sm text-muted-foreground/70"
                >
                  <Icon className="size-4" />
                  <span className="flex-1">{label}</span>
                  <Badge variant="outline" className="text-[0.7rem] font-normal">
                    Soon
                  </Badge>
                </span>
              )
            }
            return (
              <Link
                key={href}
                href={href}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex h-9 items-center gap-3 rounded-md px-3 text-sm transition-colors",
                  active
                    ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                    : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
                )}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            )
          })}
        </div>
      ))}
    </nav>
  )
}
