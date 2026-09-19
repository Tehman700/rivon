import type * as React from "react"

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: React.ReactNode
  description?: React.ReactNode
  actions?: React.ReactNode
}) {
  return (
    <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="space-y-1">
        <h1 className="text-2xl">{title}</h1>
        {description && <p className="max-w-2xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 gap-2">{actions}</div>}
    </div>
  )
}

/** Explains why the controls on a page are read-only for this user. */
export function ReadOnlyNotice() {
  return (
    <p className="mb-6 rounded-lg border bg-muted/50 px-4 py-3 text-sm text-muted-foreground">
      You can view this, but only the account owner can change it.
    </p>
  )
}
