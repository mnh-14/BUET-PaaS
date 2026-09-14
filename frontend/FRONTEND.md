# BUET-PaaS Frontend — Reference

Detailed structure of the `frontend/` module (Next.js 14, App Router) and exactly how it talks to the FastAPI [backend](../backend/BACKEND.md). Generated from the current codebase for use as security-testing / tooling context.

## 1. Key fact: there is no custom Next.js API layer

There are **no** `app/api/**/route.ts` handlers and **no server actions** in this codebase. Every page is a client component (`"use client"` at the top of every file under `app/` and `components/`). "The Next.js backend" the app relies on is entirely the **built-in rewrite proxy** configured in `next.config.js` — Next.js's own Node server rewrites requests, it doesn't run any bespoke server code of ours.

```
frontend/
├── next.config.js       # Rewrite rule: /api/v1/:path* → ${BACKEND_URL}/api/v1/:path*
├── lib/api.ts            # Single typed fetch client used by every page/component (relative URLs only)
├── context/AuthContext.tsx  # Client-side session state, wraps lib/api's getSession/logoutUser
├── app/
│   ├── layout.tsx        # Root layout, wraps everything in <AuthProvider>
│   ├── page.tsx           # Login/register landing page (AuthForm)
│   ├── dashboard/page.tsx # Lists the user's projects
│   ├── projects/new/page.tsx     # GitHub App repo/branch picker + create project
│   └── projects/[id]/page.tsx    # Project detail, deployments, SSE status, env vars
├── components/            # Presentational + a few stateful components (StatusBadge, DeploymentHistory, SecurityScanPanel, DeploymentFailurePanel, Navbar, ProjectCard, AuthForm)
└── Dockerfile              # standalone Next.js build, BACKEND_URL passed as build ARG + runtime ENV
```

## 2. Request flow (browser → Next.js → FastAPI)

```
Browser (fetch/EventSource, same-origin, credentials included)
   │  e.g. GET /api/v1/projects
   ▼
Next.js server (the container/process serving the frontend, port 3000)
   │  next.config.js `rewrites()` matches "/api/v1/:path*"
   │  rewrites to `${BACKEND_URL}/api/v1/:path*` — a transparent server-side proxy,
   │  browser never sees or connects to the FastAPI host directly
   ▼
FastAPI backend (BACKEND_URL, default http://localhost:8000)
```

- **`lib/api.ts`** hardcodes `BASE_URL = ""`, so every call in the app is a **relative** URL (`/api/v1/...`). This is deliberate: it keeps all traffic same-origin from the browser's point of view, which is what makes the HttpOnly `buetpaas_session` cookie (set by FastAPI) work without any CORS configuration, and is why the backend's `enforce_same_origin` check (`Origin` must equal `FRONTEND_URL`) is meaningful — the browser's `Origin` on these requests is the Next.js origin, not the FastAPI one.
- **`apiFetch`** (`lib/api.ts:106`) always sets `credentials: "include"` so the session cookie is forwarded on every request, including cross-container hops.
- **SSE**: `subscribeToDeployment` opens an `EventSource` against the same relative path (`/api/v1/deployments/{id}/events`) with `withCredentials: true` — also proxied by the same rewrite rule, so long-lived streaming connections pass through the Next.js server too. `subscribeToDeploymentLogs` does the same against `/api/v1/deployments/{id}/logs`, streaming real-time build/deploy pod log text (rendered by `components/DeploymentLogsPanel.tsx`).
- The rewrite is a **build-and-runtime** config value, not compiled into client JS: `BACKEND_URL` is read by `next.config.js` inside the Node process that serves the app, so it must be set in whatever environment actually runs `node server.js` (see §4), not just at `next build` time.

## 3. `lib/api.ts` — full client surface

One function per backend endpoint it uses; all typed, all going through `apiFetch`/`handleResponse` (which throws `Error(detail)` on non-2xx, reading FastAPI's `{"detail": ...}` shape).

| Function | Method & path called | Backend endpoint |
|---|---|---|
| `registerUser` | `POST /api/v1/users` | `POST /api/v1/users` |
| `loginUser` | `POST /api/v1/users/login` | `POST /api/v1/users/login` |
| `getSession` | `GET /api/v1/session` | `GET /api/v1/session` |
| `logoutUser` | `POST /api/v1/users/logout` | `POST /api/v1/users/logout` |
| `getUserProjects` | `GET /api/v1/users/{user_id}/projects` | same |
| `createProject` | `POST /api/v1/projects` | same |
| `getGitHubInstallations` | `GET /api/v1/github/installations` | same |
| `getGitHubRepositories` | `GET /api/v1/github/repositories` | same |
| `getGitHubBranches` | `GET /api/v1/github/repositories/{id}/branches?installation_id=` | same |
| `getProject` | `GET /api/v1/projects/{project_id}` | same |
| `deleteProject` | `DELETE /api/v1/projects/{project_id}` | same |
| `getDeployment` | `GET /api/v1/deployments/{deployment_id}` | same |
| `redeployProject` | `POST /api/v1/deployments/redeploy/{project_id}` | same |
| `checkProjectUpdate` | `POST /api/v1/projects/{project_id}/check-update` | same |
| `subscribeToDeployment` | `EventSource GET /api/v1/deployments/{id}/events` | same (SSE) |
| `subscribeToDeploymentLogs` | `EventSource GET /api/v1/deployments/{id}/logs` | same (SSE) |

Not called anywhere in the frontend: `PUT/GET /api/v1/projects/{id}/env` (env var editing UI doesn't exist yet), `GET /api/v1/github/connect` and `/callback` (reached via a plain `<a href>`/redirect from the "Connect GitHub" UI rather than `lib/api.ts`, since it's a full-page OAuth redirect, not a fetch) — worth checking `components/`/`app/projects/new/page.tsx` directly if you need the exact link construction.

## 4. `BACKEND_URL` — where it's set

| Context | Value | Set by |
|---|---|---|
| Local dev (`next dev`) | falls back to `http://localhost:8000` (default in `next.config.js`) | not set unless you export it yourself |
| `docker-compose.yaml` (root) | `http://host.docker.internal:8000` | passed both as Docker build `args` **and** container `environment` — the runtime `environment` value is what actually matters for the rewrite, since `next.config.js` is evaluated when `node server.js` starts, not baked into the client bundle |
| Frontend `Dockerfile` | `ARG BACKEND_URL` / `ENV BACKEND_URL` set only in the **builder** stage (`RUN npm run build`); the **runner** stage that actually runs `node server.js` does **not** set it itself | must be supplied by whatever orchestrates the runner container (docker-compose `environment:`, or a Kubernetes env var) — if it's missing there, the proxy silently falls back to `http://localhost:8000`, which is almost certainly wrong outside a dev machine |

Because this is a server-side rewrite and not a `NEXT_PUBLIC_*` variable, the actual FastAPI URL is **never exposed to the browser** — from the browser's perspective, everything under `/api/v1/*` is same-origin with the Next.js app. Anyone probing the frontend for the real backend address won't find it in client JS; it only exists in the Next.js server process's environment.

## 5. Auth/session handling on the frontend

- No token is ever read or stored by frontend JS — the `buetpaas_session` cookie is HttpOnly, set directly by the FastAPI backend's `Set-Cookie` response as it passes back through the Next.js proxy untouched.
- `AuthContext` (`context/AuthContext.tsx`) calls `getSession()` once on mount to hydrate `user`; `login()` just sets local React state after a successful `loginUser()`/`registerUser()` call — the actual authentication state of record is always the cookie, checked server-side by FastAPI's `require_user` on every subsequent request.
- Logout calls the backend to clear the cookie, then does client-side navigation (`router.push("/")`); there's no server-side session invalidation beyond that single call.

## 6. Practical implication for dynamic/security testing

If you're pointing a scanner or proxy at this app:
- **Target the Next.js origin** (e.g. `http://localhost:3000`), not the FastAPI port directly — that's what a real client sees, that's where the `Origin` header the backend checks will naturally be correct, and that's where the session cookie is scoped.
- All `/api/v1/*` paths are functionally identical whether hit through :3000 (proxied) or directly through :8000 (FastAPI) for endpoint *logic*, but only the :3000 path reflects the actual same-origin/CSRF posture of the deployed app — hitting :8000 directly bypasses the Next.js hop entirely and will behave differently with respect to `Origin`/CORS assumptions.
- The full endpoint list, auth model, and request/response shapes live in [backend/BACKEND.md](../backend/BACKEND.md); this file only adds the proxying/session-forwarding layer in front of it.
