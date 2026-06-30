---
name: springboot-target-kit
description: Reverse-engineer a legacy flow's DATA layer (Struts action → service/builder → DAO → stored procedure) into a backend-model, then scaffold the Spring Boot target (REST controller → service → SimpleJdbcCall gateway → DTO + OpenAPI) FROM that model, and prove the new endpoint reproduces the legacy data by verifying its JSON against the REAL recorded responses (HAR). Use in FULL (React + Spring Boot) modernization when a flow needs a new backend endpoint, not just a React replica. The deterministic extractor + scaffold + contract-verify are the tools; the business-logic translation stays agent-driven. Stdlib Python only; reuses the HAR that legacy-crawl-capture already records.
---

# springboot-target-kit

The **backend** target side of the modernization (symmetric to `react-replica-kit`, the frontend target).
`extract_jsp.py` parses the JSP for the UI; this parses the **server side** so the driver agent builds the new
endpoint FROM the real stored-procedure contract instead of guessing it.

It is **source-driven**: extract the legacy data layer → a `backend-model.json` → scaffold the Spring Boot
skeleton from it → fill the business logic → verify the endpoint reproduces the legacy data (the recorded
HAR is the oracle). FULL-mode only; the frontend-only fallback never installs this skill.

> Run each script with `--help` / `--self-check` before first use — the CLI is the contract. Black-box tools.

## Scripts

### extract_backend.py — legacy data layer → `backend-model.json` (the BUILD INPUT)
```bash
python scripts/extract_backend.py --action <src>/.../FaSummaryAction.java --source-dir <java-root> \
  --sqlmap-dir <resources>/sqlmaps --project project.json --out <flow>/backend-model.json   # --self-check
```
Traces action → service/builder → DAO → stored proc (bounded). Extracts each SP's name, **typed input
params** (with `source: session|param|form`), **result columns**, plus the flow's `sessionInputs` /
`requestParams`. Signal priority: iBATIS/MyBatis sqlmap XML > Spring `SimpleJdbcCall` > raw
`CallableStatement`. Degrades gracefully and notes what it couldn't resolve. See
`references/stored-procedure-mapping.md`.

### scaffold_backend.py — `backend-model.json` → Spring Boot skeleton
```bash
python scripts/scaffold_backend.py --model <flow>/backend-model.json \
  --out-dir <api>/src/main/java --package com.example.app          # --self-check
```
Generates `<Flow>Controller` (REST) · `<Flow>Service`+Impl · `<Flow>Gateway` (`SimpleJdbcCall` wired to the
SP + declared params) · `<Flow>Dto` (fields = result columns, JDBC→Java typed) · `<flow>.openapi.yaml`. The
**SP wiring, param types, and DTO shape are deterministic; the Service body + result-set mapping + session
binding are TODOs the agent fills** (match legacy semantics first). See `references/backend-layering.md`.

### verify_contract.py — prove the endpoint reproduces the legacy data (the gate)
```bash
python scripts/verify_contract.py --har <view>/legacy.har --endpoint-json new_response.json \
  --match /api/fa-summary --data-mode record         # exit 0 = PASS, 2 = FAIL ; --self-check
```
Compares the new endpoint's JSON against the **legacy recorded HAR** (the oracle the frontend capture already
produced): field presence + types (+ record-mode values + row count). Same exit contract as
`parity-verify/verify_screen.py`. Fix the gateway/DTO mapping from the concrete delta until it PASSES.

## Typical builder flow (FULL mode, one flow at a time)
```
extract_backend.py  → <flow>/backend-model.json            (SP contract + session/request inputs)
scaffold_backend.py → <api>/src/main/java/.../{Controller,Service,Gateway,Dto}.java + openapi
  → agent fills: result-set→DTO mapping, ServiceImpl business logic, session/auth binding
     (references/session-auth-state.md)
  → run the Spring Boot app; curl the endpoint to new_response.json
verify_contract.py  → PASS/FAIL vs <view>/legacy.har       (record = exact fields/values; live = structure)
  → fix from the delta → re-verify → mark the flow's backend rows verified in status.md
```
The React side then points `src/api.ts` at the new `/api/<flow>` endpoint (or keeps record/live mode until
the endpoint exists — a strangler cutover).

## References
- `references/backend-layering.md` — the React→controller→service→gateway→SP layering; generated-vs-you;
  "don't leak Struts/JSP into the API"; what to do when the legacy screen has no JSON endpoint.
- `references/stored-procedure-mapping.md` — reading sqlmaps/SimpleJdbcCall/raw JDBC; param-source resolution;
  JDBC→Java/JSON types; finishing the result-set mapping; CICS/COMMAREA note.
- `references/session-auth-state.md` — modeling user/entity/split/entitlement context; how to carry each
  input; the "never flatten stateful behavior into naive query params without documenting" rule; login.

## Dependencies
Stdlib Python only (no extra installs). The target app needs Spring Boot + a JDBC `DataSource` to the legacy
DB (JDK + Maven/Gradle on the pod — `install.sh full` *checks* for these). `verify_contract.py` reuses the
HAR from `legacy-crawl-capture`; no new dependency.
