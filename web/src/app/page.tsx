import type { Metadata } from "next"
import Link from "next/link"
import {
  ArrowRight,
  Calculator,
  CheckCircle2,
  FileText,
  MessageSquare,
  ShieldCheck,
  Sparkles,
  Sun,
} from "lucide-react"

import { RivonMark } from "@/components/brand/logo"
import { CountUp, HeroStage, PipelineDiagram, Reveal } from "@/components/marketing/motion"
import { SiteFooter } from "@/components/marketing/site-footer"
import { SiteHeader } from "@/components/marketing/site-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export const metadata: Metadata = {
  title: "Rivon — quote service jobs without the back and forth",
  description:
    "Rivon qualifies inbound enquiries by conversation, checks each job against your real capacity, and prices it from your own rate card. You approve from your phone.",
  robots: { index: true, follow: true },
  openGraph: {
    title: "Rivon — quote service jobs without the back and forth",
    description:
      "Qualify enquiries, check feasibility against real capacity, and quote from your own rate card. Hosted in the EU.",
    type: "website",
  },
}

export default function LandingPage() {
  return (
    <>
      <SiteHeader />
      <main>
        <Hero />
        <HowItWorks />
        <Difference />
        <NotJustAChatbot />
        <Europe />
        <Verticals />
        <Faq />
        <ClosingCta />
      </main>
      <SiteFooter />
    </>
  )
}

function Hero() {
  return (
    <section className="relative overflow-hidden border-b">
      <Constellation />
      <div className="relative mx-auto w-full max-w-6xl px-4 py-20 md:py-28">
        <HeroStage className="max-w-3xl">
          <Badge data-stage variant="outline" className="mb-6 gap-2 py-1 font-normal">
            <Sun className="size-3.5" /> Solar installers first · HVAC and plumbing next
          </Badge>
          <h1 data-stage className="text-4xl tracking-tight sm:text-5xl lg:text-6xl">
            Every enquiry answered, checked and priced
            <span className="block text-muted-foreground">before you pick up the phone.</span>
          </h1>
          <p data-stage className="mt-6 max-w-2xl text-lg text-muted-foreground">
            Rivon talks to the customer, works out what the job needs, checks it against the stock
            and crews you actually have, and prices it from your own rate card. Nothing reaches the
            customer until you approve it.
          </p>
          <div data-stage className="mt-8 flex flex-wrap gap-3">
            <Button asChild size="lg">
              <Link href="/request-access">
                Request access <ArrowRight />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link href="/login">Sign in</Link>
            </Button>
          </div>
          <p data-stage className="mt-4 text-sm text-muted-foreground">
            Invitation only while we work with our first installers.
          </p>
        </HeroStage>

        <div className="mt-16">
          <PipelineDiagram />
        </div>
      </div>
    </section>
  )
}

/** Quiet background echo of the logo's node graph. */
function Constellation() {
  return (
    <svg aria-hidden viewBox="0 0 800 400" className="absolute -top-10 right-0 hidden h-[420px] w-[800px] opacity-[0.07] md:block">
      <g stroke="currentColor" strokeWidth="1.5">
        <line x1="520" y1="120" x2="640" y2="60" />
        <line x1="520" y1="120" x2="660" y2="210" />
        <line x1="520" y1="120" x2="400" y2="180" />
        <line x1="400" y1="180" x2="300" y2="110" />
      </g>
      <g fill="currentColor">
        <circle cx="520" cy="120" r="10" />
        <circle cx="640" cy="60" r="14" />
        <circle cx="660" cy="210" r="14" />
        <circle cx="400" cy="180" r="8" />
        <circle cx="300" cy="110" r="6" />
      </g>
    </svg>
  )
}

function Section({
  id,
  eyebrow,
  title,
  lead,
  children,
  muted = false,
}: {
  id?: string
  eyebrow?: string
  title: string
  lead?: string
  children?: React.ReactNode
  muted?: boolean
}) {
  return (
    <section id={id} className={muted ? "border-b bg-muted/30" : "border-b"}>
      <div className="mx-auto w-full max-w-6xl px-4 py-16 md:py-24">
        <Reveal className="max-w-2xl">
          {eyebrow && <p className="mb-2 text-sm text-muted-foreground">{eyebrow}</p>}
          <h2 className="text-3xl tracking-tight sm:text-4xl">{title}</h2>
          {lead && <p className="mt-4 text-lg text-muted-foreground">{lead}</p>}
        </Reveal>
        {children}
      </div>
    </section>
  )
}

function HowItWorks() {
  const steps = [
    {
      icon: MessageSquare,
      title: "It asks what you would ask",
      text: "Roof type, consumption, timeline, address. Only the things still missing, in plain conversation, and it says up front that it is an assistant.",
    },
    {
      icon: ShieldCheck,
      title: "It checks before it promises",
      text: "Do you cover that area? Is the system size within your range? Are the panels in stock and a crew free? Every answer comes with its reason.",
    },
    {
      icon: Calculator,
      title: "It prices from your numbers",
      text: "Your rate card, your margin, your VAT. The arithmetic is fixed code, not a language model guessing a figure.",
    },
    {
      icon: FileText,
      title: "You approve, then it sends",
      text: "A card on your phone with the amount and the reasoning. Approve, edit or reject. Nothing goes out unapproved.",
    },
  ]
  return (
    <Section
      id="how"
      eyebrow="How it works"
      title="From first message to a quote you stand behind"
      lead="Set it up once with your services, prices, areas, stock and crews. After that it runs on every enquiry."
    >
      <Reveal className="mt-10 flex flex-wrap items-baseline gap-2 text-muted-foreground">
        <span className="text-3xl tracking-tight text-foreground">
          <CountUp to={30} suffix=" minutes" />
        </span>
        <span>to set up, once. Then it runs on every enquiry.</span>
      </Reveal>
      <div className="mt-8 grid gap-4 md:grid-cols-2">
        {steps.map((step, i) => (
          <Reveal key={step.title} delay={i * 0.05}>
            <Card className="h-full">
              <CardHeader>
                <step.icon className="mb-2 size-5 text-muted-foreground" />
                <CardTitle className="text-lg">{step.title}</CardTitle>
                <CardDescription className="text-base">{step.text}</CardDescription>
              </CardHeader>
            </Card>
          </Reveal>
        ))}
      </div>
    </Section>
  )
}

function Difference() {
  return (
    <Section
      id="difference"
      muted
      eyebrow="Why Rivon"
      title="A chatbot collects names. Rivon answers the question that matters."
      lead="Anyone can bolt a bot onto WhatsApp. The hard part is knowing whether a job is worth quoting, and what to charge for it."
    >
      <div className="mt-12 grid gap-4 md:grid-cols-3">
        {[
          {
            title: "Capacity, not guesswork",
            text: "A job outside your service area, too large for your crews, or short on stock is flagged with the reason before anyone is promised anything.",
          },
          {
            title: "Prices you can defend",
            text: "Every line traces back to a number you entered: cost, quantity, margin, VAT. You can explain any quote to a customer, line by line.",
          },
          {
            title: "Nothing sent behind your back",
            text: "Quotes wait for your approval. You see the score, the reasons and the full conversation before you decide.",
          },
        ].map((item, i) => (
          <Reveal key={item.title} delay={i * 0.05}>
            <Card className="h-full bg-background">
              <CardHeader>
                <CheckCircle2 className="mb-2 size-5 text-[oklch(0.55_0.13_150)]" />
                <CardTitle className="text-lg">{item.title}</CardTitle>
                <CardDescription className="text-base">{item.text}</CardDescription>
              </CardHeader>
            </Card>
          </Reveal>
        ))}
      </div>
    </Section>
  )
}

function NotJustAChatbot() {
  const rows = [
    { job: "Understanding the customer", how: "AI", ai: true },
    { job: "Writing the covering note", how: "AI", ai: true },
    { job: "Deciding if a job is feasible", how: "Fixed rules", ai: false },
    { job: "Calculating the price", how: "Fixed rules", ai: false },
    { job: "Applying margin and VAT", how: "Fixed rules", ai: false },
  ]
  return (
    <Section
      title="AI where it helps. Arithmetic where it counts."
      lead="Language models are good at conversation and bad at being exactly right. So the money is never left to one."
    >
      <div className="mt-10 grid gap-8 lg:grid-cols-[1fr_auto] lg:items-center">
        <Reveal>
          <ul className="divide-y rounded-xl border bg-background">
            {rows.map((row) => (
              <li key={row.job} className="flex items-center justify-between gap-4 px-5 py-4">
                <span className="text-sm">{row.job}</span>
                <Badge variant="outline" className={row.ai ? "" : "level-good"}>
                  {row.ai && <Sparkles className="size-3" />}
                  {row.how}
                </Badge>
              </li>
            ))}
          </ul>
        </Reveal>
        <Reveal delay={0.1} className="lg:w-64">
          <p className="text-4xl tracking-tight">
            0<span className="text-muted-foreground"> prices</span>
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            come from a language model. Every figure on a quote is computed from the rate card you
            entered, by code that is tested line by line.
          </p>
        </Reveal>
      </div>
    </Section>
  )
}

function Europe() {
  const points = [
    {
      title: "Your data stays in the EU",
      text: "Database, servers and request handling all run in Frankfurt. Each business is fixed to its region when the account is created.",
    },
    {
      title: "Customers know it's an assistant",
      text: "Every conversation opens by saying so, it cannot be switched off, and each disclosure is recorded.",
    },
    {
      title: "No automatic rejections",
      text: "If a job doesn't fit, that decision reaches you, not the customer. People can always ask for a human.",
    },
    {
      title: "Data requests are buttons, not promises",
      text: "Export or delete everything about one contact. Built in, not bolted on later.",
    },
  ]
  return (
    <Section
      id="europe"
      muted
      eyebrow="Built for the EU"
      title="Compliance designed in, not retrofitted"
      lead="The EU AI Act and GDPR shape how this works, not just what the terms page says."
    >
      <div className="mt-12 grid gap-4 sm:grid-cols-2">
        {points.map((point, i) => (
          <Reveal key={point.title} delay={i * 0.05}>
            <div className="flex h-full gap-3 rounded-xl border bg-background p-5">
              <ShieldCheck className="mt-0.5 size-5 shrink-0 text-muted-foreground" />
              <div>
                <p className="font-medium">{point.title}</p>
                <p className="mt-1 text-sm text-muted-foreground">{point.text}</p>
              </div>
            </div>
          </Reveal>
        ))}
      </div>
    </Section>
  )
}

function Verticals() {
  return (
    <Section
      title="Solar today, your trade next"
      lead="Rivon is configured per trade, not rebuilt. Solar installers come first so one trade works properly end to end."
    >
      <div className="mt-10 flex flex-wrap gap-3">
        {[
          { name: "Solar", live: true },
          { name: "HVAC", live: false },
          { name: "Plumbing", live: false },
          { name: "Construction", live: false },
        ].map((v, i) => (
          <Reveal key={v.name} delay={i * 0.04}>
            <span className="inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm">
              <RivonMark className="size-4" title="" />
              {v.name}
              <Badge variant="outline" className={v.live ? "level-good" : "font-normal"}>
                {v.live ? "Available" : "Next"}
              </Badge>
            </span>
          </Reveal>
        ))}
      </div>
    </Section>
  )
}

function Faq() {
  const faqs = [
    {
      q: "Does it message my customers without me?",
      a: "It answers questions and gathers requirements. Quotations only go out once you approve them.",
    },
    {
      q: "What if the price comes out wrong?",
      a: "Prices are computed from the rate card you entered, using fixed rules, and every quote shows its lines. If something is wrong, it is a number you can correct, not a black box.",
    },
    {
      q: "Do I have to change how I work?",
      a: "You spend about half an hour entering services, prices, areas, stock and crews. After that you review quotes on your phone.",
    },
    {
      q: "Where does my data live?",
      a: "In the EU. Database, servers and request handling run in Frankfurt.",
    },
    {
      q: "Can I try it?",
      a: "We are working with a small number of installers first. Request access and we will get in touch.",
    },
  ]
  return (
    <Section id="faq" muted title="Questions we get asked">
      <div className="mt-10 grid gap-4 md:grid-cols-2">
        {faqs.map((faq, i) => (
          <Reveal key={faq.q} delay={i * 0.04}>
            <div className="h-full rounded-xl border bg-background p-5">
              <p className="font-medium">{faq.q}</p>
              <p className="mt-2 text-sm text-muted-foreground">{faq.a}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </Section>
  )
}

function ClosingCta() {
  return (
    <section className="bg-primary text-primary-foreground">
      <div className="mx-auto w-full max-w-6xl px-4 py-20 text-center md:py-28">
        <Reveal>
          <h2 className="mx-auto max-w-3xl text-3xl tracking-tight sm:text-4xl">
            Stop quoting in the evenings.
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-primary-foreground/70">
            Set Rivon up once and let every enquiry arrive qualified, checked and priced, waiting
            for a yes or no.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Button asChild size="lg" variant="secondary">
              <Link href="/request-access">
                Request access <ArrowRight />
              </Link>
            </Button>
            <Button
              asChild
              size="lg"
              variant="outline"
              className="border-primary-foreground/30 bg-transparent text-primary-foreground hover:bg-primary-foreground/10 hover:text-primary-foreground"
            >
              <Link href="/login">Sign in</Link>
            </Button>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
