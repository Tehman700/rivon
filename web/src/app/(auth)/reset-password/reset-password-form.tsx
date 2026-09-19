"use client"

import Link from "next/link"
import { useState } from "react"
import { CheckCircle2, Loader2 } from "lucide-react"

import { FormField } from "@/components/form-field"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError, postAuth } from "@/lib/api/client"

const MIN_LENGTH = 12

export function ResetPasswordForm({ token }: { token: string }) {
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [pending, setPending] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const tooShort = password.length > 0 && password.length < MIN_LENGTH
  const mismatch = confirm.length > 0 && confirm !== password

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      await postAuth("/password-reset/confirm", { token, new_password: password })
      setDone(true)
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 400
          ? "This link has expired or was already used. Ask for a new one."
          : err instanceof ApiError
            ? err.message
            : "Couldn't reach Rivon. Try again.",
      )
    } finally {
      setPending(false)
    }
  }

  if (done) {
    return (
      <div className="space-y-4">
        <Alert className="level-good">
          <CheckCircle2 />
          <AlertDescription className="text-inherit">
            Password set. You&apos;ve been signed out everywhere else.
          </AlertDescription>
        </Alert>
        <Button asChild className="w-full">
          <Link href="/login">Sign in</Link>
        </Button>
      </div>
    )
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      {error && (
        <Alert variant="destructive">
          <AlertDescription>
            {error}{" "}
            <Link href="/forgot-password" className="underline underline-offset-4">
              New link
            </Link>
          </AlertDescription>
        </Alert>
      )}
      <FormField
        id="password"
        label="New password"
        error={tooShort ? `At least ${MIN_LENGTH} characters` : undefined}
      >
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          value={password}
          aria-invalid={tooShort}
          onChange={(e) => setPassword(e.target.value)}
        />
      </FormField>
      <FormField id="confirm" label="Confirm password" error={mismatch ? "Passwords don't match" : undefined}>
        <Input
          id="confirm"
          type="password"
          autoComplete="new-password"
          value={confirm}
          aria-invalid={mismatch}
          onChange={(e) => setConfirm(e.target.value)}
        />
      </FormField>
      <Button
        type="submit"
        className="w-full"
        disabled={pending || password.length < MIN_LENGTH || password !== confirm}
      >
        {pending && <Loader2 className="animate-spin" />}
        Set password
      </Button>
    </form>
  )
}
