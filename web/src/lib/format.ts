const euro = new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR" })
const number = new Intl.NumberFormat("en-IE", { maximumFractionDigits: 4 })

export function formatEuro(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—"
  return euro.format(Number(value))
}

export function formatNumber(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—"
  return number.format(Number(value))
}

export function formatPercent(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—"
  return `${number.format(Number(value))}%`
}

/** "" -> null, so optional fields are cleared rather than sent as empty strings. */
export function blankToNull(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === "" ? null : trimmed
}
