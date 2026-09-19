import type { Metadata } from "next"
import { notFound } from "next/navigation"

import { ReadOnlyNotice } from "@/components/page-header"
import { apiGet, getMe } from "@/lib/api/server"
import type { PricingRule, PricingSettings, Service } from "@/lib/api/types"

import { ServiceDetail } from "./service-detail"

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export async function generateMetadata({ params }: PageProps<"/services/[id]">): Promise<Metadata> {
  const { id } = await params
  if (!UUID.test(id)) return { title: "Service" }
  const service = await apiGet<Service>(`/business/services/${id}`)
  return { title: service?.name ?? "Service" }
}

export default async function ServicePage({ params }: PageProps<"/services/[id]">) {
  const { id } = await params
  if (!UUID.test(id)) notFound()
  const [me, service, rules, settings] = await Promise.all([
    getMe(),
    apiGet<Service>(`/business/services/${id}`),
    apiGet<PricingRule[]>(`/business/services/${id}/pricing-rules`),
    apiGet<PricingSettings>("/business/pricing-settings"),
  ])
  if (!service) notFound()
  const canEdit = me.role === "owner"
  return (
    <>
      {!canEdit && <ReadOnlyNotice />}
      <ServiceDetail service={service} rules={rules ?? []} settings={settings} canEdit={canEdit} />
    </>
  )
}
