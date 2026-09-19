import { NextResponse } from "next/server"

import { apiBaseUrl, setSessionCookies, type TokenPair } from "@/lib/session"

export async function POST(request: Request) {
  const body = await request.text()
  const upstream = await fetch(`${apiBaseUrl()}/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
    cache: "no-store",
  })
  if (!upstream.ok) {
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: { "content-type": "application/json" },
    })
  }
  const tokens = (await upstream.json()) as TokenPair
  const response = NextResponse.json({ ok: true })
  setSessionCookies(response, tokens)
  return response
}
