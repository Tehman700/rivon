"use client"

import { useRouter } from "next/navigation"
import { useState } from "react"
import { Loader2, MapPin, Pencil, Plus } from "lucide-react"
import { toast } from "sonner"

import { ConfirmDelete } from "@/components/capacity/confirm-delete"
import { EmptyState } from "@/components/capacity/empty-state"
import { FormField } from "@/components/form-field"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ApiError, api } from "@/lib/api/client"
import type { ServiceArea } from "@/lib/api/types"
import { COUNTRIES } from "@/lib/geo"

const ENDPOINT = "/business/service-areas"

function AreaDialog({
  area,
  defaultCountry,
  trigger,
}: {
  area?: ServiceArea
  defaultCountry: string
  trigger: React.ReactNode
}) {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [pending, setPending] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const initial = () => ({
    name: area?.name ?? "",
    country: area?.country ?? defaultCountry,
    prefixes: (area?.postal_prefixes ?? []).join(", "),
  })
  const [form, setForm] = useState(initial)

  function onOpenChange(next: boolean) {
    setOpen(next)
    if (next) {
      setForm(initial())
      setErrors({})
    }
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    setPending(true)
    setErrors({})
    const body = {
      name: form.name.trim(),
      country: form.country,
      postal_prefixes: form.prefixes
        .split(/[,\s]+/)
        .map((p) => p.trim())
        .filter(Boolean),
    }
    try {
      if (area) await api(`${ENDPOINT}/${area.id}`, { method: "PATCH", body })
      else await api(ENDPOINT, { method: "POST", body })
      toast.success(area ? "Area updated" : `${body.name} added`)
      setOpen(false)
      router.refresh()
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.status === 409 ? { name: err.message } : err.fields)
        if (err.status !== 409 && err.status !== 422) toast.error(err.message)
      } else toast.error("Couldn't save. Try again.")
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={onSubmit} noValidate className="space-y-6">
          <DialogHeader>
            <DialogTitle>{area ? "Edit service area" : "New service area"}</DialogTitle>
            <DialogDescription>
              Somewhere you&apos;ll travel to. Jobs outside your areas are flagged for you, never
              turned away automatically.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <FormField id="area-name" label="Area name" error={errors.name}>
              <Input
                id="area-name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Berlin"
                autoFocus
              />
            </FormField>
            <FormField id="area-country" label="Country" error={errors.country}>
              <Select value={form.country} onValueChange={(v) => setForm({ ...form, country: v })}>
                <SelectTrigger id="area-country" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {COUNTRIES.map((c) => (
                    <SelectItem key={c.code} value={c.code}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FormField>
            <FormField
              id="area-prefixes"
              label="Postcode starts with"
              error={errors.postal_prefixes}
              hint="Optional, comma separated. e.g. 101, 102 covers every postcode starting 101 or 102."
            >
              <Input
                id="area-prefixes"
                value={form.prefixes}
                onChange={(e) => setForm({ ...form, prefixes: e.target.value })}
                placeholder="101, 102"
              />
            </FormField>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending || !form.name.trim()}>
              {pending && <Loader2 className="animate-spin" />}
              {area ? "Save" : "Add area"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function ServiceAreasClient({
  areas,
  defaultCountry,
  canEdit,
}: {
  areas: ServiceArea[]
  defaultCountry: string
  canEdit: boolean
}) {
  const addButton = canEdit && (
    <AreaDialog
      defaultCountry={defaultCountry}
      trigger={
        <Button>
          <Plus /> New area
        </Button>
      }
    />
  )

  if (areas.length === 0) {
    return (
      <EmptyState
        icon={MapPin}
        title="No service areas yet"
        text="Add the cities or regions you travel to. Rivon checks each enquiry's address against them."
        action={addButton}
      />
    )
  }

  return (
    <>
      <div className="mb-4 flex justify-end">{addButton}</div>
      <Card className="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Area</TableHead>
              <TableHead>Country</TableHead>
              <TableHead>Postcodes</TableHead>
              {canEdit && <TableHead className="w-24" />}
            </TableRow>
          </TableHeader>
          <TableBody>
            {areas.map((area) => (
              <TableRow key={area.id}>
                <TableCell className="pl-6 font-medium">{area.name}</TableCell>
                <TableCell>{area.country}</TableCell>
                <TableCell>
                  {area.postal_prefixes.length === 0 ? (
                    <span className="text-muted-foreground">Any in this country</span>
                  ) : (
                    <span className="flex flex-wrap gap-1">
                      {area.postal_prefixes.map((prefix) => (
                        <Badge key={prefix} variant="outline" className="font-normal">
                          {prefix}…
                        </Badge>
                      ))}
                    </span>
                  )}
                </TableCell>
                {canEdit && (
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <AreaDialog
                        area={area}
                        defaultCountry={defaultCountry}
                        trigger={
                          <Button variant="ghost" size="icon" aria-label={`Edit ${area.name}`}>
                            <Pencil />
                          </Button>
                        }
                      />
                      <ConfirmDelete
                        endpoint={`${ENDPOINT}/${area.id}`}
                        name={area.name}
                        description="Enquiries from here will be flagged as outside your areas."
                      />
                    </div>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </>
  )
}
