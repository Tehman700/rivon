import type { Metadata } from "next"

import { LoginForm } from "./login-form"

export const metadata: Metadata = { title: "Sign in" }

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const { next } = await searchParams
  // Only same-site paths, so the link can't bounce users to another site.
  const target = typeof next === "string" && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard"
  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl">Sign in</h1>
        <p className="text-sm text-muted-foreground">Welcome back. Sign in to manage your business.</p>
      </div>
      <LoginForm next={target} />
    </div>
  )
}
