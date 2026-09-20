import {
  Boxes,
  Building2,
  FileText,
  HardHat,
  LayoutDashboard,
  MapPin,
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
      { href: "/service-areas", label: "Service areas", icon: MapPin },
      { href: "/inventory", label: "Inventory", icon: Boxes },
      { href: "/crews", label: "Crews", icon: HardHat },
      { href: "/settings/business", label: "Business profile", icon: Building2 },
    ],
  },
]
