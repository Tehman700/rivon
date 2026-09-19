import { cookies } from "next/headers"
import type { NextRequest } from "next/server"

import { ACCESS_COOKIE, apiBaseUrl } from "@/lib/session"

// Only these API areas are reachable from the browser through this proxy.
const ALLOWED = /^(auth\/me|business(\/[A-Za-z0-9_\-/]*)?)$/

async function forward(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params
  const target = path.join("/")
  if (!ALLOWED.test(target)) {
    return Response.json({ detail: "Not found" }, { status: 404 })
  }

  // Cookie-authenticated, so guard against cross-site requests: the browser
  // must be on this origin, and bodies must be JSON (which forms can't send).
  const origin = request.headers.get("origin")
  if (origin && origin !== request.nextUrl.origin) {
    return Response.json({ detail: "Cross-origin request refused" }, { status: 403 })
  }
  const hasBody = !["GET", "HEAD", "DELETE"].includes(request.method)
  if (hasBody && !request.headers.get("content-type")?.startsWith("application/json")) {
    return Response.json({ detail: "Expected JSON" }, { status: 415 })
  }

  const token = (await cookies()).get(ACCESS_COOKIE)?.value
  if (!token) return Response.json({ detail: "Authentication required" }, { status: 401 })

  const upstream = await fetch(`${apiBaseUrl()}/${target}${request.nextUrl.search}`, {
    method: request.method,
    headers: {
      authorization: `Bearer ${token}`,
      ...(hasBody ? { "content-type": "application/json" } : {}),
    },
    body: hasBody ? await request.text() : undefined,
    cache: "no-store",
  })
  return new Response(upstream.status === 204 ? null : upstream.body, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  })
}

export { forward as GET, forward as POST, forward as PUT, forward as PATCH, forward as DELETE }
