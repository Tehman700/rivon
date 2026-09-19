// Session cookies. Both tokens are httpOnly: page scripts can never read them,
// so an XSS bug can't steal a session. Only server code (proxy.ts, route
// handlers, server components) touches them.

import type { NextResponse } from "next/server"

export const ACCESS_COOKIE = "rivon_access"
export const REFRESH_COOKIE = "rivon_refresh"

const REFRESH_MAX_AGE = 30 * 24 * 60 * 60 // matches the API's refresh token TTL
const EXPIRY_MARGIN = 60 // drop the access cookie a minute early so it's never sent expired

export interface TokenPair {
  access_token: string
  refresh_token: string
  expires_in: number
}

function base() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
  }
}

export function setSessionCookies(response: NextResponse, tokens: TokenPair) {
  response.cookies.set(ACCESS_COOKIE, tokens.access_token, {
    ...base(),
    maxAge: Math.max(tokens.expires_in - EXPIRY_MARGIN, 1),
  })
  response.cookies.set(REFRESH_COOKIE, tokens.refresh_token, { ...base(), maxAge: REFRESH_MAX_AGE })
}

export function clearSessionCookies(response: NextResponse) {
  response.cookies.set(ACCESS_COOKIE, "", { ...base(), maxAge: 0 })
  response.cookies.set(REFRESH_COOKIE, "", { ...base(), maxAge: 0 })
}

/** Where the FastAPI backend lives. Server-side only; never exposed to the browser. */
export function apiBaseUrl(): string {
  const url = process.env.RIVON_API_URL
  if (!url) throw new Error("RIVON_API_URL is not set")
  return url.replace(/\/$/, "")
}

export async function refreshTokens(refreshToken: string): Promise<TokenPair | null> {
  try {
    const response = await fetch(`${apiBaseUrl()}/auth/refresh`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: "no-store",
    })
    return response.ok ? ((await response.json()) as TokenPair) : null
  } catch {
    return null
  }
}
