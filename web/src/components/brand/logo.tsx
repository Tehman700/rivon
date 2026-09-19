import { cn } from "@/lib/utils"

/*
 * The Rivon mark: an "R" whose leg runs out as a stream (Rivon, river): a lead
 * flowing through qualification into a quote. The amber stroke is the brand's
 * only accent colour. The same geometry is in src/app/icon.svg and
 * public/rivon-mark.svg; change all three together.
 */
export function RivonMark({ className, title = "Rivon" }: { className?: string; title?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      role="img"
      aria-label={title}
      className={cn("size-8 shrink-0", className)}
    >
      <rect width="32" height="32" rx="8" fill="oklch(0.107 0.045 280.7)" />
      <path
        d="M10.5 23V9.5h5.25a4.75 4.75 0 0 1 0 9.5H10.5"
        fill="none"
        stroke="#fff"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M15.5 19c2.2 0 2.6 4 5.6 4 1.3 0 2.2-.6 2.9-1.5"
        fill="none"
        stroke="oklch(0.782 0.158 72.3)"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function RivonLogo({ className, markClassName }: { className?: string; markClassName?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <RivonMark className={markClassName} title="" />
      <span className="text-lg font-medium tracking-tight text-foreground">rivon</span>
      <span className="sr-only">Rivon</span>
    </span>
  )
}
