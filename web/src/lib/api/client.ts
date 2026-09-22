// Browser-side calls. They go to this app's /api/backend/* route, which adds
// the httpOnly session and forwards to FastAPI; the browser never sees a token.

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    /** Field name -> message, from FastAPI 422 validation errors. */
    public fields: Record<string, string> = {},
  ) {
    super(message)
  }
}

interface ValidationIssue {
  loc: (string | number)[]
  msg: string
}

function humanise(msg: string): string {
  return msg.replace(/^Value error, /, "")
}

async function toError(response: Response): Promise<ApiError> {
  let detail: unknown = null
  try {
    detail = ((await response.json()) as { detail?: unknown }).detail
  } catch {
    // not JSON
  }
  if (response.status === 422 && Array.isArray(detail)) {
    const fields: Record<string, string> = {}
    const general: string[] = []
    for (const issue of detail as ValidationIssue[]) {
      const path = issue.loc.filter((part) => part !== "body")
      const field = path.length ? String(path[0]) : ""
      const message = humanise(issue.msg)
      if (field && !fields[field]) fields[field] = message
      else if (!field) general.push(message)
    }
    const first = general[0] ?? Object.values(fields)[0] ?? "Some fields need attention"
    return new ApiError(422, first, fields)
  }
  const message = typeof detail === "string" ? detail : `Something went wrong (${response.status})`
  return new ApiError(response.status, message)
}

export async function api<T = unknown>(
  path: string,
  init: { method?: string; body?: unknown } = {},
): Promise<T> {
  const method = init.method ?? "GET"
  // The proxy refuses anything that could carry a body unless it says JSON —
  // that is what stops a cross-site form posting here, since a form can never
  // send this content type. A POST with no body still has to declare it, or it
  // is turned away as though it were one. Keep this list in step with the one
  // in app/api/backend/[...path]/route.ts.
  const mayHaveBody = !["GET", "HEAD", "DELETE"].includes(method)
  const response = await fetch(`/api/backend${path}`, {
    method,
    headers: mayHaveBody ? { "content-type": "application/json" } : {},
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  })
  if (response.status === 401) {
    // Full reload on purpose: the session is gone, so drop all client state.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`
    throw new ApiError(401, "Your session has ended. Please sign in again.")
  }
  if (!response.ok) throw await toError(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/** For the auth routes, which are not behind the session. */
export async function postAuth(path: string, body: unknown): Promise<void> {
  const response = await fetch(`/api/auth${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!response.ok) throw await toError(response)
}
