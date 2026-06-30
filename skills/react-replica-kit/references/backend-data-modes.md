# Backend data modes — REAL data, never fakes

The replica must render **real backend data**, not hand-authored fixtures. There are two modes; pick per
view in status.md (`data_mode: record | live`). Copilot can choose on the pod based on what works.

## record mode — replay the REAL recorded responses (exact parity)
At capture, the driver agent (analysis mode) records the legacy view's ACTUAL responses to a HAR, then
converts them to MSW replay handlers:
```bash
# 1) the agent captured the real responses:
capture_screen.py --profile profiles/<id>.json --out-dir <evidence>/<id> --name legacy --record-har
# 2) convert the REAL responses -> replay handlers (no hand-authored data):
capture_fixtures.py --har <evidence>/<id>/legacy.har --out <app>/src/mocks/<id>
# 3) run (record is the default):
npm run dev
```
MSW returns the **exact bytes** the real backend returned. Because both sides show identical data, the
pixel diff is meaningful → this is the mode for **exact parity**.

## live mode — proxy the real backend (real-time data)
No MSW; the Vite dev proxy (written by `scaffold_app.sh` into `vite.config.ts`) forwards calls to the live
backend, carrying the session cookie:
```bash
VITE_DATA_MODE=live VITE_BACKEND=http://127.0.0.1:8080 npm run dev
```
All fetches go through `src/api.ts` with `credentials:'include'`, so the **real session** authenticates the
**real backend**. Live data drifts from the captured screenshot, so parity here gates on **structure +
style + data-presence**, with pixels advisory (`verify_screen.py --data-mode live`).

> **FULL mode — a generated backend.** record/live both target the *legacy* backend's responses. In FULL
> (React + Spring Boot) modernization, the `springboot-target-kit` skill **generates a new Spring Boot
> endpoint** (controller → service → `SimpleJdbcCall` gateway → DTO) and verifies its JSON against the same
> recorded HAR; `live` mode can then point at that new `/api/<flow>` endpoint instead of the legacy `.do`.
> See springboot-target-kit's `references/backend-layering.md` and `references/stored-procedure-mapping.md`.

## Auth / session (login is rebuilt)
- Login is a real screen (F000), rebuilt 1:1 from its source model. It POSTs the app's real login action
  (`VITE_LOGIN_ACTION`, from `project.loginAction` — example: `/BAA/loginAction.do`) so a real session is established.
- That session cookie then authenticates data calls in **both** modes (record replays responses captured
  under a valid session; live proxies with the cookie). The Vite proxy uses `cookieDomainRewrite:'localhost'`
  so the backend cookie sticks to the dev origin.
- If the backend needs platform/GCS session bits that don't exist on localhost, that's a runtime issue, not a
  React issue — see `legacy-crawl-capture/references/runtime-readiness-and-auth.md`.

## Which mode when
| Want | Mode |
|---|---|
| Exact pixel parity, reproducible, no live backend needed | **record** |
| Prove the rebuilt UI works against the *live* backend (data-wiring QA) | **live** |
| Most views during the build/verify loop | **record** (then spot-check **live**) |

## Rules
- **Never hand-author response data.** If a response is missing in record mode, re-record it; if missing in
  live mode, fix the proxy/session — don't fabricate.
- Keep endpoint **paths identical** to the legacy app in both modes (same `*.do`/`/api/` paths) so flipping
  modes needs no code change.
- MSW is now ONLY for record-mode replay (and optional error-state injection) — it is not the default fake-data
  layer it was in v1.
