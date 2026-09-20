"use client"

import { useEffect, useRef, type ReactNode } from "react"
import gsap from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"

import { cn } from "@/lib/utils"

gsap.registerPlugin(ScrollTrigger)

if (typeof document !== "undefined") {
  // Fonts change text height, which moves every trigger point. Recalculate
  // once they're ready so a section can't stay stuck invisible.
  document.fonts?.ready.then(() => ScrollTrigger.refresh())
}

/**
 * Animations are an enhancement, never a requirement: everything is readable
 * with JavaScript off, and gsap.matchMedia skips them entirely for people who
 * ask for reduced motion.
 */
function animate(build: (mm: gsap.MatchMedia) => void, scope: Element) {
  const ctx = gsap.context(() => {
    const mm = gsap.matchMedia()
    build(mm)
  }, scope)
  return () => ctx.revert()
}

/** Fades a block up as it scrolls into view. */
export function Reveal({
  children,
  className,
  delay = 0,
  as: Tag = "div",
}: {
  children: ReactNode
  className?: string
  delay?: number
  as?: "div" | "section" | "li"
}) {
  const ref = useRef<HTMLElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    return animate((mm) => {
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.from(el, {
          opacity: 0,
          y: 24,
          duration: 0.7,
          delay,
          ease: "power2.out",
          scrollTrigger: { trigger: el, start: "top 85%", once: true },
        })
      })
    }, el)
  }, [delay])

  // @ts-expect-error: one of three known tags, all accepting a ref
  return <Tag ref={ref} className={className}>{children}</Tag>
}

/** Staggers direct children of the hero in on first paint. */
export function HeroStage({ children, className }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    return animate((mm) => {
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.from(el.querySelectorAll("[data-stage]"), {
          opacity: 0,
          y: 18,
          duration: 0.8,
          ease: "power3.out",
          stagger: 0.09,
        })
      })
    }, el)
  }, [])

  return (
    <div ref={ref} className={className}>
      {children}
    </div>
  )
}

/** Counts a number up when it scrolls into view. */
export function CountUp({ to, suffix = "" }: { to: number; suffix?: string }) {
  const ref = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    return animate((mm) => {
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const value = { n: 0 }
        gsap.to(value, {
          n: to,
          duration: 1.2,
          ease: "power2.out",
          scrollTrigger: { trigger: el, start: "top 90%", once: true },
          onUpdate: () => {
            el.textContent = `${Math.round(value.n)}${suffix}`
          },
        })
      })
    }, el)
  }, [to, suffix])

  return (
    <span ref={ref}>
      {to}
      {suffix}
    </span>
  )
}

const STEPS = [
  { label: "Message", detail: "A customer asks for a quote" },
  { label: "Qualify", detail: "The assistant gathers requirements" },
  { label: "Check", detail: "Area, stock, crew and job size" },
  { label: "Price", detail: "From your rate card, by fixed rules" },
  { label: "Approve", detail: "You decide, on your phone" },
]

/** The pipeline, drawn then lit up step by step. */
export function PipelineDiagram({ className }: { className?: string }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    return animate((mm) => {
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const line = el.querySelector<SVGPathElement>("[data-line]")
        const timeline = gsap.timeline({
          scrollTrigger: { trigger: el, start: "top 80%", once: true },
        })
        if (line) {
          const length = line.getTotalLength()
          gsap.set(line, { strokeDasharray: length, strokeDashoffset: length })
          timeline.to(line, { strokeDashoffset: 0, duration: 1.1, ease: "power2.inOut" })
        }
        timeline.from(
          el.querySelectorAll("[data-step]"),
          { opacity: 0, scale: 0.9, duration: 0.45, stagger: 0.12, ease: "back.out(1.6)" },
          "-=0.8",
        )
      })
    }, el)
  }, [])

  return (
    <div ref={ref} className={cn("relative", className)}>
      <svg
        aria-hidden
        viewBox="0 0 1000 60"
        preserveAspectRatio="none"
        className="absolute inset-x-0 top-5 hidden h-10 w-full md:block"
      >
        <path
          data-line
          d="M40 30 H960"
          fill="none"
          stroke="var(--brand)"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
      <ol className="relative grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-5 md:gap-2">
        {STEPS.map((step, index) => (
          <li key={step.label} data-step className="flex gap-3 md:flex-col md:items-center md:text-center">
            <span className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-full border bg-background text-sm font-medium md:mt-0">
              {index + 1}
            </span>
            <span>
              <span className="block font-medium">{step.label}</span>
              <span className="block text-sm text-muted-foreground">{step.detail}</span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}
