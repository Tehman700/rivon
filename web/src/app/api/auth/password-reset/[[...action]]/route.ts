import { apiBaseUrl } from "@/lib/session"

// POST /api/auth/password-reset          -> request a reset email
// POST /api/auth/password-reset/confirm  -> set a new password with the emailed token
export async function POST(
  request: Request,
  { params }: { params: Promise<{ action?: string[] }> },
) {
  const { action } = await params
  const suffix = action?.join("/") ?? ""
  if (suffix !== "" && suffix !== "confirm") {
    return Response.json({ detail: "Not found" }, { status: 404 })
  }
  const upstream = await fetch(`${apiBaseUrl()}/auth/password-reset${suffix ? "/confirm" : ""}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: await request.text(),
    cache: "no-store",
  })
  return new Response(upstream.status === 204 || upstream.status === 202 ? null : upstream.body, {
    status: upstream.status,
    headers: { "content-type": "application/json" },
  })
}
