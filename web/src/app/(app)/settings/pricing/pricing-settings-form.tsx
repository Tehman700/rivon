"use client"

import { useRouter } from "next/navigation"
import { useState } from "react"
import { Loader2 } from "lucide-react"
import { toast } from "sonner"

import { FormField } from "@/components/form-field"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ApiError, api } from "@/lib/api/client"
import type { PricingSettings } from "@/lib/api/types"
import { formatEuro } from "@/lib/format"

type Form = Omit<PricingSettings, "updated_at">

/** Illustration only: real prices are always computed by the backend. */
function exampleForMargin(margin: string): string | null {
  const m = Number(margin)
  if (margin.trim() === "" || Number.isNaN(m) || m < 0 || m > 95) return null
  return `A ${formatEuro("1000")} cost is quoted at ${formatEuro(String(1000 / (1 - m / 100)))} before VAT.`
}

export function PricingSettingsForm({ settings, canEdit }: { settings: PricingSettings | null; canEdit: boolean }) {
  const router = useRouter()
  const [form, setForm] = useState<Form>({
    default_target_margin_percent: settings?.default_target_margin_percent ?? "",
    minimum_margin_percent: settings?.minimum_margin_percent ?? "",
    default_vat_rate_percent: settings?.default_vat_rate_percent ?? "",
  })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [pending, setPending] = useState(false)

  const input = (name: keyof Form) => ({
    id: name,
    inputMode: "decimal" as const,
    value: form[name],
    "aria-invalid": Boolean(errors[name]),
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [name]: e.target.value }),
  })

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    setPending(true)
    setErrors({})
    try {
      await api("/business/pricing-settings", { method: "PUT", body: form })
      toast.success("Pricing settings saved")
      router.refresh()
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fields)
        toast.error(err.message)
      } else toast.error("Couldn't save. Try again.")
    } finally {
      setPending(false)
    }
  }

  const complete = Object.values(form).every((v) => v.trim() !== "")

  return (
    <form onSubmit={onSubmit} noValidate>
      <fieldset disabled={!canEdit || pending} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Margins</CardTitle>
            <CardDescription>
              You enter your costs; Rivon adds your margin. Margin here means gross margin on the
              selling price, not markup on cost.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <FormField
              id="default_target_margin_percent"
              label="Target margin (%)"
              error={errors.default_target_margin_percent}
              hint={exampleForMargin(form.default_target_margin_percent) ?? "Between 0 and 95."}
            >
              <Input {...input("default_target_margin_percent")} placeholder="30" />
            </FormField>
            <FormField
              id="minimum_margin_percent"
              label="Minimum margin (%)"
              error={errors.minimum_margin_percent}
              hint="Quotes below this are flagged before you approve them."
            >
              <Input {...input("minimum_margin_percent")} placeholder="15" />
            </FormField>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>VAT</CardTitle>
            <CardDescription>
              Quotes show net, VAT and gross. Services can use their own rate, e.g. 0% on home
              solar in Germany.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <FormField id="default_vat_rate_percent" label="Default VAT rate (%)" error={errors.default_vat_rate_percent}>
              <Input {...input("default_vat_rate_percent")} placeholder="19" />
            </FormField>
          </CardContent>
        </Card>

        {canEdit && (
          <div className="flex justify-end">
            <Button type="submit" size="lg" disabled={pending || !complete}>
              {pending && <Loader2 className="animate-spin" />}
              Save pricing
            </Button>
          </div>
        )}
      </fieldset>
    </form>
  )
}
