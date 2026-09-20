import type { Metadata } from "next"

import { PageHeader, ReadOnlyNotice } from "@/components/page-header"
import { apiGet, getMe, getProfile } from "@/lib/api/server"
import type { ServiceArea } from "@/lib/api/types"

import { ServiceAreasClient } from "./areas-client"

export const metadata: Metadata = { title: "Service areas" }

export default async function ServiceAreasPage() {
  const [me, areas, profile] = await Promise.all([
    getMe(),
    apiGet<ServiceArea[]>("/business/service-areas"),
    getProfile(),
  ])
  const canEdit = me.role === "owner"
  return (
    <>
      <PageHeader
        title="Service areas"
        description="Where you work. Rivon checks each enquiry's address against these before quoting."
      />
      {!canEdit && <ReadOnlyNotice />}
      <ServiceAreasClient
        areas={areas ?? []}
        defaultCountry={profile?.country ?? "DE"}
        canEdit={canEdit}
      />
    </>
  )
}
