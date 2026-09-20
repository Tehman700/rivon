import type { Metadata } from "next"
import Link from "next/link"
import { ArrowLeft, Mail } from "lucide-react"

import { SiteFooter } from "@/components/marketing/site-footer"
import { SiteHeader } from "@/components/marketing/site-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export const metadata: Metadata = {
  title: "Request access",
  description: "Rivon is invitation only while we work with our first installers.",
}

const SUBJECT = "Rivon access request"
const BODY = `Business name:
Where you work (city / region):
What you install (e.g. rooftop solar, battery storage):
Roughly how many enquiries a week:
Your name and phone:`

export default function RequestAccessPage() {
  const mailto = `mailto:hello@tideover.site?subject=${encodeURIComponent(SUBJECT)}&body=${encodeURIComponent(BODY)}`

  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full max-w-3xl px-4 py-16 md:py-24">
        <Link href="/" className="mb-6 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" /> Back
        </Link>
        <h1 className="text-3xl tracking-tight sm:text-4xl">Request access</h1>
        <p className="mt-4 max-w-xl text-lg text-muted-foreground">
          Rivon is invitation only for now. We set each business up ourselves so the prices, service
          areas and crews are right before a single customer talks to it.
        </p>

        <Card className="mt-10">
          <CardHeader>
            <CardTitle>Tell us about your business</CardTitle>
            <CardDescription>
              Email us the details below and we&apos;ll reply about a slot. Setup takes about half an
              hour with you on a call.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <ul className="space-y-1 text-sm text-muted-foreground">
              <li>Business name</li>
              <li>Where you work</li>
              <li>What you install</li>
              <li>Roughly how many enquiries a week</li>
              <li>Your name and phone number</li>
            </ul>
            <Button asChild size="lg">
              <a href={mailto}>
                <Mail /> Email hello@tideover.site
              </a>
            </Button>
          </CardContent>
        </Card>

        <p className="mt-8 text-sm text-muted-foreground">
          Already set up?{" "}
          <Link href="/login" className="underline underline-offset-4">
            Sign in
          </Link>
          .
        </p>
      </main>
      <SiteFooter />
    </>
  )
}
