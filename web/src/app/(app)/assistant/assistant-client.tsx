"use client"

import { useState } from "react"
import { Calculator, Loader2 } from "lucide-react"
import { toast } from "sonner"

import { FormField } from "@/components/form-field"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ApiError, api } from "@/lib/api/client"
import type { SizeEstimate, VerticalConfig } from "@/lib/api/types"

export function VerticalSettingsForm({
  config,
  canEdit,
}: {
  config: VerticalConfig
  canEdit: boolean
}) {
  const [form, setForm] = useState({
    annual_kwh_per_kwp: config.settings.annual_kwh_per_kwp,
    roof_area_m2_per_kwp: config.settings.roof_area_m2_per_kwp,
    max_followups: String(config.settings.max_followups),
  })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [pending, setPending] = useState(false)

  const set = (name: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [name]: e.target.value })

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    setPending(true)
    setErrors({})
    try {
      await api("/business/vertical/settings", {
        method: "PUT",
        body: { ...form, max_followups: Number(form.max_followups) },
      })
      toast.success("Saved. New enquiries use these numbers.")
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fields)
        toast.error(err.message)
      } else toast.error("Couldn't save. Try again.")
    } finally {
      setPending(false)
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate>
      <fieldset disabled={!canEdit || pending}>
        <Card>
          <CardHeader>
            <CardTitle>Your numbers</CardTitle>
            <CardDescription>
              Used to work out a system size when the customer doesn&apos;t know theirs. Adjust them
              until the preview below matches what you&apos;d quote.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <FormField
              id="annual_kwh_per_kwp"
              label="Yearly output per kWp"
              error={errors.annual_kwh_per_kwp}
              hint="kWh a year, in your area"
            >
              <Input id="annual_kwh_per_kwp" inputMode="decimal" value={form.annual_kwh_per_kwp} onChange={set("annual_kwh_per_kwp")} />
            </FormField>
            <FormField
              id="roof_area_m2_per_kwp"
              label="Roof needed per kWp"
              error={errors.roof_area_m2_per_kwp}
              hint="m², with your usual panels"
            >
              <Input id="roof_area_m2_per_kwp" inputMode="decimal" value={form.roof_area_m2_per_kwp} onChange={set("roof_area_m2_per_kwp")} />
            </FormField>
            <FormField
              id="max_followups"
              label="Times to chase an answer"
              error={errors.max_followups}
              hint="Then it hands the conversation to you"
            >
              <Input id="max_followups" inputMode="numeric" value={form.max_followups} onChange={set("max_followups")} />
            </FormField>
          </CardContent>
        </Card>
        {canEdit && (
          <div className="mt-4 flex justify-end">
            <Button type="submit" disabled={pending}>
              {pending && <Loader2 className="animate-spin" />}
              Save numbers
            </Button>
          </div>
        )}
      </fieldset>
    </form>
  )
}

export function SizePreview() {
  const [usage, setUsage] = useState("11400")
  const [roof, setRoof] = useState("")
  const [result, setResult] = useState<SizeEstimate | null>(null)
  const [pending, setPending] = useState(false)

  async function check(event: React.FormEvent) {
    event.preventDefault()
    setPending(true)
    try {
      const body: Record<string, string> = {}
      if (usage.trim()) body.annual_consumption_kwh = usage.trim()
      if (roof.trim()) body.roof_area_m2 = roof.trim()
      setResult(await api<SizeEstimate>("/business/vertical/size-estimate", { method: "POST", body }))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't work that out. Try again.")
    } finally {
      setPending(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Try it</CardTitle>
        <CardDescription>
          The same arithmetic a quotation will use. Nothing here is guessed by a model.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={check} className="grid grid-cols-1 items-end gap-4 sm:grid-cols-[1fr_1fr_auto]">
          <FormField id="preview-usage" label="Customer uses (kWh a year)">
            <Input id="preview-usage" inputMode="decimal" value={usage} onChange={(e) => setUsage(e.target.value)} />
          </FormField>
          <FormField id="preview-roof" label="Usable roof (m²)" hint="Optional">
            <Input id="preview-roof" inputMode="decimal" value={roof} onChange={(e) => setRoof(e.target.value)} placeholder="e.g. 40" />
          </FormField>
          <Button type="submit" variant="outline" disabled={pending}>
            {pending ? <Loader2 className="animate-spin" /> : <Calculator />}
            Work it out
          </Button>
        </form>

        {result && (
          <div className="mt-6 rounded-lg border bg-muted/40 p-4">
            {result.system_size_kwp ? (
              <p className="text-2xl tracking-tight tabular-nums">
                {result.system_size_kwp} <span className="text-muted-foreground">kWp</span>
              </p>
            ) : (
              <p className="text-lg">No size yet</p>
            )}
            <p className="mt-1 text-sm text-muted-foreground">{result.explanation}</p>
            {result.missing_for_quote.length > 0 && (
              <p className="mt-3 text-sm text-muted-foreground">
                Still needed before quoting:{" "}
                {result.missing_for_quote.map((m) => (
                  <Badge key={m} variant="outline" className="mr-1 font-normal">
                    {m.replaceAll("_", " ")}
                  </Badge>
                ))}
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
