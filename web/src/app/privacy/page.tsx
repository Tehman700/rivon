import type { Metadata } from "next"
import Link from "next/link"
import { ArrowLeft } from "lucide-react"

import { SiteFooter } from "@/components/marketing/site-footer"
import { SiteHeader } from "@/components/marketing/site-header"
import { CONTACT_EMAIL } from "@/lib/contact"

export const metadata: Metadata = {
  title: "Privacy notice",
  description:
    "How Rivon handles personal data: what we collect, why, where it is stored, and the rights you have under the GDPR.",
}

/** Shown in the header and at the foot of the notice. Update whenever the text changes. */
const LAST_UPDATED = "20 September 2026"

const SECTIONS = [
  { id: "who-we-are", title: "Who we are" },
  { id: "two-roles", title: "Our two roles" },
  { id: "controller-data", title: "Data about business users" },
  { id: "processor-data", title: "Data about your customers" },
  { id: "never", title: "What we never do" },
  { id: "legal-bases", title: "Why we may process it" },
  { id: "automation", title: "Automated decisions and AI" },
  { id: "sharing", title: "Who else sees it" },
  { id: "location", title: "Where data is stored" },
  { id: "retention", title: "How long we keep it" },
  { id: "security", title: "How we protect it" },
  { id: "rights", title: "Your rights" },
  { id: "data-deletion", title: "Deleting your data" },
  { id: "cookies", title: "Cookies" },
  { id: "children", title: "Children" },
  { id: "changes", title: "Changes to this notice" },
  { id: "contact", title: "Contact us" },
]

function Section({
  id,
  title,
  children,
}: {
  id: string
  title: string
  children: React.ReactNode
}) {
  return (
    <section id={id} className="scroll-mt-24 space-y-4">
      <h2 className="text-xl font-medium tracking-tight sm:text-2xl">{title}</h2>
      <div className="space-y-4 text-sm leading-relaxed text-muted-foreground sm:text-base">
        {children}
      </div>
    </section>
  )
}

function Table({ head, rows }: { head: string[]; rows: React.ReactNode[][] }) {
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full min-w-[34rem] border-collapse text-left text-sm">
        <thead className="bg-muted/50">
          <tr>
            {head.map((cell) => (
              <th key={cell} className="px-4 py-3 font-medium text-foreground">
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y">
          {rows.map((row, i) => (
            <tr key={i} className="align-top">
              {row.map((cell, j) => (
                <td key={j} className="px-4 py-3">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function PrivacyPage() {
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

        <h1 className="text-3xl tracking-tight sm:text-4xl">Privacy notice</h1>
        <p className="mt-3 text-sm text-muted-foreground">Last updated {LAST_UPDATED}</p>
        <p className="mt-6 text-lg text-muted-foreground">
          Rivon helps service businesses answer, qualify and quote enquiries. Doing that means
          handling personal data — about the people who use our dashboard, and about the customers
          who message them. This notice explains what we hold, why, and what you can ask us to do
          about it.
        </p>

        <div className="mt-8 rounded-lg border bg-muted/30 p-5 text-sm">
          <p className="font-medium text-foreground">The short version</p>
          <ul className="mt-3 space-y-2 text-muted-foreground">
            <li>All data is stored in the European Union (Frankfurt, Germany).</li>
            <li>We never score anyone&apos;s ability to pay, credit or financial standing.</li>
            <li>
              The assistant always says it is an assistant, at the start of every conversation. That
              cannot be switched off.
            </li>
            <li>No advertising cookies, no analytics trackers, no selling data to anyone.</li>
            <li>
              You can ask for a copy of your data, or its deletion, at any time — see{" "}
              <a href="#rights" className="underline underline-offset-4 hover:text-foreground">
                Your rights
              </a>
              .
            </li>
          </ul>
        </div>

        <nav aria-label="Contents" className="mt-10 rounded-lg border p-5">
          <p className="text-sm font-medium">Contents</p>
          <ol className="mt-3 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
            {SECTIONS.map((section, i) => (
              <li key={section.id} className="text-muted-foreground">
                <a href={`#${section.id}`} className="hover:text-foreground hover:underline underline-offset-4">
                  <span className="tabular-nums">{i + 1}.</span> {section.title}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <div className="mt-12 space-y-12">
          <Section id="who-we-are" title="1. Who we are">
            <p>
              Rivon is a software service for service businesses — solar installers first — that
              answers incoming enquiries, works out whether a job is feasible, and prepares a
              quotation.
            </p>
            <p>
              Rivon is currently operated by its founding team and is not yet incorporated as a
              company. We will name the legal entity here as soon as it is registered, and tell
              existing customers when we do. Until then, the contact point for anything in this
              notice, including any request about your data, is {mail}.
            </p>
            <p>
              We are in an early stage: Rivon is used by a small number of invited businesses while
              we build it. The practices described here apply from the moment any real personal data
              reaches the service.
            </p>
          </Section>

          <Section id="two-roles" title="2. Our two roles">
            <p>
              Data protection law distinguishes between deciding <em>why</em> data is processed and
              merely handling it for someone else. Rivon does both, in different places, and it
              changes who you should talk to.
            </p>
            <Table
              head={["Whose data", "Our role", "Who decides what happens to it"]}
              rows={[
                [
                  <>People who use the Rivon dashboard — business owners, managers, agents</>,
                  <strong key="c">Controller</strong>,
                  <>We do.</>,
                ],
                [
                  <>
                    People who message a business through WhatsApp, Messenger, Instagram or a web
                    form
                  </>,
                  <strong key="p">Processor</strong>,
                  <>
                    The business they contacted does. We act on that business&apos;s instructions
                    and do not use the data for our own purposes.
                  </>,
                ],
              ]}
            />
            <p>
              So if you messaged a solar installer and want your data removed, the quickest route is
              to ask that installer. You can also write to us at {mail} and we will pass the request
              on and support it.
            </p>
          </Section>

          <Section id="controller-data" title="3. Data about business users">
            <p>If you have a Rivon account, we hold:</p>
            <Table
              head={["Category", "What it includes"]}
              rows={[
                [
                  <strong key="a">Account</strong>,
                  <>
                    Email address, a one-way hash of your password (never the password itself), your
                    role, which business you belong to, and when the account was created and last
                    changed.
                  </>,
                ],
                [
                  <strong key="b">Business configuration</strong>,
                  <>
                    What you enter to set the service up: business name and contact details,
                    address, opening hours, services, rate cards, service areas, stock and crews.
                    Mostly not personal data, though an address or a contact name can be.
                  </>,
                ],
                [
                  <strong key="c">Technical and security</strong>,
                  <>
                    IP address, browser type and timestamps in our server logs; records of sign-ins,
                    failed sign-in attempts, password resets and session refreshes.
                  </>,
                ],
                [
                  <strong key="d">Correspondence</strong>,
                  <>Emails and messages you send us, and our replies.</>,
                ],
              ]}
            />
          </Section>

          <Section id="processor-data" title="4. Data about your customers">
            <p>
              When someone contacts a business that uses Rivon, we handle the following{" "}
              <em>on that business&apos;s behalf</em>:
            </p>
            <Table
              head={["Category", "What it includes"]}
              rows={[
                [
                  <strong key="a">Messages</strong>,
                  <>
                    The conversation itself — what the customer wrote, what the assistant replied,
                    any photos or documents they sent, and the times.
                  </>,
                ],
                [
                  <strong key="b">Contact details</strong>,
                  <>
                    Whatever the channel provides: a phone number on WhatsApp, a platform-issued
                    identifier and display name on Messenger or Instagram, and a name, email address
                    or phone number if the customer gives one.
                  </>,
                ],
                [
                  <strong key="c">Enquiry details</strong>,
                  <>
                    What the job needs: postal code, property type, roof type, annual electricity
                    consumption, whether a battery is wanted, timeframe, and whether the customer
                    owns the property.
                  </>,
                ],
                [
                  <strong key="d">Qualification result</strong>,
                  <>
                    A score representing how well the enquiry fits the business, the inputs that
                    produced it, and the version of the model used — so any score can be explained
                    afterwards.
                  </>,
                ],
                [
                  <strong key="e">Outcome</strong>,
                  <>Whether the job looks feasible, and the quotation prepared for it.</>,
                ],
              ]}
            />
            <p>
              Consent to be contacted, where a channel requires it, is recorded with the version of
              the wording that was shown, so it is always clear what was agreed to and when.
            </p>
          </Section>

          <Section id="never" title="5. What we never do">
            <p>These are design decisions built into the software, not just promises:</p>
            <ul className="list-disc space-y-2 pl-5">
              <li>
                <strong className="text-foreground">
                  We never assess anyone&apos;s ability to pay, payment history or financial
                  standing.
                </strong>{" "}
                Our scoring looks only at how urgent and complete an enquiry is, and how well it
                fits what the business does. Creditworthiness assessment is deliberately out of
                scope.
              </li>
              <li>
                <strong className="text-foreground">We never sell personal data</strong>, and we do
                not share it for anyone else&apos;s advertising.
              </li>
              <li>
                <strong className="text-foreground">
                  We never use one business&apos;s data for another.
                </strong>{" "}
                Every record is tagged with the business it belongs to, and the database enforces
                that separation independently of the application.
              </li>
              <li>
                <strong className="text-foreground">
                  We do not use your customers&apos; conversations to train AI models.
                </strong>
              </li>
              <li>
                <strong className="text-foreground">We never hide that a customer is talking to an assistant.</strong>
              </li>
            </ul>
          </Section>

          <Section id="legal-bases" title="6. Why we may process it">
            <p>Under the GDPR, each purpose needs a lawful basis. Ours are:</p>
            <Table
              head={["What we do", "Why", "Lawful basis"]}
              rows={[
                [
                  <>Run your account and provide the service</>,
                  <>You asked us to</>,
                  <>Performance of a contract — Art 6(1)(b)</>,
                ],
                [
                  <>Keep the service secure, prevent abuse, keep logs</>,
                  <>Protecting the service and its users</>,
                  <>Legitimate interests — Art 6(1)(f)</>,
                ],
                [
                  <>Answer support requests</>,
                  <>You contacted us</>,
                  <>Legitimate interests / contract</>,
                ],
                [
                  <>Keep accounting and tax records</>,
                  <>We are required to</>,
                  <>Legal obligation — Art 6(1)(c)</>,
                ],
                [
                  <>Handle customer conversations</>,
                  <>The business instructed us to</>,
                  <>
                    Determined by that business as controller — usually steps taken at the
                    customer&apos;s own request, Art 6(1)(b), or legitimate interests
                  </>,
                ],
              ]}
            />
          </Section>

          <Section id="automation" title="7. Automated decisions and AI">
            <p>
              Rivon uses automation in two places, and we think it matters that you understand
              exactly where.
            </p>
            <p>
              <strong className="text-foreground">Prices and feasibility are calculated, not generated.</strong>{" "}
              Every number in a quotation comes from arithmetic on the rate card the business
              entered. No language model produces a price, a system size or a feasibility verdict.
              The assistant writes the words around numbers that ordinary code has computed.
            </p>
            <p>
              <strong className="text-foreground">Scoring never decides anything on its own.</strong> An
              enquiry gets a score for intent, urgency, completeness and fit. It is a sorting aid
              for the business, not a verdict on a person. We store the inputs and the model version
              behind every score so it can be explained on request.
            </p>
            <p>
              <strong className="text-foreground">No enquiry is finally rejected by a machine.</strong> Where
              a job looks unfeasible, the outcome is either confirmed by a person at the business or
              recorded as provisional with a route to human review. You will not be turned away by
              software with nobody to appeal to.
            </p>
            <p>
              <strong className="text-foreground">The assistant identifies itself.</strong> At the start of
              every conversation, customers are told they are talking to an automated assistant, and
              that disclosure is logged. Businesses using Rivon cannot disable it. A human can take
              over a conversation at any point.
            </p>
          </Section>

          <Section id="sharing" title="8. Who else sees it">
            <p>
              We use a small number of suppliers to run the service. They process data on our
              instructions, under contract, and nothing more.
            </p>
            <Table
              head={["Supplier", "What for", "Where"]}
              rows={[
                [<>Neon</>, <>The database</>, <>Frankfurt, Germany</>],
                [<>Amazon Web Services</>, <>Application servers and file storage</>, <>Frankfurt, Germany</>],
                [<>Vercel</>, <>Serving the dashboard and website</>, <>Frankfurt, Germany</>],
                [
                  <>Meta Platforms</>,
                  <>Delivering messages on WhatsApp, Messenger and Instagram</>,
                  <>Ireland / United States</>,
                ],
                [
                  <>OpenAI, Google</>,
                  <>Understanding and writing conversation text. Not yet in use</>,
                  <>European Union / United States</>,
                ],
              ]}
            />
            <p>
              We may also disclose data where the law requires it, or to establish or defend a legal
              claim. If Rivon is ever sold or merged, data may transfer to the buyer, and we will
              tell you before that happens.
            </p>
            <p>
              Where a supplier processes data outside the European Economic Area, that transfer is
              covered by the European Commission&apos;s standard contractual clauses or an adequacy
              decision. If you message a business through WhatsApp, Messenger or Instagram, Meta
              also handles your data in its own right, under its own privacy policy — using those
              apps is a choice you make with Meta, not with us.
            </p>
          </Section>

          <Section id="location" title="9. Where data is stored">
            <p>
              Everything Rivon stores sits in the European Union — specifically Frankfurt, Germany.
              The database, the application servers, file storage and the web front end are all
              hosted there. Businesses are tagged with their region, and data belonging to an EU
              business stays in the EU.
            </p>
          </Section>

          <Section id="retention" title="10. How long we keep it">
            <Table
              head={["What", "How long"]}
              rows={[
                [<>Your account and business configuration</>, <>While the account is open, then 30 days</>],
                [
                  <>Customer conversations, enquiries and quotations</>,
                  <>
                    As instructed by the business that owns them. Where no instruction is given, 24
                    months from the last message
                  </>,
                ],
                [<>Security and server logs</>, <>90 days</>],
                [<>Backups</>, <>30 days, after which they are overwritten</>],
                [<>Accounting records</>, <>As long as tax law requires</>],
              ]}
            />
            <p>
              A deletion request is honoured within backups&apos; normal rotation: the live data goes
              immediately, and backup copies age out within 30 days.
            </p>
          </Section>

          <Section id="security" title="11. How we protect it">
            <ul className="list-disc space-y-2 pl-5">
              <li>Everything travels over encrypted connections, and is encrypted at rest.</li>
              <li>
                Passwords are stored as one-way hashes using a modern algorithm. Nobody at Rivon can
                read your password.
              </li>
              <li>
                Access tokens for connected WhatsApp, Messenger and Instagram accounts are encrypted
                separately before they reach the database.
              </li>
              <li>
                Each business&apos;s data is separated at the database level as well as in the
                application, so a bug in one layer cannot expose another business&apos;s records.
              </li>
              <li>Session cookies are HTTP-only and cannot be read by scripts in the browser.</li>
              <li>Access to production systems is limited to the people who need it.</li>
            </ul>
            <p>
              If a breach ever occurs that is likely to put people at risk, we will notify the
              relevant supervisory authority within 72 hours and tell those affected without undue
              delay.
            </p>
          </Section>

          <Section id="rights" title="12. Your rights">
            <p>If you are in the EU or the UK, you have the right to:</p>
            <ul className="list-disc space-y-2 pl-5">
              <li>
                <strong className="text-foreground">Access</strong> — get a copy of the personal data we hold
                about you.
              </li>
              <li>
                <strong className="text-foreground">Rectification</strong> — have inaccurate data corrected.
              </li>
              <li>
                <strong className="text-foreground">Erasure</strong> — have your data deleted, where there is
                no overriding reason to keep it.
              </li>
              <li>
                <strong className="text-foreground">Restriction</strong> — have us pause processing while a
                dispute is resolved.
              </li>
              <li>
                <strong className="text-foreground">Portability</strong> — receive your data in a
                machine-readable form, or have it sent elsewhere.
              </li>
              <li>
                <strong className="text-foreground">Objection</strong> — object to processing based on
                legitimate interests, including being profiled or scored.
              </li>
              <li>
                <strong className="text-foreground">Withdraw consent</strong> at any time, where processing
                relies on it. This does not undo what was done beforehand.
              </li>
              <li>
                <strong className="text-foreground">Complain</strong> to your national data protection
                authority. You can do this whether or not you contact us first.
              </li>
            </ul>
            <p>
              Write to {mail}. We respond within one month, and will tell you if a request needs
              longer. There is no charge unless a request is clearly excessive. If you contacted a
              business through Rivon rather than holding an account, see{" "}
              <a href="#two-roles" className="underline underline-offset-4 hover:text-foreground">
                Our two roles
              </a>{" "}
              first.
            </p>
          </Section>

          <Section id="data-deletion" title="13. Deleting your data">
            <p>To have your data removed, email {mail} with the subject line “Data deletion”, and:</p>
            <ul className="list-disc space-y-2 pl-5">
              <li>
                if you have a Rivon account, the email address on it; or
              </li>
              <li>
                if you messaged a business through WhatsApp, Messenger or Instagram, the phone
                number or account you messaged from, and roughly which business you contacted.
              </li>
            </ul>
            <p>
              We will confirm receipt, give you a reference so you can check progress, and complete
              the deletion within 30 days. Live records go immediately; backup copies are overwritten
              on their normal 30-day cycle.
            </p>
            <p>
              If you connected a Facebook Page or Instagram account to Rivon, you can also remove
              Rivon&apos;s access at any time from your Meta Business Settings, under connected
              business integrations. Doing so stops us acting on that account immediately. It does
              not by itself delete data already stored, so send the email as well if that is what you
              want.
            </p>
          </Section>

          <Section id="cookies" title="14. Cookies">
            <p>
              Rivon uses two cookies, and only two. Both are strictly necessary to keep you signed
              in, so no consent banner is required and there is nothing to opt out of.
            </p>
            <Table
              head={["Cookie", "What it does", "How long"]}
              rows={[
                [
                  <code key="a" className="font-mono text-xs">rivon_access</code>,
                  <>Keeps you signed in between page loads</>,
                  <>Minutes</>,
                ],
                [
                  <code key="b" className="font-mono text-xs">rivon_refresh</code>,
                  <>Lets your session renew without signing in again</>,
                  <>Until you sign out</>,
                ],
              ]}
            />
            <p>
              No analytics, no advertising pixels, no third-party trackers, no cross-site profiling.
              Signing out clears both cookies.
            </p>
          </Section>

          <Section id="children" title="15. Children">
            <p>
              Rivon is a tool for businesses and is not directed at children. We do not knowingly
              collect data from anyone under 16. If you believe a child&apos;s data has reached us,
              tell us at {mail} and we will delete it.
            </p>
          </Section>

          <Section id="changes" title="16. Changes to this notice">
            <p>
              We update this notice when the service changes. The date at the top always reflects the
              current version. If a change materially affects how we handle your data, we will tell
              account holders by email before it takes effect rather than relying on you to check
              this page.
            </p>
          </Section>

          <Section id="contact" title="17. Contact us">
            <p>
              For anything in this notice — a question, a request about your data, or a complaint —
              email {mail}. We read everything that arrives there.
            </p>
            <p>
              We have not appointed a data protection officer, as we are not required to. Requests go
              to the same address and are handled by the founding team.
            </p>
          </Section>
        </div>

        <p className="mt-16 border-t pt-6 text-sm text-muted-foreground">
          This notice was last updated on {LAST_UPDATED}.
        </p>
      </main>

      <SiteFooter />
    </>
  )
}
