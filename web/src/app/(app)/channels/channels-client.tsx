"use client"

import { useRouter } from "next/navigation"
import { useState } from "react"
import { AlertTriangle, CheckCircle2, Loader2, Plug, Unplug } from "lucide-react"
import { toast } from "sonner"

import {
  InstagramIcon,
  MessengerIcon,
  WhatsAppIcon,
} from "@/components/brand/channel-icons"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { ApiError, api } from "@/lib/api/client"
import type { ChannelConnection, ChannelProvider, ConnectStart } from "@/lib/api/types"

import { WhatsAppConnect } from "./whatsapp-connect"

/** The three cards, in the order a solar installer is most likely to want them. */
const PROVIDERS: {
  id: ChannelProvider
  name: string
  description: string
  icon: (props: { className?: string }) => React.ReactElement
  /** Brand colour, used only for the icon tile. */
  tint: string
  available: boolean
}[] = [
  {
    id: "messenger",
    name: "Facebook Messenger",
    description: "Answer the people who message your Facebook Page, day or night.",
    icon: MessengerIcon,
    tint: "bg-[#0866ff]",
    available: true,
  },
  {
    id: "instagram",
    name: "Instagram",
    description: "Reply to Instagram DMs from the account linked to your Page.",
    icon: InstagramIcon,
    tint: "bg-gradient-to-br from-[#f9ce34] via-[#ee2a7b] to-[#6228d7]",
    available: true,
  },
  {
    id: "whatsapp",
    name: "WhatsApp",
    description: "Answer the number your customers already message, from the WhatsApp Business Platform.",
    icon: WhatsAppIcon,
    tint: "bg-[#25d366]",
    available: true,
  },
]

function StatusBadge({ connection }: { connection: ChannelConnection }) {
  if (connection.needs_attention) {
    return (
      <Badge variant="destructive" className="gap-1 font-normal">
        <AlertTriangle className="size-3" /> Needs reconnecting
      </Badge>
    )
  }
  return (
    <Badge variant="outline" className="gap-1 border-emerald-600/30 font-normal text-emerald-700">
      <CheckCircle2 className="size-3" /> Connected
    </Badge>
  )
}

function ConnectedAccount({
  connection,
  canEdit,
  onChanged,
}: {
  connection: ChannelConnection
  canEdit: boolean
  onChanged: () => void
}) {
  const [pending, setPending] = useState(false)

  async function disconnect() {
    setPending(true)
    try {
      await api(`/channels/${connection.id}`, { method: "DELETE" })
      toast.success(`${connection.display_name ?? "Account"} disconnected`)
      onChanged()
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not disconnect")
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border bg-muted/30 px-4 py-3 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">
          {connection.display_name ?? connection.external_id}
        </p>
        <p className="text-xs text-muted-foreground">
          Connected {new Date(connection.connected_at).toLocaleDateString()}
          {connection.status_detail ? ` — ${connection.status_detail}` : ""}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <StatusBadge connection={connection} />
        {canEdit && (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="ghost" size="sm" disabled={pending}>
                {pending ? <Loader2 className="animate-spin" /> : <Unplug />}
                <span className="sr-only sm:not-sr-only">Disconnect</span>
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>
                  Disconnect {connection.display_name ?? "this account"}?
                </AlertDialogTitle>
                <AlertDialogDescription>
                  Rivon stops answering messages sent to it, and we delete the access it was
                  given. Your past conversations are kept. You can connect it again at any time.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Keep connected</AlertDialogCancel>
                <AlertDialogAction onClick={disconnect}>Disconnect</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </div>
    </div>
  )
}

export function ChannelsClient({
  connections,
  canEdit,
}: {
  connections: ChannelConnection[]
  canEdit: boolean
}) {
  const router = useRouter()
  const [starting, setStarting] = useState<ChannelProvider | null>(null)

  async function connect(provider: ChannelProvider) {
    setStarting(provider)
    try {
      // The server mints a single-use state and builds the dialog URL; we only
      // ever send the customer to it.
      const start = await api<ConnectStart>(`/channels/connect/${provider}`, { method: "POST" })
      window.location.assign(start.authorize_url)
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not start the connection")
      setStarting(null)
    }
  }

  return (
    <div className="space-y-4">
      {PROVIDERS.map((provider) => {
        const linked = connections.filter((c) => c.provider === provider.id)
        const Icon = provider.icon
        return (
          <Card key={provider.id} className="p-5 sm:p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
              <span
                className={`flex size-11 shrink-0 items-center justify-center rounded-xl text-white ${provider.tint}`}
                aria-hidden
              >
                <Icon className="size-5" />
              </span>

              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-base font-medium">{provider.name}</h2>
                  {!provider.available && (
                    <Badge variant="secondary" className="font-normal">
                      Coming soon
                    </Badge>
                  )}
                </div>
                <p className="text-sm text-muted-foreground">{provider.description}</p>
              </div>

              {canEdit && provider.available && provider.id === "whatsapp" && (
                // Embedded Signup: Facebook's popup, not a redirect.
                <WhatsAppConnect hasNumbers={linked.length > 0} />
              )}
              {canEdit && provider.available && provider.id !== "whatsapp" && (
                <Button
                  variant={linked.length ? "outline" : "default"}
                  onClick={() => connect(provider.id)}
                  disabled={starting !== null}
                  className="sm:shrink-0"
                >
                  {starting === provider.id ? <Loader2 className="animate-spin" /> : <Plug />}
                  {linked.length ? "Connect another" : "Connect"}
                </Button>
              )}
            </div>

            {linked.length > 0 && (
              <div className="mt-4 space-y-2">
                {linked.map((connection) => (
                  <ConnectedAccount
                    key={connection.id}
                    connection={connection}
                    canEdit={canEdit}
                    onChanged={() => router.refresh()}
                  />
                ))}
              </div>
            )}
          </Card>
        )
      })}
    </div>
  )
}
