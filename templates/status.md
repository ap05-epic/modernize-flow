# Project Status — <app> modernization

> The driver agent (`modernize-flow` in FULL mode, `jsp2react` in FRONTEND mode) creates and OWNS this file.
> It is the control plane — **always read it first**. Humans only override config; the agent fills the rest.
> Machine config lives in `project.json` (this section mirrors it for humans).

## Project Config
- Mode: `full` (React + Spring Boot)  |  `frontend` (React only — fallback)
- project.json: `<path>`            <!-- the machine config every script reads via --project -->
- App name / context root: `<App>` / `/<ctx>`
- Legacy app URL: `<http://host:port/ctx/...>`
- Legacy source path(s): `<.../src/main/webapp>` , `<struts-config.xml>` , `<.../sqlmaps>` (FULL)
- Target frontend path: `<work/<app>-ui>`
- Target backend path: `<work/<app>-api>`   (FULL only)
- Legacy run command: `<how to start the legacy app, or n/a if already running>`
- Target run command(s): `ui: npm run dev`  ·  `api: ./mvnw spring-boot:run` (FULL)
- Login: action `<from project.loginAction>` · fields `<user>/<pass>` · auth_state `<path>`
- Default demo URL / screen: `<the strongest demo flow>`
- Viewport: `<1920x1080>`   ·   Evidence root: `<work/evidence>`   ·   INDEX: `evidence/INDEX.html`
- Shared artifacts: theme `evidence/theme/{tokens.json,theme.css}` · viewgraph `evidence/viewgraph.json`

## Architecture
- Source stack: `<Struts 1 + JSP (Tiles) + Dojo/jQuery; iBATIS/JDBC -> DB2 stored procs>`
- Target stack: `<Vite + React + TS frontend>`  +  `<Spring Boot REST -> service -> SimpleJdbcCall gateway -> stored proc>` (FULL)
- Data mode per feature: `record` (replay REAL recorded HAR) | `live` (Vite proxy to legacy) | `api` (the new Spring Boot endpoint, FULL)

## Current Iteration
- Active feature: `<ID — one control/slice>`
- Goal: `<what "done" means for this row>`
- Dependencies: `<IDs that must be complete first>`

## Feature Inventory
One row per **user-visible control / state / slice** (NOT one row per page). If a row reads only
"X page" or "X flow", it is too coarse — split it before coding. IDs: shared `S1..`, then per flow
(e.g. `CL1..`, `D1..`). FULL mode adds backend rows (session endpoint, API contract, gateway, DTO).

| ID | Flow | Feature / Slice | Depends On | Data mode | Status | Evidence | Notes |
|----|------|-----------------|------------|-----------|--------|----------|-------|
| S1 | shared | login (rebuilt) + session bootstrap | — | live | not started | evidence/login__default/ | auth feeds all data calls |
| S2 | shared | page shell / nav | S1 | record | not started | | |
| F1 | <flow> | page shell | S2 | record | not started | evidence/<flow>__default/ | source-model.json is the build input |
| F2 | <flow> | <period dropdown> | F1 | record | not started | | distinct control = its own row |
| F3 | <flow> | summary table | F1 | record | not started | | |
| F4 | <flow> | empty state | F3 | record | not started | | |
| F5 | <flow> | error state | F3 | record | not started | | |
| B1 | <flow> | API contract + DTO (Spring Boot) | F3 | api | not started | <flow>/backend-model.json | FULL only |
| B2 | <flow> | gateway -> stored proc | B1 | api | not started | | verify vs legacy HAR |

**Status legend (the lifecycle — use these EXACTLY, no synonyms):**
`not started` · `in progress` · `implemented` (code done, not yet verified) · `verified` (parity/contract
gate PASSED) · `signed off` (human-accepted) · `blocked` (record the blocker in §Blockers).

## Decisions
- <high-impact answers known upfront — auth model, which flows, any POC simplification of session/state
  (REQUIRED to record here if you flatten stateful behavior — see springboot session-auth-state.md)>

## Verification Notes
- <per-feature: how it was proven — parity report path, contract-verify result vs HAR, build/compile, screenshots>

## Blockers & Notes
| ID | Type (blocker/note) | Detail | Recovery attempts | State |
|----|---------------------|--------|-------------------|-------|

## Completion Log
| Date | Feature(s) | From → To status | Result | Notes |
|------|------------|------------------|--------|-------|

## Next Recommended Step
- <the single next unblocked feature, by ID>
