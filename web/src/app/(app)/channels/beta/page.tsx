import type { Metadata } from "next"
import { Suspense } from "react"

import { PageHeader, ReadOnlyNotice } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { getMe } from "@/lib/api/server"

import { PickerClient } from "./picker-client"

export const metadata: Metadata = { title: "Connect a Page (beta)" }

/**
 * BETA: the ManyChat-style connect flow, beside the current Channels page so
 * it can be tried without changing what the Connect buttons there do.
 */
export default async function ChannelsBetaPage() {
  const me = await getMe()
  const canEdit = me.role === "owner"

  return (
    <>
      <PageHeader
        title={
          <span className="inline-flex items-center gap-2">
            Connect a Page <Badge variant="secondary" className="font-normal">Beta</Badge>
          </span>
        }
        description="Choose which Facebook Page — and its Instagram account — Rivon should answer for."
      />
      {!canEdit && <ReadOnlyNotice />}
      <Suspense>
        <PickerClient canEdit={canEdit} />
      </Suspense>
    </>
  )
}
