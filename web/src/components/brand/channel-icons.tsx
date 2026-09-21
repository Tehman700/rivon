/*
 * Channel glyphs for the Connect cards.
 *
 * Drawn here rather than imported: lucide dropped its brand icons, and these
 * are the marks customers actually recognise on a "connect your account"
 * screen. Simplified silhouettes, used only to identify each platform.
 *
 * They inherit `currentColor`, so the card sets the colour once on the tile.
 */

type IconProps = { className?: string }

export function MessengerIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden className={className}>
      <path d="M12 2C6.24 2 2 6.22 2 11.2c0 2.84 1.4 5.35 3.6 7v3.3l3.3-1.82c.98.27 2.02.42 3.1.42 5.76 0 10-4.22 10-9.2S17.76 2 12 2Z" />
      <path
        d="m6.6 13.9 4.05-4.3 2.1 2.2 3.65-2.2-4.05 4.3-2.1-2.2-3.65 2.2Z"
        fill="#fff"
      />
    </svg>
  )
}

export function InstagramIcon({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={className}
    >
      <rect x="2.5" y="2.5" width="19" height="19" rx="5.5" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="17.4" cy="6.6" r="1.1" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function WhatsAppIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden className={className}>
      <path d="M12.04 2c-5.46 0-9.9 4.43-9.9 9.88 0 1.74.46 3.44 1.33 4.94L2 22l5.32-1.39a9.9 9.9 0 0 0 4.72 1.2h.01c5.45 0 9.89-4.43 9.89-9.88 0-2.64-1.03-5.12-2.9-6.99A9.82 9.82 0 0 0 12.04 2Zm0 18.05h-.01a8.2 8.2 0 0 1-4.18-1.14l-.3-.18-3.1.81.83-3.02-.2-.31a8.17 8.17 0 0 1-1.26-4.36c0-4.53 3.7-8.22 8.23-8.22a8.2 8.2 0 0 1 8.21 8.23c0 4.53-3.69 8.19-8.22 8.19Z" />
      <path d="M9.4 7.6h-.6c-.2 0-.55.08-.84.4-.29.31-1.1 1.07-1.1 2.6s1.13 3.02 1.28 3.23c.16.2 2.18 3.48 5.38 4.74 2.66 1.05 3.2.84 3.78.79.58-.05 1.87-.76 2.13-1.5.26-.74.26-1.37.18-1.5-.08-.13-.29-.21-.6-.37-.31-.16-1.87-.92-2.16-1.03-.29-.1-.5-.16-.71.16-.21.31-.82 1.03-1 1.24-.19.21-.37.24-.68.08-.31-.16-1.33-.49-2.53-1.56-.94-.83-1.57-1.86-1.75-2.18-.19-.31-.02-.48.13-.64.14-.14.31-.37.47-.55.15-.19.2-.32.31-.53.1-.21.05-.4-.03-.55-.08-.16-.7-1.7-.96-2.33-.25-.61-.5-.53-.7-.54Z" />
    </svg>
  )
}
