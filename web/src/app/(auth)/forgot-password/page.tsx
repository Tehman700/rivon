"use client"

import Link from "next/link"
import { useState } from "react"
import { ArrowLeft, Loader2, MailCheck } from "lucide-react"

import { FormField } from "@/components/form-field"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError, postAuth } from "@/lib/api/client"

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("")
  const [sent, setSent] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      await postAuth("/password-reset", { email })
      setSent(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach Rivon. Try again.")
    } finally {
      setPending(false)
    }
  }

  if (sent) {
    return (
      <div className="space-y-4">
        <MailCheck className="size-8 text-muted-foreground" />
        <h1 className="text-2xl">Check your email</h1>
        <p className="text-sm text-muted-foreground">
          If an account exists for <span className="text-foreground">{email}</span>, we&apos;ve sent a
          link to set a new password. It expires in 60 minutes.
        </p>
        <BackToSignIn />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl">Reset your password</h1>
        <p className="text-sm text-muted-foreground">We&apos;ll email you a link to set a new one.</p>
      </div>
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <FormField id="email" label="Email">
          <Input
            id="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </FormField>
        <Button type="submit" className="w-full" disabled={pending || !email}>
          {pending && <Loader2 className="animate-spin" />}
          Send reset link
        </Button>
      </form>
      <BackToSignIn />
    </div>
  )
}

function BackToSignIn() {
  return (
    <Link href="/login" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="size-4" /> Back to sign in
    </Link>
  )
}
