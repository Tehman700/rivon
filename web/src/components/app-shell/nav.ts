import {
  Building2,
  FileText,
  LayoutDashboard,
  MessagesSquare,
  Percent,
  Users,
  Wrench,
  type LucideIcon,
} from "lucide-react"

export interface NavItem {
  href: string
  label: string
  icon: LucideIcon
  /** Built later in the roadmap: shown, but not clickable. */
  soon?: boolean
}

export const NAV_SECTIONS: { title: string; items: NavItem[] }[] = [
  {
    title: "Workspace",
    items: [
      { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
      { href: "/leads", label: "Leads", icon: Users, soon: true },
      { href: "/conversations", label: "Conversations", icon: MessagesSquare, soon: true },
      { href: "/quotations", label: "Quotations", icon: FileText, soon: true },
    ],
  },
  {
    title: "Setup",
    items: [
      { href: "/services", label: "Services & rate cards", icon: Wrench },
      { href: "/settings/pricing", label: "Pricing", icon: Percent },
      { href: "/settings/business", label: "Business profile", icon: Building2 },
    ],
  },
]
