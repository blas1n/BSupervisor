# BSupervisor Frontend

Next.js 15 (App Router) + React 19 + Tailwind 4 dashboard for the BSupervisor
AI agent auditing and safety system.

## Stack

- **Framework**: Next.js 15 (App Router)
- **React**: 19
- **CSS**: Tailwind 4 (config-less, via `@tailwindcss/postcss`)
- **Tests (e2e)**: Playwright
- **Lint**: ESLint flat config + typescript-eslint
- **Package manager**: npm (`package-lock.json`)

## Scripts

```bash
npm install          # install deps
npm run dev          # start Next.js dev server (default port 3000)
npm run build        # production build
npm run start        # start production server (after build)
npm run lint         # eslint
npm run test:e2e     # Playwright e2e tests
```

## Environment

Copy `.env.example` to `.env.local` and adjust:

- `NEXT_PUBLIC_API_URL` — public API base URL inlined into the client bundle.
  Leave empty to use the relative `/api` path (proxied via `next.config.mjs`).
- `API_PROXY_TARGET` — server-only target for the `/api/*` rewrite during
  local dev (defaults to `http://localhost:8000`).

## Routes

| Path          | Component       | Auth     |
|---------------|-----------------|----------|
| `/login`      | `Login`         | Public   |
| `/`           | `Dashboard`     | Required |
| `/incidents`  | `Incidents`     | Required |
| `/rules`      | `RulesManager`  | Required |
| `/reports`    | `DailyReport`   | Required |
| `/costs`      | `CostMonitor`   | Required |
| `/settings`   | `Settings`      | Required |

Authenticated routes live under the `app/(protected)/` route group; the
group's `layout.tsx` handles the auth gate via `useAuth()` (cookie-based SSO
to `auth.bsvibe.dev`).
