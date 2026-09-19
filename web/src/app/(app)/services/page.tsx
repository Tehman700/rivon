import type { Metadata } from "next"

import { PageHeader } from "@/components/page-header"
import { apiGet, getMe } from "@/lib/api/server"
import type { PricingRule, PricingSettings, Service } from "@/lib/api/types"

import { ServicesTable } from "./services-table"

export const metadata: Metadata = { title: "Services & rate cards" }

export default async function ServicesPage() {
  const [me, services, settings] = await Promise.all([
    getMe(),
    apiGet<Service[]>("/business/services?include_archived=true"),
    apiGet<PricingSettings>("/business/pricing-settings"),
  ])
  const list = services ?? []
  const rules = await Promise.all(
    list.map((s) => apiGet<PricingRule[]>(`/business/services/${s.id}/pricing-rules`)),
  )
  const lineCounts = Object.fromEntries(list.map((s, i) => [s.id, rules[i]?.length ?? 0]))

  return (
    <>
      <PageHeader
        title="Services & rate cards"
        description="What you offer, and what each job costs you to deliver. Quotes are priced from these by fixed rules, never guessed."
      />
      <ServicesTable services={list} lineCounts={lineCounts} settings={settings} canEdit={me.role === "owner"} />
    </>
  )
}
