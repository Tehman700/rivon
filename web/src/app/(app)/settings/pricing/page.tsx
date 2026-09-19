import type { Metadata } from "next"

import { PageHeader, ReadOnlyNotice } from "@/components/page-header"
import { apiGet, getMe } from "@/lib/api/server"
import type { PricingSettings } from "@/lib/api/types"

import { PricingSettingsForm } from "./pricing-settings-form"

export const metadata: Metadata = { title: "Pricing" }

export default async function PricingPage() {
  const [me, settings] = await Promise.all([
    getMe(),
    apiGet<PricingSettings>("/business/pricing-settings"),
  ])
  const canEdit = me.role === "owner"
  return (
    <>
      <PageHeader
        title="Pricing"
        description="Defaults every quote starts from. Individual services can override them."
      />
      {!canEdit && <ReadOnlyNotice />}
      <PricingSettingsForm settings={settings} canEdit={canEdit} />
    </>
  )
}
