"use client"

/**
 * BETA: where Meta returns the customer in the Page-picker flow.
 *
 * Must match RIVON_META_REDIRECT_URI_V2 and the App Dashboard exactly. It hands
 * the code and state to the API, which opens a picker session, then moves on to
 * the picker. The token never touches the browser.
 */

import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Suspense, useEffect, useRef, useState } from "react"
import { AlertTriangle, Loader2 } from "lucide-react"

import { RivonLogo } from "@/components/brand/logo"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ApiError, api } from "@/lib/api/client"
import type { PickerSession } from "@/lib/api/types"

function Inner() {
  const params = useSearchParams()
  const router = useRouter()
  const [apiFailure, setApiFailure] = useState<string | null>(null)
  // React runs effects twice in development, and the state is single use.
  const started = useRef(false)

  const code = params.get("code")
  const state = params.get("state")
  // What is wrong with the return itself is known on the first render.
  const returnFailure = params.get("error")
    ? params.get("error_reason") === "user_denied"
      ? "You cancelled before granting access, so nothing was connected."
      : (params.get("error_description") ?? "Facebook reported an error.")
    : !code || !state
      ? "Facebook did not send anything back."
      : null
  const failure = returnFailure ?? apiFailure

  useEffect(() => {
    if (started.current || returnFailure || !code || !state) return
    started.current = true
    api<PickerSession>("/channels/v2/callback", { method: "POST", body: { code, state } })
      .then(({ session_id }) => router.replace(`/channels/beta?session=${session_id}`))
      .catch((error) =>
        setApiFailure(error instanceof ApiError ? error.message : "The sign-in could not be completed."),
      )
  }, [code, state, returnFailure, router])

  if (!failure) {
    return (
      <CardContent className="flex items-center gap-3 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" /> Finding your Facebook Pages…
      </CardContent>
    )
  }
  return (
    <>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <AlertTriangle className="size-5 text-destructive" /> Not connected
        </CardTitle>
        <CardDescription>{failure}</CardDescription>
      </CardHeader>
      <CardContent>
        <Button asChild>
          <Link href="/channels/beta">Try again</Link>
        </Button>
      </CardContent>
    </>
  )
}

export default function MetaBetaCallbackPage() {
  return (
    <main className="mx-auto flex min-h-svh w-full max-w-lg flex-col justify-center px-4 py-16">
      <RivonLogo className="mb-6 self-start" />
      <Card>
        <Suspense
          fallback={
            <CardContent className="flex items-center gap-3 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Finding your Facebook Pages…
            </CardContent>
          }
        >
          <Inner />
        </Suspense>
      </Card>
    </main>
  )
}
