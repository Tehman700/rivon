"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { Archive, ArrowLeft, Calculator, Pencil, Plus, RotateCcw, Trash2 } from "lucide-react"
import { toast } from "sonner"

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
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ApiError, api } from "@/lib/api/client"
import { CATEGORY_LABELS, type PricingRule, type PricingSettings, type Service } from "@/lib/api/types"
import { formatEuro, formatPercent } from "@/lib/format"

import { ServiceDialog } from "../service-dialog"
import { RuleDialog, describeRule } from "./rule-dialog"

export function ServiceDetail({
  service,
  rules,
  settings,
  canEdit,
}: {
  service: Service
  rules: PricingRule[]
  settings: PricingSettings | null
  canEdit: boolean
}) {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const nextSort = rules.length ? Math.max(...rules.map((r) => r.sort_order)) + 1 : 1

  async function setArchived(archived: boolean) {
    setBusy(true)
    try {
      await api(`/business/services/${service.id}`, { method: "PATCH", body: { archived } })
      toast.success(archived ? `${service.name} archived` : `${service.name} restored`)
      router.refresh()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't update the service.")
    } finally {
      setBusy(false)
    }
  }

  async function deleteRule(rule: PricingRule) {
    try {
      await api(`/business/services/${service.id}/pricing-rules/${rule.id}`, { method: "DELETE" })
      toast.success(`${rule.name} removed`)
      router.refresh()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't remove the line.")
    }
  }

  const margin = service.target_margin_percent ?? settings?.default_target_margin_percent ?? null
  const vat = service.vat_rate_percent ?? settings?.default_vat_rate_percent ?? null

  return (
    <>
      <Link href="/services" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Services
      </Link>

      <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h1 className="flex flex-wrap items-center gap-2 text-2xl">
            {service.name}
            {service.archived && <Badge variant="secondary">Archived</Badge>}
          </h1>
          {service.description && <p className="max-w-2xl text-sm text-muted-foreground">{service.description}</p>}
        </div>
        {canEdit && (
          <div className="flex shrink-0 gap-2">
            <ServiceDialog
              service={service}
              trigger={
                <Button variant="outline">
                  <Pencil /> Edit
                </Button>
              }
            />
            {service.archived ? (
              <Button variant="outline" disabled={busy} onClick={() => setArchived(false)}>
                <RotateCcw /> Restore
              </Button>
            ) : (
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="outline" disabled={busy}>
                    <Archive /> Archive
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Archive {service.name}?</AlertDialogTitle>
                    <AlertDialogDescription>
                      It won&apos;t be offered to new customers. Its rate card is kept and you can
                      restore it any time.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction onClick={() => setArchived(true)}>Archive</AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            )}
          </div>
        )}
      </div>

      <div className="mb-6 grid grid-cols-3 gap-2 sm:gap-4">
        <Stat label="Target margin" value={formatPercent(margin)} note={service.target_margin_percent ? "This service" : "Business default"} />
        <Stat label="VAT rate" value={formatPercent(vat)} note={service.vat_rate_percent ? "This service" : "Business default"} />
        <Stat label="Rate card" value={`${rules.length} line${rules.length === 1 ? "" : "s"}`} note="Costs, net of VAT" />
      </div>
      {!settings && (
        <p className="mb-6 rounded-lg border px-4 py-3 text-sm level-warn">
          Set your business-wide margins and VAT in{" "}
          <Link href="/settings/pricing" className="underline underline-offset-4">Pricing</Link> before quoting.
        </p>
      )}

      <Card className="pb-0">
        <CardHeader>
          <CardTitle>Rate card</CardTitle>
          <CardDescription>
            What this job costs you. When a lead comes in, Rivon fills in the quantities from the
            conversation and prices it with these lines.
          </CardDescription>
          {canEdit && rules.length > 0 && (
            <div className="col-start-2 row-span-2 row-start-1 self-start justify-self-end">
              <RuleDialog serviceId={service.id} nextSort={nextSort} trigger={<Button><Plus /> Add line</Button>} />
            </div>
          )}
        </CardHeader>
        <CardContent className="p-0">
          {rules.length === 0 ? (
            <div className="flex flex-col items-center gap-3 border-t px-6 py-12 text-center">
              <Calculator className="size-8 text-muted-foreground" />
              <p className="font-medium">No lines yet</p>
              <p className="max-w-sm text-sm text-muted-foreground">
                Add each cost: modules per kWp, installation hours, scaffolding, travel.
              </p>
              {canEdit && <RuleDialog serviceId={service.id} nextSort={nextSort} trigger={<Button><Plus /> Add the first line</Button>} />}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-6">Line</TableHead>
                  <TableHead className="hidden md:table-cell">How it&apos;s charged</TableHead>
                  <TableHead className="text-right">Cost per unit</TableHead>
                  {canEdit && <TableHead className="w-24" />}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rules.map((rule) => (
                  <TableRow key={rule.id}>
                    <TableCell className="pl-6 align-top">
                      <p className="font-medium">{rule.name}</p>
                      <Badge variant="outline" className="mt-1 font-normal">{CATEGORY_LABELS[rule.category]}</Badge>
                      <p className="mt-1 text-sm whitespace-normal text-muted-foreground md:hidden">{describeRule({ ...rule, sort_order: String(rule.sort_order) })}</p>
                    </TableCell>
                    <TableCell className="hidden max-w-sm align-top text-sm whitespace-normal text-muted-foreground md:table-cell">
                      {describeRule({ ...rule, sort_order: String(rule.sort_order) })}
                    </TableCell>
                    <TableCell className="text-right align-top tabular-nums">
                      {formatEuro(rule.unit_cost_eur)}
                      <span className="text-muted-foreground"> / {rule.unit_label}</span>
                    </TableCell>
                    {canEdit && (
                      <TableCell className="align-top">
                        <div className="flex justify-end gap-1">
                          <RuleDialog
                            serviceId={service.id}
                            rule={rule}
                            trigger={<Button variant="ghost" size="icon" aria-label={`Edit ${rule.name}`}><Pencil /></Button>}
                          />
                          <AlertDialog>
                            <AlertDialogTrigger asChild>
                              <Button variant="ghost" size="icon" aria-label={`Remove ${rule.name}`}><Trash2 /></Button>
                            </AlertDialogTrigger>
                            <AlertDialogContent>
                              <AlertDialogHeader>
                                <AlertDialogTitle>Remove {rule.name}?</AlertDialogTitle>
                                <AlertDialogDescription>
                                  New quotes won&apos;t include it. Quotes already sent keep their own copy.
                                </AlertDialogDescription>
                              </AlertDialogHeader>
                              <AlertDialogFooter>
                                <AlertDialogCancel>Cancel</AlertDialogCancel>
                                <AlertDialogAction variant="destructive" onClick={() => deleteRule(rule)}>Remove</AlertDialogAction>
                              </AlertDialogFooter>
                            </AlertDialogContent>
                          </AlertDialog>
                        </div>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  )
}

function Stat({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <Card size="sm">
      <CardContent className="space-y-1">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p className="text-lg tracking-tight tabular-nums sm:text-2xl">{value}</p>
        <p className="text-xs text-muted-foreground">{note}</p>
      </CardContent>
    </Card>
  )
}
