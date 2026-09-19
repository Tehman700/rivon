"use client"

import { Plus, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { WEEKDAYS, type OpeningPeriod, type Weekday, type WeeklyHours } from "@/lib/api/types"

const DEFAULT_PERIOD: OpeningPeriod = { opens: "08:00", closes: "17:00" }
const MAX_PERIODS = 4

export function emptyHours(): WeeklyHours {
  return Object.fromEntries(WEEKDAYS.map((d) => [d, []])) as unknown as WeeklyHours
}

/** Checks the same rules as the API so problems show before saving. */
export function hoursProblem(periods: OpeningPeriod[]): string | null {
  const sorted = [...periods].sort((a, b) => a.opens.localeCompare(b.opens))
  for (const p of sorted) {
    if (!p.opens || !p.closes) return "Enter both times"
    if (p.closes <= p.opens) return "Closing time must be after opening time"
  }
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i].opens < sorted[i - 1].closes) return "Opening periods overlap"
  }
  return null
}

export function HoursEditor({
  value,
  onChange,
  disabled,
}: {
  value: WeeklyHours
  onChange: (hours: WeeklyHours) => void
  disabled?: boolean
}) {
  function setDay(day: Weekday, periods: OpeningPeriod[]) {
    onChange({ ...value, [day]: periods })
  }

  return (
    <div className="divide-y rounded-lg border">
      {WEEKDAYS.map((day) => {
        const periods = value[day] ?? []
        const open = periods.length > 0
        const problem = hoursProblem(periods)
        return (
          <div key={day} className="flex flex-col gap-3 p-3 sm:flex-row sm:items-start">
            <label className="flex w-36 shrink-0 items-center gap-3 pt-1.5 text-sm capitalize">
              <Switch
                checked={open}
                disabled={disabled}
                onCheckedChange={(on) => setDay(day, on ? [DEFAULT_PERIOD] : [])}
                aria-label={`Open on ${day}`}
              />
              {day}
            </label>
            <div className="flex-1 space-y-2">
              {!open && <p className="pt-1.5 text-sm text-muted-foreground">Closed</p>}
              {periods.map((period, index) => (
                <div key={index} className="flex items-center gap-2">
                  <Input
                    type="time"
                    aria-label={`${day} opens`}
                    className="w-32"
                    value={period.opens}
                    disabled={disabled}
                    onChange={(e) =>
                      setDay(day, periods.map((p, i) => (i === index ? { ...p, opens: e.target.value } : p)))
                    }
                  />
                  <span className="text-sm text-muted-foreground">to</span>
                  <Input
                    type="time"
                    aria-label={`${day} closes`}
                    className="w-32"
                    value={period.closes}
                    disabled={disabled}
                    onChange={(e) =>
                      setDay(day, periods.map((p, i) => (i === index ? { ...p, closes: e.target.value } : p)))
                    }
                  />
                  {!disabled && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label="Remove period"
                      onClick={() => setDay(day, periods.filter((_, i) => i !== index))}
                    >
                      <X />
                    </Button>
                  )}
                </div>
              ))}
              {open && !disabled && periods.length < MAX_PERIODS && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-muted-foreground"
                  onClick={() => {
                    const last = periods[periods.length - 1]
                    setDay(day, [...periods, { opens: last?.closes ?? "13:00", closes: "18:00" }])
                  }}
                >
                  <Plus /> Add a period
                </Button>
              )}
              {problem && <p className="text-sm text-destructive">{problem}</p>}
            </div>
          </div>
        )
      })}
    </div>
  )
}
