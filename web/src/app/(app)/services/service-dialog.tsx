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
import { Textarea } from "@/components/ui/textarea"
import { ApiError, api } from "@/lib/api/client"
import type { Service } from "@/lib/api/types"
import { blankToNull } from "@/lib/format"

/** Create a service, or edit one when `service` is given. */
export function ServiceDialog({
  service,
  trigger,
  onCreated,
}: {
  service?: Service
  trigger: React.ReactNode
  onCreated?: (service: Service) => void
}) {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [pending, setPending] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const initial = () => ({
    name: service?.name ?? "",
    description: service?.description ?? "",
    target_margin_percent: service?.target_margin_percent ?? "",
    vat_rate_percent: service?.vat_rate_percent ?? "",
  })
  const [form, setForm] = useState(initial)

  function reset(next: boolean) {
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
      description: blankToNull(form.description),
      target_margin_percent: blankToNull(form.target_margin_percent),
      vat_rate_percent: blankToNull(form.vat_rate_percent),
    }
    try {
      if (service) {
        await api(`/business/services/${service.id}`, { method: "PATCH", body })
        toast.success("Service updated")
      } else {
        const created = await api<Service>("/business/services", { method: "POST", body })
        toast.success(`${created.name} added`)
        onCreated?.(created)
      }
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

  const set = (name: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm({ ...form, [name]: e.target.value })

  return (
    <Dialog open={open} onOpenChange={reset}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={onSubmit} noValidate className="space-y-6">
          <DialogHeader>
            <DialogTitle>{service ? "Edit service" : "New service"}</DialogTitle>
            <DialogDescription>
              Something customers can ask you for. You&apos;ll add its costs on the next screen.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <FormField id="service-name" label="Name" error={errors.name}>
              <Input id="service-name" value={form.name} onChange={set("name")} placeholder="Rooftop PV installation" autoFocus />
            </FormField>
            <FormField id="service-description" label="Description" error={errors.description} hint="Optional. Helps the assistant explain it.">
              <Textarea id="service-description" value={form.description} onChange={set("description")} rows={3} />
            </FormField>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <FormField
                id="service-margin"
                label="Own target margin (%)"
                error={errors.target_margin_percent}
                hint="Empty = business default"
              >
                <Input id="service-margin" inputMode="decimal" value={form.target_margin_percent} onChange={set("target_margin_percent")} />
              </FormField>
              <FormField id="service-vat" label="Own VAT rate (%)" error={errors.vat_rate_percent} hint="Empty = business default">
                <Input id="service-vat" inputMode="decimal" value={form.vat_rate_percent} onChange={set("vat_rate_percent")} />
              </FormField>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending || !form.name.trim()}>
              {pending && <Loader2 className="animate-spin" />}
              {service ? "Save" : "Add service"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
