"use client"

import { AlertTriangle } from "lucide-react"

import { Button } from "@/components/ui/button"

export default function AppError({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="flex flex-col items-center gap-4 py-24 text-center">
      <AlertTriangle className="size-8 text-muted-foreground" />
      <h1 className="text-xl">Something went wrong loading this page</h1>
      <p className="max-w-sm text-sm text-muted-foreground">
        Rivon couldn&apos;t reach its service just now. Your data is safe.
      </p>
      <Button onClick={reset}>Try again</Button>
    </div>
  )
}
