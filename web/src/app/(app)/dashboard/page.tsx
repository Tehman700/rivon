import type { Metadata } from "next"
import Link from "next/link"
import { ArrowRight, CheckCircle2, Circle, FileText, MessagesSquare, ShieldCheck } from "lucide-react"

import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { apiGet, getMe, getProfile } from "@/lib/api/server"
import type { Crew, InventoryItem, PricingRule, PricingSettings, Service, ServiceArea } from "@/lib/api/types"

export const metadata: Metadata = { title: "Overview" }

interface Step {
  title: string
  description: string
  href: string
  done: boolean
  detail?: string
}

export default async function DashboardPage() {
  const [me, profile, services, pricing, areas, inventory, crews] = await Promise.all([
    getMe(),
    getProfile(),
    apiGet<Service[]>("/business/services"),
    apiGet<PricingSettings>("/business/pricing-settings"),
    apiGet<ServiceArea[]>("/business/service-areas"),
    apiGet<InventoryItem[]>("/business/inventory"),
    apiGet<Crew[]>("/business/crews"),
  ])
  const active = services ?? []
  const rateCards = await Promise.all(
    active.map((s) => apiGet<PricingRule[]>(`/business/services/${s.id}/pricing-rules`)),
  )
  const withoutRates = active.filter((_, i) => (rateCards[i] ?? []).length === 0)
  const totalLines = rateCards.reduce((sum, rules) => sum + (rules?.length ?? 0), 0)

  const steps: Step[] = [
    {
      title: "Describe your business",
      description: "Name, contact details, opening hours and the size of jobs you take on.",
      href: "/settings/business",
      done: profile !== null,
    },
    {
      title: "Add the services you offer",
      description: "What customers can ask you for, e.g. rooftop PV, battery storage.",
      href: "/services",
      done: active.length > 0,
      detail: active.length ? `${active.length} active` : undefined,
    },
    {
      title: "Set your margins and VAT",
      description: "Your target and minimum margin, and the VAT rate quotes use by default.",
      href: "/settings/pricing",
      done: pricing !== null,
    },
    {
      title: "Build a rate card for each service",
      description: "Your costs per kWp, per hour, per km: what quotes are priced from.",
      href: withoutRates[0] ? `/services/${withoutRates[0].id}` : "/services",
      done: active.length > 0 && withoutRates.length === 0,
      detail: active.length
        ? withoutRates.length
          ? `${withoutRates.length} service${withoutRates.length === 1 ? "" : "s"} without one`
          : `${totalLines} line${totalLines === 1 ? "" : "s"} in total`
        : undefined,
    },
  ]

  // What feasibility needs before it can judge a job (BIZ-05/06/07).
  const capacity = [
    { label: "service area", href: "/service-areas", count: (areas ?? []).length },
    { label: "stock item", href: "/inventory", count: (inventory ?? []).length },
    { label: "crew", href: "/crews", count: (crews ?? []).filter((c) => c.active).length },
  ]
  const missing = capacity.filter((c) => c.count === 0)
  steps.push({
    title: "Say what you can take on",
    description:
      "Your service areas, the stock you hold and the crews you can send. Rivon checks every job against these.",
    href: missing[0]?.href ?? "/service-areas",
    done: missing.length === 0,
    detail: missing.length
      ? `no ${missing.map((m) => `${m.label}s`).join(", ")} yet`
      : capacity.map((c) => `${c.count} ${c.label}${c.count === 1 ? "" : "s"}`).join(" · "),
  })

  const completed = steps.filter((s) => s.done).length
  const firstName = profile?.name ?? "your business"

  return (
    <>
      <PageHeader
        title={`Welcome${profile ? `, ${firstName}` : ""}`}
        description="Set Rivon up once. From then on, every inquiry is qualified, checked against your real capacity and priced from your own rate card."
      />

      <Card>
        <CardHeader>
          <CardTitle>Getting set up</CardTitle>
          <CardDescription>
            {completed === steps.length
              ? "All set. Your setup is ready for quoting."
              : `${completed} of ${steps.length} steps done`}
          </CardDescription>
          <Progress value={(completed / steps.length) * 100} className="mt-2 h-2" />
        </CardHeader>
        <CardContent className="p-0">
          <ol className="divide-y border-t">
            {steps.map((step) => (
              <li key={step.title}>
                <Link
                  href={step.href}
                  className="group flex items-start gap-4 px-6 py-4 transition-colors hover:bg-muted/50"
                >
                  {step.done ? (
                    <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-[oklch(0.55_0.13_150)]" aria-label="Done" />
                  ) : (
                    <Circle className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-label="To do" />
                  )}
                  <span className="min-w-0 flex-1 space-y-1">
                    <span className="flex flex-wrap items-center gap-2 text-sm font-medium">
                      {step.title}
                      {step.detail && (
                        <Badge variant="outline" className={step.done ? "level-good" : "level-warn"}>
                          {step.detail}
                        </Badge>
                      )}
                    </span>
                    <span className="block text-sm text-muted-foreground">{step.description}</span>
                  </span>
                  <ArrowRight className="mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                </Link>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      <h2 className="mt-10 mb-4 text-lg">Coming next</h2>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Upcoming
          icon={MessagesSquare}
          title="Conversations"
          text="Your assistant qualifies inquiries and tells customers up front that they're talking to an AI."
        />
        <Upcoming
          icon={ShieldCheck}
          title="Feasibility checks"
          text="Every job checked against your areas, stock and crews, with reasons, before anything is quoted."
        />
        <Upcoming
          icon={FileText}
          title="Quotations"
          text="Priced from your rate card by fixed rules, then sent only after you approve them."
        />
      </div>

      {me.role !== "owner" && (
        <p className="mt-8 text-sm text-muted-foreground">
          You&apos;re signed in as {me.role}. You can view the setup; the owner makes changes.
        </p>
      )}
    </>
  )
}

function Upcoming({ icon: Icon, title, text }: { icon: typeof FileText; title: string; text: string }) {
  return (
    <Card size="sm" className="bg-muted/30">
      <CardHeader>
        <Icon className="mb-2 size-5 text-muted-foreground" />
        <CardTitle className="flex items-center gap-2">
          {title}
          <Badge variant="outline" className="font-normal">
            Soon
          </Badge>
        </CardTitle>
        <CardDescription>{text}</CardDescription>
      </CardHeader>
    </Card>
  )
}
