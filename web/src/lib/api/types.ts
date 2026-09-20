// Mirrors the FastAPI schemas (rivon/platform/api.py, rivon/business/schemas.py).
// Decimals travel as strings so money is never rounded through a float.

export type UserRole = "owner" | "manager" | "agent"
export type Region = "eu" | "non_eu"

export interface Me {
  user_id: string
  tenant_id: string
  email: string
  role: UserRole
  region: Region
}

export interface OpeningPeriod {
  opens: string // "HH:MM"
  closes: string
}

export const WEEKDAYS = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
] as const
export type Weekday = (typeof WEEKDAYS)[number]
export type WeeklyHours = Record<Weekday, OpeningPeriod[]>

export type ProjectSizeUnit = "kWp"

export interface BusinessProfile {
  name: string
  assistant_name: string
  contact_email: string | null
  contact_phone: string | null
  website: string | null
  address_line: string | null
  city: string | null
  postal_code: string | null
  country: string | null
  timezone: string
  business_hours: WeeklyHours
  min_project_size: string | null
  max_project_size: string | null
  project_size_unit: ProjectSizeUnit | null
  min_project_value_eur: string | null
  max_project_value_eur: string | null
  updated_at: string
}

export type BusinessProfileInput = Omit<BusinessProfile, "updated_at">

export interface Service {
  id: string
  name: string
  description: string | null
  archived: boolean
  archived_at: string | null
  target_margin_percent: string | null
  vat_rate_percent: string | null
  created_at: string
  updated_at: string
}

export interface PricingSettings {
  default_target_margin_percent: string
  minimum_margin_percent: string
  default_vat_rate_percent: string
  updated_at: string
}

export type RuleCategory = "materials" | "labour" | "transport" | "fees"
export type QuantityBasis = "fixed" | "system_size_kwp" | "battery_capacity_kwh" | "distance_km"

export interface PricingRule {
  id: string
  service_id: string
  name: string
  category: RuleCategory
  quantity_basis: QuantityBasis
  quantity_factor: string
  unit_label: string
  unit_cost_eur: string
  included_quantity: string
  minimum_quantity: string
  round_up: boolean
  sort_order: number
  created_at: string
  updated_at: string
}

export type PricingRuleInput = Omit<PricingRule, "id" | "service_id" | "created_at" | "updated_at">

export const CATEGORY_LABELS: Record<RuleCategory, string> = {
  materials: "Materials",
  labour: "Labour",
  transport: "Transport",
  fees: "Fees",
}

export const BASIS_LABELS: Record<QuantityBasis, string> = {
  fixed: "Fixed",
  system_size_kwp: "System size (kWp)",
  battery_capacity_kwh: "Battery capacity (kWh)",
  distance_km: "Distance (km, one way)",
}

export interface ServiceArea {
  id: string
  name: string
  country: string
  postal_prefixes: string[]
  created_at: string
  updated_at: string
}

export interface InventoryItem {
  id: string
  name: string
  sku: string | null
  unit_label: string
  quantity: string
  low_stock_threshold: string | null
  low_stock: boolean
  created_at: string
  updated_at: string
}

export interface Crew {
  id: string
  name: string
  headcount: number
  weekly_capacity_hours: string
  active: boolean
  created_at: string
  updated_at: string
}

export interface VerticalField {
  name: string
  kind: "text" | "number" | "boolean" | "choice" | "multi_choice"
  label: string
  question: string
  unit: string | null
  choices: string[]
  required: boolean
}

export interface VerticalConfig {
  key: string
  label: string
  groups: { key: string; label: string; fields: VerticalField[] }[]
  required_any_of: string[][]
  settings: {
    vertical: string
    annual_kwh_per_kwp: string
    roof_area_m2_per_kwp: string
    max_followups: number
    updated_at: string
  }
}

export interface SizeEstimate {
  system_size_kwp: string | null
  basis: "stated" | "annual_consumption" | "roof_limited" | "unknown"
  explanation: string
  missing_for_quote: string[]
}
