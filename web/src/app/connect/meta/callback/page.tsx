"use client"

/**
 * Where Meta sends the customer back to.
 *
 * The URL here must match the App Dashboard exactly, trailing slash included —
 * strict mode is on, and a mismatch shows a blank error page with no
 * explanation, which is the single most common way this breaks.
 *
 * The page does nothing itself beyond handing the code and state to the API.
 * The exchange is server side, because the app secret never belongs in a
 * browser.
 */

import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { Suspense, useEffect, useRef, useState } from "react"
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react"

import { RivonLogo } from "@/components/brand/logo"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ApiError, api } from "@/lib/api/client"
import type { ConnectOutcome } from "@/lib/api/types"

type State =
  | { step: "working" }
  | { step: "done"; outcome: ConnectOutcome }
  | { step: "failed"; message: string }

function CallbackInner() {
  const params = useSearchParams()
  const [state, setState] = useState<State>({ step: "working" })
  // React runs effects twice in development; the state is single use, so a
  // second exchange would fail and show an error on a connection that worked.
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true

    const code = params.get("code")
    const stateValue = params.get("state")
    const declined = params.get("error_description") ?? params.get("error")

    if (declined) {
      setState({
        step: "failed",
        message:
          params.get("error_reason") === "user_denied"
            ? "You cancelled before granting access, so nothing was connected."
            : declined,
      })
      return
    }
    if (!code || !stateValue) {
      setState({ step: "failed", message: "Facebook did not send anything back to connect." })
      return
    }

    api<ConnectOutcome>("/channels/callback", { method: "POST", body: { code, state: stateValue } })
      .then((outcome) => setState({ step: "done", outcome }))
      .catch((error) =>
        setState({
          step: "failed",
          message: error instanceof ApiError ? error.message : "The connection could not be completed.",
        }),
      )
  }, [params])

  if (state.step === "working") {
    return (
      <CardContent className="flex items-center gap-3 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        Finishing the connection…
      </CardContent>
    )
  }

  if (state.step === "failed") {
    return (
      <>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <AlertTriangle className="size-5 text-destructive" /> Not connected
          </CardTitle>
          <CardDescription>{state.message}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild>
            <Link href="/channels">Back to channels</Link>
          </Button>
        </CardContent>
      </>
    )
  }

  const { connected, skipped } = state.outcome
  return (
    <>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <CheckCircle2 className="size-5 text-emerald-600" />
          {connected.length === 1 ? "Account connected" : `${connected.length} accounts connected`}
        </CardTitle>
        <CardDescription>Rivon will start answering messages sent to them.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <ul className="space-y-1 text-sm">
          {connected.map((connection) => (
            <li key={connection.id}>
              <span className="font-medium">{connection.display_name ?? connection.external_id}</span>
              <span className="text-muted-foreground"> — {connection.provider}</span>
            </li>
          ))}
        </ul>

        {skipped.length > 0 && (
          <div className="rounded-lg border bg-muted/30 p-4 text-sm">
            <p className="font-medium">Left out</p>
            <ul className="mt-1 space-y-1 text-muted-foreground">
              {skipped.map((item) => (
                <li key={item.account}>
                  {item.account} — {item.reason}
                </li>
              ))}
            </ul>
          </div>
        )}

        <Button asChild>
          <Link href="/channels">Back to channels</Link>
        </Button>
      </CardContent>
    </>
  )
}

export default function MetaCallbackPage() {
  return (
    <main className="mx-auto flex min-h-svh w-full max-w-lg flex-col justify-center px-4 py-16">
      <RivonLogo className="mb-6 self-start" />
      <Card>
        <Suspense
          fallback={
            <CardContent className="flex items-center gap-3 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Finishing the connection…
            </CardContent>
          }
        >
          <CallbackInner />
        </Suspense>
      </Card>
    </main>
  )
}
