import { NextResponse, type NextRequest } from "next/server"

import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  clearSessionCookies,
  refreshTokens,
  setSessionCookies,
} from "@/lib/session"

// Pages reachable without a session.
const PUBLIC_PAGES = new Set(["/login", "/forgot-password", "/reset-password"])

/**
 * Gatekeeper for every page and /api/backend call:
 * - a valid access cookie: carry on;
 * - only a refresh cookie: refresh now, so server components render with a
 *   fresh token (the API's grace window makes parallel refreshes safe);
 * - neither: pages go to /login, API calls get 401.
 * Server components and route handlers still check the token themselves.
 */
export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl
  const isPublicPage = PUBLIC_PAGES.has(pathname)

  if (request.cookies.has(ACCESS_COOKIE)) return NextResponse.next()

  const refresh = request.cookies.get(REFRESH_COOKIE)?.value
  if (refresh) {
    const tokens = await refreshTokens(refresh)
    if (tokens) {
      // Make the new access token visible to this same request's renderers...
      request.cookies.set(ACCESS_COOKIE, tokens.access_token)
      const response = NextResponse.next({ request: { headers: request.headers } })
      // ...and store both for the browser's next requests.
      setSessionCookies(response, tokens)
      return response
    }
  }

  if (isPublicPage) return NextResponse.next()

  const response = pathname.startsWith("/api/")
    ? NextResponse.json({ detail: "Authentication required" }, { status: 401 })
    : NextResponse.redirect(
        new URL(`/login?next=${encodeURIComponent(pathname)}`, request.url),
      )
  if (refresh) clearSessionCookies(response) // the refresh token is dead
  return response
}

export const config = {
  matcher: [
    // Everything except auth endpoints, Next internals and static files.
    "/((?!api/auth|_next/static|_next/image|icon.svg|favicon.ico|rivon-.*\\.svg).*)",
  ],
}
