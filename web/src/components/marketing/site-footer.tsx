import Link from "next/link"

import { RivonLogo } from "@/components/brand/logo"
import { CONTACT_EMAIL } from "@/lib/contact"

export function SiteFooter() {
  return (
    <footer className="border-t bg-muted/30">
      <div className="mx-auto grid w-full max-w-6xl gap-8 px-4 py-12 sm:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-3">
          <RivonLogo />
          <p className="max-w-xs text-sm text-muted-foreground">
            Lead qualification, feasibility and quotation for service businesses. Hosted in the EU.
          </p>
        </div>
        <div className="space-y-2 text-sm">
          <p className="font-medium">Product</p>
          <a href="#how" className="block text-muted-foreground hover:text-foreground">How it works</a>
          <a href="#difference" className="block text-muted-foreground hover:text-foreground">Why Rivon</a>
          <a href="#europe" className="block text-muted-foreground hover:text-foreground">Built for the EU</a>
        </div>
        <div className="space-y-2 text-sm">
          <p className="font-medium">Account</p>
          <Link href="/login" className="block text-muted-foreground hover:text-foreground">Sign in</Link>
          <Link href="/request-access" className="block text-muted-foreground hover:text-foreground">Request access</Link>
        </div>
        <div className="space-y-2 text-sm">
          <p className="font-medium">Contact</p>
          <a href={`mailto:${CONTACT_EMAIL}`} className="block break-all text-muted-foreground hover:text-foreground">
            {CONTACT_EMAIL}
          </a>
          <p className="text-muted-foreground">Privacy notice and terms are in preparation.</p>
        </div>
      </div>
      <div className="border-t">
        <p className="mx-auto w-full max-w-6xl px-4 py-6 text-xs text-muted-foreground">
          © {new Date().getFullYear()} Rivon. Your customers are always told when they are talking to an assistant.
        </p>
      </div>
    </footer>
  )
}
