"use client"

import { useRouter } from "next/navigation"
import { LogOut } from "lucide-react"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import type { Me } from "@/lib/api/types"

const ROLE_LABEL = { owner: "Owner", manager: "Manager", agent: "Agent" } as const

export function UserMenu({ me }: { me: Me }) {
  const router = useRouter()

  async function signOut() {
    await fetch("/api/auth/logout", { method: "POST" })
    router.replace("/login")
    router.refresh()
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="h-auto w-full justify-start gap-3 px-2 py-2">
          <Avatar className="size-8">
            <AvatarFallback className="bg-muted text-xs">{me.email.slice(0, 2).toUpperCase()}</AvatarFallback>
          </Avatar>
          <span className="min-w-0 flex-1 text-left">
            <span className="block truncate text-sm font-medium">{me.email}</span>
            <span className="block text-xs text-muted-foreground">{ROLE_LABEL[me.role]}</span>
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-60">
        <DropdownMenuLabel className="font-normal">
          <span className="block truncate text-sm">{me.email}</span>
          <span className="block text-xs text-muted-foreground">
            {ROLE_LABEL[me.role]} · data hosted in the {me.region === "eu" ? "EU" : "non-EU region"}
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={signOut}>
          <LogOut /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
