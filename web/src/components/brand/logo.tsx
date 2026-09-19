import { cn } from "@/lib/utils"

/*
 * The Rivon mark, traced from design-files/"Rivon Logo with Integrated Spark
 * Element.png": a hub with spokes out to connected nodes, plus a few short
 * "spark" stubs.
 *
 * Blue nodes and links use the brand blue. The neutral nodes use
 * currentColor, so the mark reads correctly on light and dark surfaces:
 * white on the dark panel, near-black on white. Keep this in sync with
 * src/app/icon.svg, public/rivon-mark.svg and public/rivon-logo.svg.
 */

const BLUE = "oklch(0.749 0.129 241.6)"

const BLUE_NODES = [
  { cx: 51.62, cy: 54.26, r: 5.52 },
  { cx: 51.83, cy: 10.32, r: 5.19 },
  { cx: 35.6, cy: 34.72, r: 4.98 }, // hub
]
const NEUTRAL_NODES = [
  { cx: 25.66, cy: 24.53, r: 4.82 },
  { cx: 20.84, cy: 44.09, r: 3.68 },
  { cx: 58.48, cy: 31.57, r: 3.52 },
  { cx: 28.14, cy: 57.9, r: 3.43 },
  { cx: 5.38, cy: 36.67, r: 3.38 },
  { cx: 28.26, cy: 6.03, r: 3.36 },
]
const GREY_NODE = { cx: 10.41, cy: 14.42, r: 3.01 }

const BLUE_LINKS = [
  [35.6, 34.72, 51.83, 10.32],
  [35.6, 34.72, 51.62, 54.26],
  [35.6, 34.72, 20.84, 44.09],
  [25.66, 24.53, 5.38, 36.67],
] as const
const GREY_LINKS = [
  [35.6, 34.72, 58.48, 31.57],
  [25.66, 24.53, 10.41, 14.42],
] as const
/** Spokes that stop short of the hub, which is what gives the mark its spark. */
const STUBS = [
  [28.26, 6.03, 35.6, 34.72, 0.45],
  [28.14, 57.9, 35.6, 34.72, 0.55],
  [25.66, 24.53, 35.6, 34.72, 0.55],
] as const

function stub([x1, y1, x2, y2, fraction]: (typeof STUBS)[number]) {
  return { x1, y1, x2: x1 + (x2 - x1) * fraction, y2: y1 + (y2 - y1) * fraction }
}

export function RivonMark({ className, title = "Rivon" }: { className?: string; title?: string }) {
  return (
    <svg
      viewBox="0 0 64 64"
      role={title ? "img" : "presentation"}
      aria-label={title || undefined}
      aria-hidden={title ? undefined : true}
      className={cn("size-8 shrink-0", className)}
      strokeWidth={2.55}
      strokeLinecap="round"
    >
      <g stroke="currentColor" opacity={0.55}>
        {GREY_LINKS.map(([x1, y1, x2, y2]) => (
          <line key={`g${x1}${y1}${x2}`} x1={x1} y1={y1} x2={x2} y2={y2} />
        ))}
        {STUBS.map((s) => (
          <line key={`s${s[0]}${s[1]}`} {...stub(s)} />
        ))}
      </g>
      <g stroke={BLUE}>
        {BLUE_LINKS.map(([x1, y1, x2, y2]) => (
          <line key={`b${x1}${y1}${x2}`} x1={x1} y1={y1} x2={x2} y2={y2} />
        ))}
      </g>
      <g fill="currentColor">
        {NEUTRAL_NODES.map((n) => (
          <circle key={`n${n.cx}${n.cy}`} {...n} />
        ))}
        <circle {...GREY_NODE} opacity={0.55} />
      </g>
      <g fill={BLUE}>
        {BLUE_NODES.map((n) => (
          <circle key={`bn${n.cx}${n.cy}`} {...n} />
        ))}
      </g>
    </svg>
  )
}

/** Mark plus wordmark. The wordmark is light-weight text, as in the source logo. */
export function RivonLogo({
  className,
  markClassName,
  wordClassName,
}: {
  className?: string
  markClassName?: string
  wordClassName?: string
}) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <RivonMark className={markClassName} title="" />
      <span className={cn("text-xl font-light tracking-tight", wordClassName)}>Rivon</span>
      <span className="sr-only">Rivon</span>
    </span>
  )
}
