"use client"

import { useRouter } from "next/navigation"
import { useState } from "react"
import { Boxes, Loader2, Pencil, Plus } from "lucide-react"
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ApiError, api } from "@/lib/api/client"
import type { InventoryItem } from "@/lib/api/types"
import { blankToNull, formatNumber } from "@/lib/format"

const ENDPOINT = "/business/inventory"

function ItemDialog({ item, trigger }: { item?: InventoryItem; trigger: React.ReactNode }) {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [pending, setPending] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const initial = () => ({
    name: item?.name ?? "",
    sku: item?.sku ?? "",
    unit_label: item?.unit_label ?? "",
    quantity: item?.quantity ?? "0",
    low_stock_threshold: item?.low_stock_threshold ?? "",
  })
  const [form, setForm] = useState(initial)

  function onOpenChange(next: boolean) {
    setOpen(next)
    if (next) {
      setForm(initial())
      setErrors({})
    }
  }

  const set = (name: keyof ReturnType<typeof initial>) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [name]: e.target.value })

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    setPending(true)
    setErrors({})
    const body = {
      name: form.name.trim(),
      sku: blankToNull(form.sku),
      unit_label: form.unit_label.trim(),
      quantity: form.quantity.trim() || "0",
      low_stock_threshold: blankToNull(form.low_stock_threshold),
    }
    try {
      if (item) await api(`${ENDPOINT}/${item.id}`, { method: "PATCH", body })
      else await api(ENDPOINT, { method: "POST", body })
      toast.success(item ? "Item updated" : `${body.name} added`)
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
            <DialogTitle>{item ? "Edit item" : "New stock item"}</DialogTitle>
            <DialogDescription>
              What you hold. Rivon checks quantities before quoting a job that needs them.
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField id="item-name" label="Item" error={errors.name} className="sm:col-span-2">
              <Input id="item-name" value={form.name} onChange={set("name")} placeholder="Solar module 430W" autoFocus />
            </FormField>
            <FormField id="item-sku" label="Code" error={errors.sku} hint="Optional">
              <Input id="item-sku" value={form.sku} onChange={set("sku")} placeholder="PV-430" />
            </FormField>
            <FormField id="item-unit" label="Counted in" error={errors.unit_label} hint="panel, kWh, metre">
              <Input id="item-unit" value={form.unit_label} onChange={set("unit_label")} placeholder="panel" />
            </FormField>
            <FormField id="item-quantity" label="In stock" error={errors.quantity}>
              <Input id="item-quantity" inputMode="decimal" value={form.quantity} onChange={set("quantity")} />
            </FormField>
            <FormField
              id="item-threshold"
              label="Warn below"
              error={errors.low_stock_threshold}
              hint="Optional. A warning, never a block."
            >
              <Input
                id="item-threshold"
                inputMode="decimal"
                value={form.low_stock_threshold}
                onChange={set("low_stock_threshold")}
              />
            </FormField>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending || !form.name.trim() || !form.unit_label.trim()}>
              {pending && <Loader2 className="animate-spin" />}
              {item ? "Save" : "Add item"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function InventoryClient({ items, canEdit }: { items: InventoryItem[]; canEdit: boolean }) {
  const addButton = canEdit && (
    <ItemDialog
      trigger={
        <Button>
          <Plus /> New item
        </Button>
      }
    />
  )

  if (items.length === 0) {
    return (
      <EmptyState
        icon={Boxes}
        title="No stock yet"
        text="Add the parts you keep: panels, inverters, mounting, cable. Quantities are checked before a job is quoted."
        action={addButton}
      />
    )
  }

  const low = items.filter((i) => i.low_stock).length

  return (
    <>
      <div className="mb-4 flex items-center justify-between gap-3">
        {low > 0 ? (
          <Badge variant="outline" className="level-warn">
            {low} item{low === 1 ? "" : "s"} running low
          </Badge>
        ) : (
          <span />
        )}
        {addButton}
      </div>
      <Card className="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Item</TableHead>
              <TableHead className="hidden sm:table-cell">Code</TableHead>
              <TableHead className="text-right">In stock</TableHead>
              <TableHead className="hidden text-right sm:table-cell">Warn below</TableHead>
              {canEdit && <TableHead className="w-24" />}
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.id}>
                <TableCell className="pl-6">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{item.name}</span>
                    {item.low_stock && (
                      <Badge variant="outline" className="level-warn">
                        Low
                      </Badge>
                    )}
                  </span>
                </TableCell>
                <TableCell className="hidden text-muted-foreground sm:table-cell">{item.sku ?? "—"}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatNumber(item.quantity)}
                  <span className="text-muted-foreground"> {item.unit_label}</span>
                </TableCell>
                <TableCell className="hidden text-right tabular-nums text-muted-foreground sm:table-cell">
                  {item.low_stock_threshold ? formatNumber(item.low_stock_threshold) : "—"}
                </TableCell>
                {canEdit && (
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <ItemDialog
                        item={item}
                        trigger={
                          <Button variant="ghost" size="icon" aria-label={`Edit ${item.name}`}>
                            <Pencil />
                          </Button>
                        }
                      />
                      <ConfirmDelete
                        endpoint={`${ENDPOINT}/${item.id}`}
                        name={item.name}
                        description="Jobs needing it will no longer be checked against your stock."
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
