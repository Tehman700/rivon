import type { Metadata } from "next"
import Link from "next/link"

import { PageHeader, ReadOnlyNotice } from "@/components/page-header"
import { apiGet, getMe } from "@/lib/api/server"
import type { ChannelConnection } from "@/lib/api/types"

import { ChannelsClient } from "./channels-client"

export const metadata: Metadata = { title: "Channels" }

export default async function ChannelsPage() {
  const [me, connections] = await Promise.all([
    getMe(),
    apiGet<ChannelConnection[]>("/channels"),
  ])
  const canEdit = me.role === "owner"

  return (
    <>
      <PageHeader
        title="Channels"
        description="Where your customers can reach you. Connect an account and Rivon starts answering the messages sent to it."
      />
      {!canEdit && <ReadOnlyNotice />}
      {canEdit && (
        <p className="mb-4 text-sm text-muted-foreground">
          No Facebook Page yet, or want to pick which one?{" "}
          <Link href="/channels/beta" className="underline underline-offset-4 hover:text-foreground">
            Try the new connect flow (beta)
          </Link>
        </p>
      )}
      <ChannelsClient connections={connections ?? []} canEdit={canEdit} />
    </>
  )
}
