import type { Metadata } from "next"

import { PageHeader, ReadOnlyNotice } from "@/components/page-header"
import { apiGet, getMe } from "@/lib/api/server"
import type { InventoryItem } from "@/lib/api/types"

import { InventoryClient } from "./inventory-client"

export const metadata: Metadata = { title: "Inventory" }

export default async function InventoryPage() {
  const [me, items] = await Promise.all([getMe(), apiGet<InventoryItem[]>("/business/inventory")])
  const canEdit = me.role === "owner"
  return (
    <>
      <PageHeader
        title="Inventory"
        description="What you hold. Feasibility checks a job's parts against these quantities before anything is quoted."
      />
      {!canEdit && <ReadOnlyNotice />}
      <InventoryClient items={items ?? []} canEdit={canEdit} />
    </>
  )
}
