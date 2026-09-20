"use client"

import { useRouter } from "next/navigation"
import { useState } from "react"
import { HardHat, Loader2, Pencil, Plus } from "lucide-react"
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
import { Switch } from "@/components/ui/switch"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ApiError, api } from "@/lib/api/client"
import type { Crew } from "@/lib/api/types"
import { formatNumber } from "@/lib/format"

const ENDPOINT = "/business/crews"

function CrewDialog({ crew, trigger }: { crew?: Crew; trigger: React.ReactNode }) {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [pending, setPending] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const initial = () => ({
    name: crew?.name ?? "",
    headcount: String(crew?.headcount ?? 2),
    weekly_capacity_hours: crew?.weekly_capacity_hours ?? "",
    active: crew?.active ?? true,
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
      headcount: Number(form.headcount) || 1,
      weekly_capacity_hours: form.weekly_capacity_hours.trim(),
      active: form.active,
    }
    try {
      if (crew) await api(`${ENDPOINT}/${crew.id}`, { method: "PATCH", body })
      else await api(ENDPOINT, { method: "POST", body })
      toast.success(crew ? "Crew updated" : `${body.name} added`)
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
            <DialogTitle>{crew ? "Edit crew" : "New crew"}</DialogTitle>
            <DialogDescription>
              A team you can send to a job. Capacity in hours per week is enough for Rivon to tell
              whether a job fits, without keeping a calendar.
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField id="crew-name" label="Crew name" error={errors.name} className="sm:col-span-2">
              <Input
                id="crew-name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Team Nord"
                autoFocus
              />
            </FormField>
            <FormField id="crew-headcount" label="People" error={errors.headcount}>
              <Input
                id="crew-headcount"
                inputMode="numeric"
                value={form.headcount}
                onChange={(e) => setForm({ ...form, headcount: e.target.value })}
              />
            </FormField>
            <FormField
              id="crew-hours"
              label="Hours a week"
              error={errors.weekly_capacity_hours}
              hint="Installing hours, not office time"
            >
              <Input
                id="crew-hours"
                inputMode="decimal"
                value={form.weekly_capacity_hours}
                onChange={(e) => setForm({ ...form, weekly_capacity_hours: e.target.value })}
                placeholder="120"
              />
            </FormField>
            <label className="flex items-center gap-3 text-sm sm:col-span-2">
              <Switch checked={form.active} onCheckedChange={(on) => setForm({ ...form, active: on })} />
              Available for new jobs
            </label>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={pending || !form.name.trim() || !form.weekly_capacity_hours.trim()}
            >
              {pending && <Loader2 className="animate-spin" />}
              {crew ? "Save" : "Add crew"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function CrewsClient({ crews, canEdit }: { crews: Crew[]; canEdit: boolean }) {
  const addButton = canEdit && (
    <CrewDialog
      trigger={
        <Button>
          <Plus /> New crew
        </Button>
      }
    />
  )

  if (crews.length === 0) {
    return (
      <EmptyState
        icon={HardHat}
        title="No crews yet"
        text="Add your installation teams and how many hours a week each can work."
        action={addButton}
      />
    )
  }

  const available = crews.filter((c) => c.active)
  const hours = available.reduce((sum, c) => sum + Number(c.weekly_capacity_hours), 0)

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          <span className="text-foreground tabular-nums">{formatNumber(String(hours))} hours</span> a
          week available across {available.length} crew{available.length === 1 ? "" : "s"}
        </p>
        {addButton}
      </div>
      <Card className="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Crew</TableHead>
              <TableHead className="text-right">People</TableHead>
              <TableHead className="text-right">Hours / week</TableHead>
              <TableHead>Status</TableHead>
              {canEdit && <TableHead className="w-24" />}
            </TableRow>
          </TableHeader>
          <TableBody>
            {crews.map((crew) => (
              <TableRow key={crew.id}>
                <TableCell className="pl-6 font-medium">{crew.name}</TableCell>
                <TableCell className="text-right tabular-nums">{crew.headcount}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatNumber(crew.weekly_capacity_hours)}
                </TableCell>
                <TableCell>
                  <Badge variant="outline" className={crew.active ? "level-good" : ""}>
                    {crew.active ? "Available" : "Unavailable"}
                  </Badge>
                </TableCell>
                {canEdit && (
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <CrewDialog
                        crew={crew}
                        trigger={
                          <Button variant="ghost" size="icon" aria-label={`Edit ${crew.name}`}>
                            <Pencil />
                          </Button>
                        }
                      />
                      <ConfirmDelete
                        endpoint={`${ENDPOINT}/${crew.id}`}
                        name={crew.name}
                        description="Their hours will no longer count towards what you can take on."
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
