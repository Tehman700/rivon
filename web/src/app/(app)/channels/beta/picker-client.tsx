"use client"

/**
 * BETA: connect by choosing a Page — the ManyChat round trip.
 *
 *   sign in with Facebook → see your Pages → none? create one on Facebook
 *   → come back (the list refreshes itself) → press Connect
 *
 * The session id in the URL is all the page holds. Every token stays on the
 * server; this screen only ever sees Page names and ids.
 */

import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { useCallback, useEffect, useRef, useState } from "react"
import {
  ArrowLeft,
  CheckCircle2,
  ExternalLink,
  HelpCircle,
  Loader2,
  Lock,
  Plug,
  RefreshCw,
} from "lucide-react"
import { toast } from "sonner"

import { InstagramIcon, MessengerIcon } from "@/components/brand/channel-icons"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"
import { ApiError, api } from "@/lib/api/client"
import type { ChannelConnection, ConnectStart, PickerPage, PickerPages } from "@/lib/api/types"

function StartCard({ canEdit }: { canEdit: boolean }) {
  const [starting, setStarting] = useState(false)

  async function start() {
    setStarting(true)
    try {
      const { authorize_url } = await api<ConnectStart>("/channels/v2/connect", { method: "POST" })
      window.location.assign(authorize_url)
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not start the connection")
      setStarting(false)
    }
  }

  return (
    <Card className="p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-[#0866ff] text-white" aria-hidden>
          <MessengerIcon className="size-5" />
        </span>
        <div className="flex-1 space-y-1">
          <h2 className="text-base font-medium">Connect a Facebook Page</h2>
          <p className="text-sm text-muted-foreground">
            Sign in with Facebook, then choose the Page your customers message — or create one if you
            don&apos;t have it yet. Its Instagram account can come along too.
          </p>
        </div>
        {canEdit && (
          <Button onClick={start} disabled={starting} className="sm:shrink-0">
            {starting ? <Loader2 className="animate-spin" /> : <Plug />} Continue with Facebook
          </Button>
        )}
      </div>
    </Card>
  )
}

function StatusBadge({ status }: { status: string }) {
  if (status === "connected") {
    return (
      <Badge variant="outline" className="gap-1 border-emerald-600/30 font-normal text-emerald-700">
        <CheckCircle2 className="size-3" /> Connected
      </Badge>
    )
  }
  if (status === "taken") {
    return (
      <Badge variant="secondary" className="gap-1 font-normal">
        <Lock className="size-3" /> Connected to another business
      </Badge>
    )
  }
  return null
}

function PageRow({
  page,
  busy,
  onConnect,
}: {
  page: PickerPage
  busy: boolean
  onConnect: (page: PickerPage, withInstagram: boolean) => void
}) {
  const instagramAvailable = page.instagram_status === "available"
  const [withInstagram, setWithInstagram] = useState(instagramAvailable)
  const canConnect =
    page.messenger_status === "available" ||
    (page.messenger_status === "connected" && instagramAvailable)

  return (
    <li className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center">
      <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-muted text-sm font-medium">
        {page.name.slice(0, 1).toUpperCase() || "?"}
      </span>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="truncate text-sm font-medium">{page.name || page.id}</p>
          <StatusBadge status={page.messenger_status} />
        </div>
        {page.instagram ? (
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <InstagramIcon className="size-3.5" />@{page.instagram.username ?? page.instagram.id}
            {page.instagram_status === null && <span>— Instagram access was not granted</span>}
            {page.instagram_status && page.instagram_status !== "available" && (
              <StatusBadge status={page.instagram_status} />
            )}
            {instagramAvailable && (
              <label className="ml-1 inline-flex items-center gap-1.5">
                <Switch checked={withInstagram} onCheckedChange={setWithInstagram} disabled={busy} />
                connect it too
              </label>
            )}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">No Instagram account linked to this Page</p>
        )}
      </div>
      {canConnect && (
        <Button onClick={() => onConnect(page, withInstagram)} disabled={busy} className="sm:shrink-0">
          {busy ? <Loader2 className="animate-spin" /> : <Plug />}
          {page.messenger_status === "connected" ? "Add Instagram" : "Connect"}
        </Button>
      )}
    </li>
  )
}

function Picker({ sessionId }: { sessionId: string }) {
  const router = useRouter()
  const [data, setData] = useState<PickerPages | null>(null)
  const [loading, setLoading] = useState(true)
  const [expired, setExpired] = useState<string | null>(null)
  const [connecting, setConnecting] = useState<string | null>(null)
  const awayToCreate = useRef(false)

  const onLoadError = useCallback((error: unknown) => {
    if (error instanceof ApiError && error.status === 410) setExpired(error.message)
    else toast.error(error instanceof ApiError ? error.message : "Could not load your Pages")
  }, [])

  const fetchPages = useCallback(
    () => api<PickerPages>(`/channels/v2/sessions/${sessionId}/pages`),
    [sessionId],
  )

  /** Refresh. `quiet` keeps the list on screen while it reloads. */
  const load = useCallback(
    async (quiet = false) => {
      if (!quiet) setLoading(true)
      try {
        setData(await fetchPages())
      } catch (error) {
        onLoadError(error)
      } finally {
        setLoading(false)
      }
    },
    [fetchPages, onLoadError],
  )

  // First load: state is only touched once the request answers.
  useEffect(() => {
    let current = true
    fetchPages()
      .then((pages) => current && setData(pages))
      .catch((error) => current && onLoadError(error))
      .finally(() => current && setLoading(false))
    return () => {
      current = false
    }
  }, [fetchPages, onLoadError])

  // Coming back from Facebook after creating a Page: refresh by ourselves, so
  // nobody has to find the button.
  useEffect(() => {
    function onFocus() {
      if (awayToCreate.current) {
        awayToCreate.current = false
        void load(true)
      }
    }
    window.addEventListener("focus", onFocus)
    return () => window.removeEventListener("focus", onFocus)
  }, [load])

  async function connect(page: PickerPage, withInstagram: boolean) {
    setConnecting(page.id)
    try {
      const connected = await api<ChannelConnection[]>(`/channels/v2/sessions/${sessionId}/connect`, {
        method: "POST",
        body: { page_id: page.id, include_instagram: withInstagram },
      })
      toast.success(
        connected.length > 1
          ? `${page.name} and its Instagram account are connected`
          : `${page.name} is connected`,
      )
      await load(true)
    } catch (error) {
      if (error instanceof ApiError && error.status === 410) setExpired(error.message)
      else toast.error(error instanceof ApiError ? error.message : "Could not connect that Page")
    } finally {
      setConnecting(null)
    }
  }

  async function finish() {
    // Destroys the held sign-in straight away rather than at expiry.
    await api(`/channels/v2/sessions/${sessionId}`, { method: "DELETE" }).catch(() => undefined)
    router.push("/channels")
  }

  if (expired) {
    return (
      <Card className="space-y-3 p-6">
        <p className="font-medium">This connection window has closed</p>
        <p className="text-sm text-muted-foreground">{expired}</p>
        <Button asChild>
          <Link href="/channels/beta">Start again</Link>
        </Button>
      </Card>
    )
  }

  const pages = data?.pages ?? []
  const createUrl = data?.create_page_url ?? "https://www.facebook.com/pages/create"

  return (
    <div className="space-y-4">
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <p className="text-sm font-medium">
            {loading
              ? "Looking for your Facebook Pages…"
              : pages.length
                ? `We found ${pages.length} Facebook Page${pages.length > 1 ? "s" : ""} managed by you`
                : "We haven't found any Facebook Pages managed by you"}
          </p>
          <Button variant="ghost" size="sm" onClick={() => load()} disabled={loading}>
            <RefreshCw className={loading ? "animate-spin" : ""} /> Refresh
          </Button>
        </div>

        {!loading && pages.length === 0 && (
          <div className="space-y-4 px-6 py-10 text-center">
            <p className="text-sm text-muted-foreground">
              Your customers message a Facebook Page, so you need one first. It takes about two
              minutes on Facebook — this list refreshes when you come back.
            </p>
            <Button asChild onClick={() => (awayToCreate.current = true)}>
              <a href={createUrl} target="_blank" rel="noopener noreferrer">
                <ExternalLink /> Create a Page on Facebook
              </a>
            </Button>
          </div>
        )}

        {pages.length > 0 && (
          <ul className="divide-y">
            {pages.map((page) => (
              <PageRow
                key={page.id}
                page={page}
                busy={connecting !== null}
                onConnect={connect}
              />
            ))}
          </ul>
        )}
      </Card>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
        <a
          href={createUrl}
          target="_blank"
          rel="noopener noreferrer"
          onClick={() => (awayToCreate.current = true)}
          className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
        >
          <ExternalLink className="size-3.5" /> Create new Page
        </a>
        <Link
          href="/channels/beta"
          className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
        >
          <HelpCircle className="size-3.5" /> I can&apos;t see my Page — sign in again and include it
        </Link>
        <Button variant="outline" size="sm" className="ml-auto" onClick={finish}>
          Done
        </Button>
      </div>
    </div>
  )
}

export function PickerClient({ canEdit }: { canEdit: boolean }) {
  const params = useSearchParams()
  const sessionId = params.get("session")

  return (
    <div className="space-y-6">
      <Link
        href="/channels"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" /> Back to channels
      </Link>
      {sessionId && canEdit ? <Picker sessionId={sessionId} /> : <StartCard canEdit={canEdit} />}
    </div>
  )
}
