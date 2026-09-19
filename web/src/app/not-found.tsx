import Link from "next/link"

import { RivonMark } from "@/components/brand/logo"
import { Button } from "@/components/ui/button"

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 px-4 text-center">
      <RivonMark className="size-10" />
      <h1 className="text-2xl">Page not found</h1>
      <p className="max-w-sm text-sm text-muted-foreground">
        It may have been moved, or belongs to another account.
      </p>
      <Button asChild>
        <Link href="/dashboard">Back to overview</Link>
      </Button>
    </main>
  )
}
