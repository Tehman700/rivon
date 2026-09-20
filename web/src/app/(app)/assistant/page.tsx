import type { Metadata } from "next"
import { MessagesSquare } from "lucide-react"

import { PageHeader, ReadOnlyNotice } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { apiGet, getMe } from "@/lib/api/server"
import type { VerticalConfig } from "@/lib/api/types"

import { SizePreview, VerticalSettingsForm } from "./assistant-client"

export const metadata: Metadata = { title: "Assistant & sizing" }

export default async function AssistantPage() {
  const [me, config] = await Promise.all([getMe(), apiGet<VerticalConfig>("/business/vertical")])
  if (!config) return null
  const canEdit = me.role === "owner"

  return (
    <>
      <PageHeader
        title="Assistant & sizing"
        description="What your assistant asks a customer, and how their answers become the system size a quote is priced from."
      />
      {!canEdit && <ReadOnlyNotice />}

      <div className="space-y-6">
        <VerticalSettingsForm config={config} canEdit={canEdit} />
        <SizePreview />

        <Card>
          <CardHeader>
            <CardTitle>What it asks</CardTitle>
            <CardDescription>
              The same questions for every solar installer, so answers can be relied on. It asks only
              for what&apos;s still missing, and says up front that it&apos;s an assistant.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {config.groups.map((group) => (
              <div key={group.key}>
                <p className="mb-2 text-sm font-medium">{group.label}</p>
                <ul className="divide-y rounded-lg border">
                  {group.fields.map((field) => (
                    <li key={field.name} className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-baseline sm:gap-4">
                      <span className="flex w-56 shrink-0 items-center gap-2 text-sm">
                        {field.label}
                        {field.required && (
                          <Badge variant="outline" className="font-normal">
                            Needed
                          </Badge>
                        )}
                      </span>
                      <span className="flex-1 text-sm text-muted-foreground">
                        <MessagesSquare className="mr-1 inline size-3.5 align-[-2px]" />
                        {field.question}
                        {field.unit && <span className="ml-1">({field.unit})</span>}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            <p className="text-sm text-muted-foreground">
              A quote also needs one of:{" "}
              {config.required_any_of.flat().map((name) => (
                <Badge key={name} variant="outline" className="mr-1 font-normal">
                  {name.replaceAll("_", " ")}
                </Badge>
              ))}
            </p>
          </CardContent>
        </Card>
      </div>
    </>
  )
}
