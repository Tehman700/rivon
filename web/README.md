# Rivon web

The owner dashboard: Next.js (App Router), Tailwind v4 and shadcn/ui on Radix,
following the design system in `design-files/DESIGN-STRUCTURE.md` (local only).

```sh
cp .env.example .env.local     # RIVON_API_URL=http://localhost:8000
npm install
npm run dev                    # http://localhost:3000, with the API running (docker compose up)
```

## How it talks to the API

The browser never holds a token. `/api/auth/login` stores the access and refresh
tokens in **httpOnly, SameSite=Lax cookies**. Browser calls go to
`/api/backend/*` (`src/app/api/backend/[...path]/route.ts`), which adds the token
and forwards to FastAPI. That proxy only allows `auth/me` and `business/*`,
refuses cross-origin requests, and only accepts JSON bodies.

`src/proxy.ts` (Next 16's replacement for middleware) guards every page and
silently refreshes an expired access token using the refresh cookie. The API's
30-second rotation grace window makes parallel refreshes safe.

Server components read data with `apiGet()` (`src/lib/api/server.ts`); forms
write with `api()` (`src/lib/api/client.ts`) and then `router.refresh()`.
Prices are never calculated here, only shown: pricing is deterministic Python.

## Brand

The mark is traced from `design-files/Rivon Logo with Integrated Spark
Element.png`: a hub with spokes out to connected nodes, plus a few short
"spark" stubs. Blue nodes and links use the brand blue (`#59b7f8`, the
`--brand` token); neutral nodes use `currentColor` so the mark reads on light
and dark surfaces. The wordmark is light-weight text.

Keep these in sync: `src/components/brand/logo.tsx`, `src/app/icon.svg`,
`public/rivon-mark.svg`, `public/rivon-logo.svg`.

## Deploying

`vercel.json` pins functions to `fra1` (Frankfurt) so request handling stays in
the EU. Set `RIVON_API_URL` in the Vercel project to the deployed API's HTTPS URL.
