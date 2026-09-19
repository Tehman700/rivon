"use client"

import { useRouter } from "next/navigation"
import { useState } from "react"
import { Loader2 } from "lucide-react"
import { toast } from "sonner"

import { FormField } from "@/components/form-field"
import { Button } from "@/components/ui/button"
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
import { Switch } from "@/components/ui/switch"
import { ApiError, api } from "@/lib/api/client"
import {
  BASIS_LABELS,
  CATEGORY_LABELS,
  type PricingRule,
  type QuantityBasis,
  type RuleCategory,
} from "@/lib/api/types"
import { formatEuro, formatNumber } from "@/lib/format"

interface Form {
  name: string
  category: RuleCategory
  quantity_basis: QuantityBasis
  quantity_factor: string
  unit_label: string
  unit_cost_eur: string
  included_quantity: string
  minimum_quantity: string
  round_up: boolean
  sort_order: string
}

const DEFAULT_UNIT: Record<QuantityBasis, string> = {
  fixed: "item",
  system_size_kwp: "kWp",
  battery_capacity_kwh: "kWh",
  distance_km: "km",
}

function blank(nextSort: number): Form {
  return {
    name: "",
    category: "materials",
    quantity_basis: "system_size_kwp",
    quantity_factor: "1",
    unit_label: "kWp",
    unit_cost_eur: "",
    included_quantity: "0",
    minimum_quantity: "0",
    round_up: false,
    sort_order: String(nextSort),
  }
}

function fromRule(rule: PricingRule): Form {
  return {
    ...rule,
    quantity_factor: rule.quantity_factor,
    included_quantity: rule.included_quantity,
    minimum_quantity: rule.minimum_quantity,
    sort_order: String(rule.sort_order),
  }
}

const BASIS_WORDS: Record<Exclude<QuantityBasis, "fixed">, { unit: string; noun: string }> = {
  system_size_kwp: { unit: "kWp", noun: "system size" },
  battery_capacity_kwh: { unit: "kWh", noun: "battery capacity" },
  distance_km: { unit: "km", noun: "distance (one way)" },
}

/** Describes the rule in words. It never computes a price: that's the backend's job. */
export function describeRule(f: Pick<Form, keyof Form>): string {
  const unit = f.unit_label || "unit"
  let basis: string
  if (f.quantity_basis === "fixed") {
    basis = `${formatNumber(f.quantity_factor)} ${unit}`
  } else {
    const { unit: basisUnit, noun } = BASIS_WORDS[f.quantity_basis]
    const perUnit = Number(f.quantity_factor) === 1 && unit === basisUnit ? "" : `${formatNumber(f.quantity_factor)} ${unit} `
    basis = `${perUnit}per ${basisUnit} of ${noun}`
  }
  const parts = [basis]
  if (Number(f.included_quantity) > 0) parts.push(`first ${formatNumber(f.included_quantity)} ${unit} free`)
  if (Number(f.minimum_quantity) > 0) parts.push(`at least ${formatNumber(f.minimum_quantity)} ${unit}`)
  if (f.round_up) parts.push("rounded up")
  const cost = f.unit_cost_eur ? `${formatEuro(f.unit_cost_eur)} per ${unit}` : "cost not set"
  const text = `${parts.join(", ")}, at ${cost}`
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export function RuleDialog({
  serviceId,
  rule,
  nextSort = 0,
  trigger,
}: {
  serviceId: string
  rule?: PricingRule
  nextSort?: number
  trigger: React.ReactNode
}) {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [pending, setPending] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [form, setForm] = useState<Form>(() => (rule ? fromRule(rule) : blank(nextSort)))

  function onOpenChange(next: boolean) {
    setOpen(next)
    if (next) {
      setForm(rule ? fromRule(rule) : blank(nextSort))
      setErrors({})
    }
  }

  const set = (name: keyof Form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [name]: e.target.value })

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    setPending(true)
    setErrors({})
    const body = { ...form, name: form.name.trim(), unit_label: form.unit_label.trim(), sort_order: Number(form.sort_order) || 0 }
    const base = `/business/services/${serviceId}/pricing-rules`
    try {
      if (rule) await api(`${base}/${rule.id}`, { method: "PATCH", body })
      else await api(base, { method: "POST", body })
      toast.success(rule ? "Line updated" : "Line added")
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

  const fixed = form.quantity_basis === "fixed"

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <form onSubmit={onSubmit} noValidate className="space-y-6">
          <DialogHeader>
            <DialogTitle>{rule ? "Edit rate card line" : "New rate card line"}</DialogTitle>
            <DialogDescription>Your cost, net of VAT. Rivon adds margin and VAT when it quotes.</DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField id="rule-name" label="Line name" error={errors.name} className="sm:col-span-2">
              <Input id="rule-name" value={form.name} onChange={set("name")} placeholder="Installation labour" autoFocus />
            </FormField>
            <FormField id="rule-category" label="Shown on the quote under" error={errors.category}>
              <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v as RuleCategory })}>
                <SelectTrigger id="rule-category" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FormField>
            <FormField id="rule-basis" label="Quantity is based on" error={errors.quantity_basis}>
              <Select
                value={form.quantity_basis}
                onValueChange={(v) => {
                  const basis = v as QuantityBasis
                  const unitWasDefault = form.unit_label === DEFAULT_UNIT[form.quantity_basis]
                  setForm({ ...form, quantity_basis: basis, unit_label: unitWasDefault ? DEFAULT_UNIT[basis] : form.unit_label })
                }}
              >
                <SelectTrigger id="rule-basis" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(BASIS_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FormField>
            <FormField
              id="rule-factor"
              label={fixed ? "Quantity" : "Multiply by"}
              error={errors.quantity_factor}
              hint={fixed ? "e.g. 1 inverter" : "e.g. 2.5 hours per kWp, 2 for a return trip"}
            >
              <Input id="rule-factor" inputMode="decimal" value={form.quantity_factor} onChange={set("quantity_factor")} />
            </FormField>
            <FormField id="rule-unit" label="Unit" error={errors.unit_label} hint="Shown on the quote: h, kWp, km, item">
              <Input id="rule-unit" value={form.unit_label} onChange={set("unit_label")} />
            </FormField>
            <FormField id="rule-cost" label="Your cost per unit (€)" error={errors.unit_cost_eur}>
              <Input id="rule-cost" inputMode="decimal" value={form.unit_cost_eur} onChange={set("unit_cost_eur")} placeholder="48.00" />
            </FormField>
            <FormField id="rule-sort" label="Position" error={errors.sort_order} hint="Lower numbers come first">
              <Input id="rule-sort" inputMode="numeric" value={form.sort_order} onChange={set("sort_order")} />
            </FormField>
            <FormField id="rule-included" label="Included free" error={errors.included_quantity} hint="e.g. first 30 km">
              <Input id="rule-included" inputMode="decimal" value={form.included_quantity} onChange={set("included_quantity")} />
            </FormField>
            <FormField id="rule-minimum" label="Minimum charged" error={errors.minimum_quantity} hint="e.g. at least 8 hours">
              <Input id="rule-minimum" inputMode="decimal" value={form.minimum_quantity} onChange={set("minimum_quantity")} />
            </FormField>
            <label className="flex items-center gap-3 text-sm sm:col-span-2">
              <Switch checked={form.round_up} onCheckedChange={(on) => setForm({ ...form, round_up: on })} />
              Round the quantity up to a whole number
            </label>
          </div>

          <p className="rounded-lg bg-muted px-4 py-3 text-sm">
            <span className="text-muted-foreground">In words: </span>
            {describeRule(form)}
          </p>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={pending || !form.name.trim() || !form.unit_cost_eur.trim()}>
              {pending && <Loader2 className="animate-spin" />}
              {rule ? "Save line" : "Add line"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
