import type { Metadata } from "next"
import Link from "next/link"
import { ArrowLeft, Mail } from "lucide-react"

import { SiteFooter } from "@/components/marketing/site-footer"
import { SiteHeader } from "@/components/marketing/site-header"
import { Button } from "@/components/ui/button"
import { CONTACT_EMAIL } from "@/lib/contact"

export const metadata: Metadata = {
  title: "Delete your data",
  description:
    "How to ask Rivon to delete the personal data it holds about you, including data received from Facebook, Instagram or WhatsApp.",
}

/**
 * Meta requires a Data Deletion Instructions URL on its own path: it rejects a
 * fragment link into another page. Kept in step with section 13 of the privacy
 * notice, which links here.
 */
const SUBJECT = "Data deletion"
const BODY = `I would like my data deleted.

If you have a Rivon account, the email address on it:

If you messaged a business through Facebook, Instagram or WhatsApp,
the account or phone number you messaged from:

Roughly which business you contacted:`

export default function DataDeletionPage() {
  const mailto = `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(SUBJECT)}&body=${encodeURIComponent(BODY)}`
  const mail = (
    <a href={`mailto:${CONTACT_EMAIL}`} className="underline underline-offset-4 hover:text-foreground">
      {CONTACT_EMAIL}
    </a>
  )

  return (
    <>
      <SiteHeader />

      <main className="mx-auto w-full max-w-3xl px-4 py-16 md:py-24">
        <Link
          href="/"
          className="mb-6 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" /> Back
        </Link>

        <h1 className="text-3xl tracking-tight sm:text-4xl">Delete your data</h1>
        <p className="mt-6 text-lg text-muted-foreground">
          You can ask us to delete everything we hold about you, at any time, for any reason. You
          do not have to give one, and there is no charge.
        </p>

        <div className="mt-10 space-y-10 text-sm leading-relaxed text-muted-foreground sm:text-base">
          <section className="space-y-4">
            <h2 className="text-xl font-medium tracking-tight text-foreground">How to ask</h2>
            <p>
              Email {mail} with the subject line <strong className="text-foreground">Data deletion</strong>, and tell us
              enough to find you:
            </p>
            <ul className="list-disc space-y-2 pl-5">
              <li>
                <strong className="text-foreground">If you have a Rivon account</strong> — the email address on it.
              </li>
              <li>
                <strong className="text-foreground">
                  If you messaged a business through Facebook, Instagram or WhatsApp
                </strong>{" "}
                — the account or phone number you messaged from, and roughly which business you
                contacted.
              </li>
            </ul>
            <Button asChild size="lg">
              <a href={mailto}>
                <Mail /> Email {CONTACT_EMAIL}
              </a>
            </Button>
          </section>

          <section className="space-y-4">
            <h2 className="text-xl font-medium tracking-tight text-foreground">What happens next</h2>
            <ol className="list-decimal space-y-2 pl-5">
              <li>We confirm we have your request, usually within a couple of working days.</li>
              <li>
                We give you a reference so you can check on it, and tell you if anything must be
                kept by law — an invoice, for example — and why.
              </li>
              <li>
                Live records are deleted. Backup copies are overwritten on their normal 30-day
                cycle, so everything is gone within 30 days.
              </li>
              <li>We write to you again to confirm it is done.</li>
            </ol>
          </section>

          <section className="space-y-4">
            <h2 className="text-xl font-medium tracking-tight text-foreground">
              Data we received from Facebook, Instagram or WhatsApp
            </h2>
            <p>
              If you messaged a business that uses Rivon, we may hold the conversation, the
              identifier the platform gave us for you, your display name, and the details of your
              enquiry. That is deleted along with everything else when you ask.
            </p>
            <p>
              A business that connected its Facebook Page or Instagram account to Rivon can also
              remove our access at any time, from Meta Business Settings under connected business
              integrations. That stops us acting on the account immediately, but it does not by
              itself delete anything already stored — so send the email too if that is what you
              want.
            </p>
            <p>
              Deleting data from Rivon does not delete anything held by Meta. For that, use the
              privacy settings in Facebook, Instagram or WhatsApp.
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-xl font-medium tracking-tight text-foreground">
              If you messaged a business rather than using Rivon yourself
            </h2>
            <p>
              For those conversations the business you contacted decides what happens to the data,
              and we act on its instructions. You can ask us directly and we will pass the request
              on and support it — but asking that business as well is usually the fastest route.
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-xl font-medium tracking-tight text-foreground">Your other rights</h2>
            <p>
              Deletion is one of several rights you have. You can also ask for a copy of your data,
              have it corrected, object to it being used, or complain to your national data
              protection authority. The{" "}
              <Link href="/privacy" className="underline underline-offset-4 hover:text-foreground">
                privacy notice
              </Link>{" "}
              explains all of them.
            </p>
          </section>
        </div>
      </main>

      <SiteFooter />
    </>
  )
}
