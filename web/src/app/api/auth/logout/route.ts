import { cookies } from "next/headers"
import { NextResponse } from "next/server"

import { REFRESH_COOKIE, apiBaseUrl, clearSessionCookies } from "@/lib/session"

export async function POST() {
  const refresh = (await cookies()).get(REFRESH_COOKIE)?.value
  if (refresh) {
    // Revoke server-side too, so a copied refresh token is useless.
    await fetch(`${apiBaseUrl()}/auth/logout`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
      cache: "no-store",
    }).catch(() => undefined)
  }
  const response = NextResponse.json({ ok: true })
  clearSessionCookies(response)
  return response
}
