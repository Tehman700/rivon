import "server-only"

import { cookies } from "next/headers"
import { redirect } from "next/navigation"
import { cache } from "react"

import type { BusinessProfile, Me } from "@/lib/api/types"

import { ACCESS_COOKIE, apiBaseUrl } from "@/lib/session"

/**
 * GET from the API inside a server component, as the signed-in user.
 * Returns null on 404 (e.g. a profile not set up yet); sends the user to
 * /login on 401. proxy.ts has already refreshed an expired access token.
 */
export async function apiGet<T>(path: string): Promise<T | null> {
  const token = (await cookies()).get(ACCESS_COOKIE)?.value
  if (!token) redirect("/login")

  const response = await fetch(`${apiBaseUrl()}${path}`, {
    headers: { authorization: `Bearer ${token}` },
    cache: "no-store",
  })
  if (response.status === 401) redirect("/login")
  if (response.status === 404) return null
  if (!response.ok) {
    throw new Error(`API ${path} failed: ${response.status}`)
  }
  return (await response.json()) as T
}


/** The signed-in user; fetched once per request however many components ask. */
export const getMe = cache(async (): Promise<Me> => {
  const me = await apiGet<Me>("/auth/me")
  if (!me) redirect("/login")
  return me
})

export const getProfile = cache(() => apiGet<BusinessProfile>("/business/profile"))
