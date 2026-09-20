import type { Metadata } from "next"

import { PageHeader, ReadOnlyNotice } from "@/components/page-header"
import { apiGet, getMe } from "@/lib/api/server"
import type { Crew } from "@/lib/api/types"

import { CrewsClient } from "./crews-client"

export const metadata: Metadata = { title: "Crews" }

export default async function CrewsPage() {
  const [me, crews] = await Promise.all([getMe(), apiGet<Crew[]>("/business/crews")])
  const canEdit = me.role === "owner"
  return (
    <>
      <PageHeader
        title="Crews"
        description="Who can go out, and how much they can take on. Used to check a job fits before it is quoted."
      />
      {!canEdit && <ReadOnlyNotice />}
      <CrewsClient crews={crews ?? []} canEdit={canEdit} />
    </>
  )
}
