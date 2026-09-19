"use client"

import { useRouter } from "next/navigation"
import { useState } from "react"
import { Loader2 } from "lucide-react"
import { toast } from "sonner"

import { FormField } from "@/components/form-field"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ApiError, api } from "@/lib/api/client"
import { WEEKDAYS, type BusinessProfile, type BusinessProfileInput, type WeeklyHours } from "@/lib/api/types"
import { blankToNull } from "@/lib/format"
import { COUNTRIES, TIMEZONES } from "@/lib/geo"

import { HoursEditor, emptyHours, hoursProblem } from "./hours-editor"

type TextFields = Exclude<keyof BusinessProfileInput, "business_hours" | "project_size_unit">
type FormState = Record<TextFields, string> & { business_hours: WeeklyHours }

const NONE = "__none__"

function toForm(profile: BusinessProfile | null): FormState {
  return {
    name: profile?.name ?? "",
    assistant_name: profile?.assistant_name ?? "Rivon",
    contact_email: profile?.contact_email ?? "",
    contact_phone: profile?.contact_phone ?? "",
    website: profile?.website ?? "",
    address_line: profile?.address_line ?? "",
    city: profile?.city ?? "",
    postal_code: profile?.postal_code ?? "",
    country: profile?.country ?? "",
    timezone: profile?.timezone ?? "Europe/Berlin",
    business_hours: { ...emptyHours(), ...(profile?.business_hours ?? {}) },
    min_project_size: profile?.min_project_size ?? "",
    max_project_size: profile?.max_project_size ?? "",
    min_project_value_eur: profile?.min_project_value_eur ?? "",
    max_project_value_eur: profile?.max_project_value_eur ?? "",
  }
}

function toPayload(form: FormState): BusinessProfileInput {
  const size = {
    min: blankToNull(form.min_project_size),
    max: blankToNull(form.max_project_size),
  }
  return {
    name: form.name.trim(),
    assistant_name: form.assistant_name.trim() || "Rivon",
    contact_email: blankToNull(form.contact_email),
    contact_phone: blankToNull(form.contact_phone),
    website: blankToNull(form.website),
    address_line: blankToNull(form.address_line),
    city: blankToNull(form.city),
    postal_code: blankToNull(form.postal_code),
    country: blankToNull(form.country),
    timezone: form.timezone,
    business_hours: form.business_hours,
    min_project_size: size.min,
    max_project_size: size.max,
    project_size_unit: size.min || size.max ? "kWp" : null,
    min_project_value_eur: blankToNull(form.min_project_value_eur),
    max_project_value_eur: blankToNull(form.max_project_value_eur),
  }
}

export function BusinessProfileForm({
  profile,
  canEdit,
}: {
  profile: BusinessProfile | null
  canEdit: boolean
}) {
  const router = useRouter()
  const [form, setForm] = useState<FormState>(() => toForm(profile))
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [pending, setPending] = useState(false)

  const hoursInvalid = WEEKDAYS.some((d) => hoursProblem(form.business_hours[d]) !== null)

  function field(name: TextFields) {
    return {
      id: name,
      value: form[name],
      "aria-invalid": Boolean(errors[name]),
      onChange: (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [name]: e.target.value }),
    }
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    setPending(true)
    setErrors({})
    try {
      await api("/business/profile", { method: "PUT", body: toPayload(form) })
      toast.success("Business profile saved")
      router.refresh()
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fields)
        toast.error(err.message)
      } else {
        toast.error("Couldn't save. Try again.")
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate>
      <fieldset disabled={!canEdit || pending} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Your business</CardTitle>
            <CardDescription>How you appear to customers.</CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <FormField id="name" label="Business name" error={errors.name}>
              <Input {...field("name")} placeholder="Sonnenkraft Solar GmbH" required />
            </FormField>
            <FormField
              id="assistant_name"
              label="Assistant name"
              error={errors.assistant_name}
              hint="What your assistant calls itself. It always says it's an AI."
            >
              <Input {...field("assistant_name")} placeholder="Rivon" />
            </FormField>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Contact and address</CardTitle>
            <CardDescription>Shown on quotations.</CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <FormField id="contact_email" label="Email" error={errors.contact_email}>
              <Input {...field("contact_email")} type="email" placeholder="info@yourcompany.eu" />
            </FormField>
            <FormField id="contact_phone" label="Phone" error={errors.contact_phone}>
              <Input {...field("contact_phone")} type="tel" placeholder="+49 30 1234567" />
            </FormField>
            <FormField id="website" label="Website" error={errors.website} className="md:col-span-2">
              <Input {...field("website")} type="url" placeholder="https://yourcompany.eu" />
            </FormField>
            <FormField id="address_line" label="Street address" error={errors.address_line} className="md:col-span-2">
              <Input {...field("address_line")} />
            </FormField>
            <FormField id="postal_code" label="Postal code" error={errors.postal_code}>
              <Input {...field("postal_code")} />
            </FormField>
            <FormField id="city" label="City" error={errors.city}>
              <Input {...field("city")} />
            </FormField>
            <FormField id="country" label="Country" error={errors.country}>
              <Select
                value={form.country || NONE}
                onValueChange={(v) => setForm({ ...form, country: v === NONE ? "" : v })}
                disabled={!canEdit}
              >
                <SelectTrigger id="country" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>Not set</SelectItem>
                  {COUNTRIES.map((c) => (
                    <SelectItem key={c.code} value={c.code}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FormField>
            <FormField id="timezone" label="Timezone" error={errors.timezone} hint="Used for opening hours and scheduling.">
              <Select value={form.timezone} onValueChange={(v) => setForm({ ...form, timezone: v })} disabled={!canEdit}>
                <SelectTrigger id="timezone" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIMEZONES.map((tz) => (
                    <SelectItem key={tz} value={tz}>
                      {tz.replace("_", " ")}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FormField>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Opening hours</CardTitle>
            <CardDescription>
              When your team is reachable. You can split a day, e.g. a lunch break.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <HoursEditor
              value={form.business_hours}
              onChange={(hours) => setForm({ ...form, business_hours: hours })}
              disabled={!canEdit}
            />
            {errors.business_hours && <p className="mt-2 text-sm text-destructive">{errors.business_hours}</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Jobs you take on</CardTitle>
            <CardDescription>
              Inquiries outside these limits are flagged for you to decide. They are never turned
              away automatically. Leave a field empty for no limit.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <FormField id="min_project_size" label="Smallest system (kWp)" error={errors.min_project_size}>
              <Input {...field("min_project_size")} inputMode="decimal" placeholder="e.g. 3" />
            </FormField>
            <FormField id="max_project_size" label="Largest system (kWp)" error={errors.max_project_size}>
              <Input {...field("max_project_size")} inputMode="decimal" placeholder="e.g. 30" />
            </FormField>
            <FormField id="min_project_value_eur" label="Smallest job value (€)" error={errors.min_project_value_eur}>
              <Input {...field("min_project_value_eur")} inputMode="decimal" placeholder="e.g. 5000" />
            </FormField>
            <FormField id="max_project_value_eur" label="Largest job value (€)" error={errors.max_project_value_eur}>
              <Input {...field("max_project_value_eur")} inputMode="decimal" placeholder="e.g. 60000" />
            </FormField>
          </CardContent>
        </Card>

        {canEdit && (
          <div className="flex justify-end">
            <Button type="submit" size="lg" disabled={pending || !form.name.trim() || hoursInvalid}>
              {pending && <Loader2 className="animate-spin" />}
              Save profile
            </Button>
          </div>
        )}
      </fieldset>
    </form>
  )
}
