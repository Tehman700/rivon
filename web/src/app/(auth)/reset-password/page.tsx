import type { Metadata } from "next"
import Link from "next/link"

import { ResetPasswordForm } from "./reset-password-form"

export const metadata: Metadata = { title: "Set your password" }

export default async function ResetPasswordPage({ searchParams }: PageProps<"/reset-password">) {
  const { token } = await searchParams
  if (typeof token !== "string" || !token) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl">This link isn&apos;t complete</h1>
        <p className="text-sm text-muted-foreground">
          Open the link from your email again, or ask for a new one.
        </p>
        <Link href="/forgot-password" className="text-sm underline underline-offset-4">
          Request a new link
        </Link>
      </div>
    )
  }
  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl">Set your password</h1>
        <p className="text-sm text-muted-foreground">
          Use at least 12 characters. A few unrelated words work well.
        </p>
      </div>
      <ResetPasswordForm token={token} />
    </div>
  )
}
