"use client"

/**
 * WhatsApp Embedded Signup, the browser half.
 *
 * Different from the Page flow in three ways, each of which shapes this file:
 *
 * 1. It runs in Facebook's own popup through their JavaScript SDK, not a
 *    redirect. Browsers only allow a popup from a direct click, so the SDK and
 *    the configuration are loaded when the dialog opens — by the time the
 *    customer clicks "Continue to Facebook", FB.login can run synchronously.
 *
 * 2. The WhatsApp account and number ids arrive by a browser message event
 *    (WA_EMBEDDED_SIGNUP), separately from the code, and in either order. Both
 *    are needed; neither is in the other.
 *
 * 3. The code lives thirty seconds. The moment both halves are here, they go to
 *    the server, which exchanges the code before doing anything else.
 */

import { useRouter } from "next/navigation"
import { useCallback, useEffect, useRef, useState } from "react"
import { AlertTriangle, CheckCircle2, Copy, Loader2, Plug } from "lucide-react"
import { toast } from "sonner"

import { FormField } from "@/components/form-field"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { ApiError, api } from "@/lib/api/client"
import type { WhatsAppConnected, WhatsAppStart } from "@/lib/api/types"

// --- The bit of Facebook's SDK we use -----------------------------------------

interface FacebookLoginResponse {
  authResponse?: { code?: string } | null
  status?: string
}

interface FacebookSdk {
  init(options: { appId: string; version: string; xfbml?: boolean; cookie?: boolean }): void
  login(
    callback: (response: FacebookLoginResponse) => void,
    options: Record<string, unknown>,
  ): void
}

declare global {
  interface Window {
    FB?: FacebookSdk
    fbAsyncInit?: () => void
  }
}

const SDK_URL = "https://connect.facebook.net/en_US/sdk.js"
let sdkLoading: Promise<FacebookSdk> | null = null

/** Load the SDK once per page, however many times the dialog is opened. */
function loadSdk(appId: string, version: string): Promise<FacebookSdk> {
  if (window.FB) return Promise.resolve(window.FB)
  if (sdkLoading) return sdkLoading
  sdkLoading = new Promise<FacebookSdk>((resolve, reject) => {
    window.fbAsyncInit = () => {
      window.FB!.init({ appId, version, xfbml: false, cookie: true })
      resolve(window.FB!)
    }
    const script = document.createElement("script")
    script.src = SDK_URL
    script.async = true
    script.defer = true
    script.crossOrigin = "anonymous"
    script.onerror = () => {
      sdkLoading = null
      reject(new Error("Facebook could not be reached. Check an ad blocker is not stopping it."))
    }
    document.body.appendChild(script)
  })
  return sdkLoading
}

// --- What the popup tells us --------------------------------------------------

interface SessionInfo {
  wabaId: string
  phoneNumberId: string
}

type SessionEvent =
  | { kind: "finished"; info: SessionInfo }
  | { kind: "no-number" }
  | { kind: "cancelled"; step?: string }
  | { kind: "error"; message: string }

function readSessionEvent(event: MessageEvent): SessionEvent | null {
  // Only Facebook's own windows get to tell us anything.
  let host: string
  try {
    host = new URL(event.origin).hostname
  } catch {
    return null // an opaque "null" origin
  }
  if (!/(^|\.)facebook\.com$/.test(host)) return null
  let message: { type?: string; event?: string; data?: Record<string, string> }
  try {
    message = typeof event.data === "string" ? JSON.parse(event.data) : event.data
  } catch {
    return null
  }
  if (message?.type !== "WA_EMBEDDED_SIGNUP") return null

  const data = message.data ?? {}
  switch (message.event) {
    case "FINISH":
      if (data.waba_id && data.phone_number_id) {
        return { kind: "finished", info: { wabaId: data.waba_id, phoneNumberId: data.phone_number_id } }
      }
      return { kind: "no-number" }
    case "FINISH_ONLY_WABA":
      // An account was created, but no number was added to it. Nothing to connect.
      return { kind: "no-number" }
    case "CANCEL":
      return { kind: "cancelled", step: data.current_step }
    case "ERROR":
      return { kind: "error", message: data.error_message ?? "Facebook reported an error" }
    default:
      return null
  }
}

// --- The component ------------------------------------------------------------

type Stage =
  | { step: "idle" }
  | { step: "preparing" }
  | { step: "ready"; sdk: FacebookSdk; configId: string }
  | { step: "in-facebook" }
  | { step: "finishing" }
  | { step: "done"; result: WhatsAppConnected }
  | { step: "failed"; message: string }

/** How long to wait for the second half after the first arrives. */
const PAIRING_TIMEOUT_MS = 8_000

export function WhatsAppConnect({ hasNumbers }: { hasNumbers: boolean }) {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [stage, setStage] = useState<Stage>({ step: "idle" })
  const [pin, setPin] = useState("")
  const [pinError, setPinError] = useState<string>()

  // The two halves, filled in whichever order Facebook sends them.
  const code = useRef<string | null>(null)
  const session = useRef<SessionInfo | null>(null)
  const submitted = useRef(false)
  const pinRef = useRef("")
  const pairingTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clearPairing = () => {
    if (pairingTimer.current) clearTimeout(pairingTimer.current)
    pairingTimer.current = null
  }

  const reset = () => {
    code.current = null
    session.current = null
    submitted.current = false
    clearPairing()
  }

  const fail = useCallback((message: string) => {
    clearPairing()
    setStage({ step: "failed", message })
  }, [])

  const submitIfComplete = useCallback(async () => {
    if (submitted.current || !code.current || !session.current) {
      // Half here, half not: give the other half a moment, then say so.
      if (!submitted.current && (code.current || session.current) && !pairingTimer.current) {
        pairingTimer.current = setTimeout(() => {
          if (!submitted.current) {
            fail(
              code.current
                ? "Facebook did not send the WhatsApp account details. Please try again."
                : "Facebook did not finish the sign-in. Please try again.",
            )
          }
        }, PAIRING_TIMEOUT_MS)
      }
      return
    }
    submitted.current = true
    clearPairing()
    setStage({ step: "finishing" })
    try {
      const result = await api<WhatsAppConnected>("/channels/whatsapp/complete", {
        method: "POST",
        body: {
          code: code.current,
          waba_id: session.current.wabaId,
          phone_number_id: session.current.phoneNumberId,
          ...(pinRef.current ? { pin: pinRef.current } : {}),
        },
      })
      setStage({ step: "done", result })
      router.refresh()
    } catch (error) {
      fail(error instanceof ApiError ? error.message : "The number could not be connected.")
    }
  }, [fail, router])

  // Listen for the popup's session events while the dialog is open.
  useEffect(() => {
    if (!open) return
    function onMessage(event: MessageEvent) {
      const parsed = readSessionEvent(event)
      if (!parsed) return
      if (parsed.kind === "finished") {
        session.current = parsed.info
        void submitIfComplete()
      } else if (parsed.kind === "no-number") {
        fail("The WhatsApp account was created, but no phone number was added to it. Connect again and add a number.")
      } else if (parsed.kind === "cancelled") {
        fail("You closed Facebook before finishing, so nothing was connected.")
      } else {
        fail(parsed.message)
      }
    }
    window.addEventListener("message", onMessage)
    return () => window.removeEventListener("message", onMessage)
  }, [open, submitIfComplete, fail])

  // Load everything when the dialog opens, so the click can open the popup
  // straight away — browsers block popups that follow an await.
  async function prepare() {
    setStage({ step: "preparing" })
    try {
      const start = await api<WhatsAppStart>("/channels/whatsapp/start", { method: "POST" })
      const sdk = await loadSdk(start.app_id, start.graph_version)
      setStage({ step: "ready", sdk, configId: start.config_id })
    } catch (error) {
      fail(error instanceof ApiError || error instanceof Error ? error.message : "WhatsApp setup could not start.")
    }
  }

  function onOpenChange(next: boolean) {
    // Do not let a stray click close it while the number is being registered.
    if (!next && stage.step === "finishing") return
    setOpen(next)
    if (next) {
      reset()
      setPin("")
      setPinError(undefined)
      void prepare()
    }
  }

  function launch() {
    if (stage.step !== "ready") return
    if (pin && !/^\d{6}$/.test(pin)) {
      setPinError("A WhatsApp PIN is exactly six digits.")
      return
    }
    setPinError(undefined)
    pinRef.current = pin
    reset()
    const { sdk, configId } = stage
    setStage({ step: "in-facebook" })

    // Must stay synchronous: this is what the browser treats as the click that
    // opened the popup. The callback may not be async either.
    sdk.login(
      (response) => {
        const returned = response.authResponse?.code
        if (!returned) {
          // Closing the popup before the end also lands here; the session
          // event, if any, will have said which.
          if (!session.current) fail("You closed Facebook before finishing, so nothing was connected.")
          return
        }
        code.current = returned
        void submitIfComplete()
      },
      {
        config_id: configId,
        response_type: "code",
        override_default_response_type: true,
        extras: { setup: {}, sessionInfoVersion: "3" },
      },
    )
  }

  const busy = ["preparing", "in-facebook", "finishing"].includes(stage.step)

  return (
    <>
      <Button
        variant={hasNumbers ? "outline" : "default"}
        onClick={() => onOpenChange(true)}
        className="sm:shrink-0"
      >
        <Plug />
        {hasNumbers ? "Connect another" : "Connect"}
      </Button>

      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-md">
          {stage.step === "done" ? (
            <Connected result={stage.result} onClose={() => setOpen(false)} />
          ) : stage.step === "failed" ? (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <AlertTriangle className="size-5 text-destructive" /> Not connected
                </DialogTitle>
                <DialogDescription>{stage.message}</DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={() => setOpen(false)}>
                  Close
                </Button>
                <Button onClick={() => { reset(); void prepare() }}>Try again</Button>
              </DialogFooter>
            </>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle>Connect WhatsApp</DialogTitle>
                <DialogDescription>
                  Facebook opens in a new window. You&apos;ll choose or create a WhatsApp Business
                  account and verify the phone number your customers will message.
                </DialogDescription>
              </DialogHeader>

              <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
                <li>
                  The number must <strong className="text-foreground">not</strong> be in use on the
                  WhatsApp or WhatsApp Business app. It moves to Rivon, and stops working there.
                </li>
                <li>Have the phone to hand — Facebook sends it a verification code.</li>
                <li>
                  You&apos;ll add your own payment method in WhatsApp Manager before messaging customers
                  who have not written to you first.
                </li>
              </ul>

              <FormField
                id="whatsapp-pin"
                label="Two-step verification PIN (optional)"
                hint="Only if this number already has one. Leave empty and we'll set one and show it to you once."
                error={pinError}
              >
                <Input
                  id="whatsapp-pin"
                  inputMode="numeric"
                  autoComplete="off"
                  maxLength={6}
                  placeholder="6 digits"
                  value={pin}
                  onChange={(event) => setPin(event.target.value.replace(/\D/g, ""))}
                  disabled={busy}
                />
              </FormField>

              <DialogFooter>
                <Button variant="outline" onClick={() => onOpenChange(false)} disabled={stage.step === "finishing"}>
                  Cancel
                </Button>
                <Button onClick={launch} disabled={stage.step !== "ready"}>
                  {busy ? <Loader2 className="animate-spin" /> : null}
                  {stage.step === "preparing" && "Loading Facebook…"}
                  {stage.step === "ready" && "Continue to Facebook"}
                  {stage.step === "in-facebook" && "Waiting for Facebook…"}
                  {stage.step === "finishing" && "Connecting the number…"}
                  {stage.step === "idle" && "Continue to Facebook"}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}

function Connected({ result, onClose }: { result: WhatsAppConnected; onClose: () => void }) {
  const { connection, registration_pin: pin } = result
  const number = connection.display_name ?? connection.external_id

  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          <CheckCircle2 className="size-5 text-emerald-600" /> WhatsApp connected
        </DialogTitle>
        <DialogDescription>
          {number} is connected. Rivon will start answering messages sent to it.
        </DialogDescription>
      </DialogHeader>

      {pin && (
        <div className="space-y-2 rounded-lg border border-amber-500/40 bg-amber-50 p-4 text-sm dark:bg-amber-950/30">
          <p className="font-medium">Save this PIN — it will not be shown again</p>
          <div className="flex items-center gap-2">
            <code className="rounded bg-background px-2 py-1 font-mono text-lg tracking-widest">{pin}</code>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                void navigator.clipboard.writeText(pin)
                toast.success("PIN copied")
              }}
            >
              <Copy /> Copy
            </Button>
          </div>
          <p className="text-muted-foreground">
            It is the number&apos;s two-step verification PIN. You need it to move the number
            elsewhere later. Rivon does not keep a copy.
          </p>
        </div>
      )}

      <DialogFooter>
        <Button onClick={onClose}>Done</Button>
      </DialogFooter>
    </>
  )
}
