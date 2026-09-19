import Link from "next/link"

import { RivonLogo } from "@/components/brand/logo"

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="flex flex-col px-4 py-8 sm:px-8">
        <Link href="/login" className="w-fit">
          <RivonLogo />
        </Link>
        <main className="flex flex-1 items-center justify-center py-12">
          <div className="w-full max-w-sm">{children}</div>
        </main>
        <p className="text-xs text-muted-foreground">
          Hosted in the EU · Your customers always know they&apos;re talking to an assistant.
        </p>
      </div>
      <aside className="relative hidden overflow-hidden bg-primary lg:flex lg:flex-col lg:justify-end lg:p-12">
        <FlowLines />
        <div className="relative max-w-md space-y-4 text-primary-foreground">
          <p className="text-3xl tracking-tight">
            From first message to a priced, feasible quote, approved from your phone.
          </p>
          <ul className="space-y-2 text-sm text-primary-foreground/70">
            <li>Qualifies every inquiry by conversation</li>
            <li>Checks it against your real capacity before quoting</li>
            <li>Prices it from your own rate card, never guessed</li>
          </ul>
        </div>
      </aside>
    </div>
  )
}

/** Decorative lines echoing the logo's spokes. */
function FlowLines() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 400 400"
      preserveAspectRatio="none"
      className="absolute inset-0 size-full opacity-40"
    >
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <path
          key={i}
          d={`M-20 ${90 + i * 38} C 100 ${40 + i * 38}, 180 ${180 + i * 30}, 420 ${110 + i * 40}`}
          fill="none"
          stroke={i === 2 ? "var(--brand)" : "oklch(1 0 0 / 0.12)"}
          strokeWidth={i === 2 ? 2 : 1}
        />
      ))}
    </svg>
  )
}
