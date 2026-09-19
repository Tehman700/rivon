"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { ChevronRight, Plus, Wrench } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { PricingSettings, Service } from "@/lib/api/types"
import { formatPercent } from "@/lib/format"

import { ServiceDialog } from "./service-dialog"

export function ServicesTable({
  services,
  lineCounts,
  settings,
  canEdit,
}: {
  services: Service[]
  lineCounts: Record<string, number>
  settings: PricingSettings | null
  canEdit: boolean
}) {
  const router = useRouter()
  const active = services.filter((s) => !s.archived)
  const archived = services.filter((s) => s.archived)

  const newButton = canEdit && (
    <ServiceDialog
      onCreated={(s) => router.push(`/services/${s.id}`)}
      trigger={
        <Button>
          <Plus /> New service
        </Button>
      }
    />
  )

  function rows(list: Service[]) {
    if (list.length === 0) {
      return (
        <Card className="items-center gap-3 px-6 py-12 text-center">
          <Wrench className="size-8 text-muted-foreground" />
          <p className="font-medium">No services here</p>
          <p className="max-w-sm text-sm text-muted-foreground">
            Add what your customers can ask you for, then give each one a rate card.
          </p>
          {newButton}
        </Card>
      )
    }
    return (
      <Card className="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Service</TableHead>
              <TableHead>Rate card</TableHead>
              <TableHead className="hidden sm:table-cell">Margin</TableHead>
              <TableHead className="hidden sm:table-cell">VAT</TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {list.map((service) => {
              const lines = lineCounts[service.id] ?? 0
              return (
                <TableRow key={service.id} className="cursor-pointer" onClick={() => router.push(`/services/${service.id}`)}>
                  <TableCell className="pl-6">
                    <Link href={`/services/${service.id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>
                      {service.name}
                    </Link>
                    {service.description && (
                      <p className="line-clamp-1 max-w-md text-sm text-muted-foreground">{service.description}</p>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={lines ? "level-good" : "level-warn"}>
                      {lines ? `${lines} line${lines === 1 ? "" : "s"}` : "Not set up"}
                    </Badge>
                  </TableCell>
                  <TableCell className="hidden text-sm sm:table-cell">
                    <Overridable value={service.target_margin_percent} fallback={settings?.default_target_margin_percent} />
                  </TableCell>
                  <TableCell className="hidden text-sm sm:table-cell">
                    <Overridable value={service.vat_rate_percent} fallback={settings?.default_vat_rate_percent} />
                  </TableCell>
                  <TableCell>
                    <ChevronRight className="size-4 text-muted-foreground" />
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </Card>
    )
  }

  return (
    <Tabs defaultValue="active">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <TabsList>
          <TabsTrigger value="active">Active ({active.length})</TabsTrigger>
          <TabsTrigger value="archived">Archived ({archived.length})</TabsTrigger>
        </TabsList>
        {active.length > 0 && newButton}
      </div>
      <TabsContent value="active">{rows(active)}</TabsContent>
      <TabsContent value="archived">{rows(archived)}</TabsContent>
    </Tabs>
  )
}

function Overridable({ value, fallback }: { value: string | null; fallback?: string }) {
  if (value !== null) return <span>{formatPercent(value)}</span>
  return <span className="text-muted-foreground">{fallback ? `${formatPercent(fallback)} (default)` : "Default"}</span>
}
