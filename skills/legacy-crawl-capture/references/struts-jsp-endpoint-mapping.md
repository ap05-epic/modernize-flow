# Deriving endpoints & data contracts from JSP/Struts (for fixtures + React wiring)

Goal: for each screen, list **every data call it makes** and **the shape of each response**, so we can
(a) replay the REAL recorded response in record mode (MSW) and (b) wire the React replica to the same
endpoint paths. This is the "separate the UI from the data" half of fidelity — the UI look comes from the
captured screen; the data comes from these contracts.

## The three backend layers (trace all three)

| Layer | How to recognize it | Where the call goes | Contract source |
|---|---|---|---|
| **Struts action** | `*.do` in markup; `<action path>` in `struts-config.xml` | `…Action.execute()` → service → builder → DAO | the JSP forward + `name=` ActionForm fields; the action's request params |
| **Spring REST** | `fetch`/XHR to `/api/...`; `@RestController`/`@RequestMapping` in `api/controller` | controller → service → DAO / feign | the controller method signature + the DTO it returns (`api/dto`) |
| **WS / feign (→ mainframe)** | `<app>-WebServiceClient`, `*.wsdl`, `@FeignClient`, `…/ws/…` | external service / mainframe | the WSDL types or feign interface return type |

The **mainframe** data enters through the WS/feign layer (and, where a CICS program backs it, through the
CICS COMMAREA / DB2 declarations — see the team's `cics-analysis` agent if COBOL/BMS source is available).
You do **not** call the mainframe to render — in record mode the REAL recorded response (HAR) stands in for
it; in live mode the Vite proxy reaches the real backend through this layer.

> **FULL mode — the backend is now in scope.** When the target includes a Spring Boot backend, the
> `springboot-target-kit` skill reverse-engineers this same data layer (Struts action → service → DAO →
> stored procedure, reading `project.db.sqlmapDir`) and **generates the new endpoint** (controller →
> service → `SimpleJdbcCall` gateway → DTO), verifying its JSON against the recorded HAR. See its
> `references/stored-procedure-mapping.md` and `references/backend-layering.md`. In FRONTEND-only mode you
> stop at the data contract here and wire React to the recorded (record) / proxied (live) responses.

## How to trace one screen

1. **Start from the action.** In `screens.json`, the screen's `action_do` + `type` + `forwards.success`
   give you the JSP and the action class. Open the action class.
2. **Find the data the action puts on the request/session** (`request.setAttribute(...)`, form population,
   service calls). Each service call that the JSP later iterates over is a data contract.
3. **Find dynamic calls in the JSP/JS.** Grep the JSP and its `*.js` for `.do`, `/api/`, `ajax`, `fetch`,
   `XMLHttpRequest`, dataTables `ajax:` configs, Dojo `xhr`. Each is a runtime endpoint.
4. **Confirm at runtime.** The endpoints that actually fire are already in `<name>.network.json` from
   `capture_screen.py`. Cross-check the static trace against the captured network — the captured set is
   authoritative for what the screen loads; the source explains *why* and gives field names/types.
5. **Record** in spec.md §3 "Endpoints / data contract" table: METHOD, path, layer, request params,
   response shape, and the `[ACTION:Class#method]` / `[ENDPOINT:…]` evidence tag.

## Response shape → TypeScript + fixture

- For **JSON** (REST/feign), the captured body in `network.json` IS the shape. Derive a TS interface for
  Appendix B and let `capture_fixtures.py` emit the fixture verbatim.
- For **Struts `.do` that returns HTML**, the "data" is whatever the JSP iterates (a list/bean). The React
  replica should fetch a JSON equivalent of that bean. If the legacy screen loads its grid via a later
  XHR (common with dataTables/clusterize), fixture that XHR. If the data is baked into the server-rendered
  HTML, derive the replay fixture from the captured DOM model (`model.json` table headers + rows) — it's
  still the REAL rendered data, not hand-authored.

## CICS / mainframe note (only if COBOL/BMS source is in scope)

When a feign/WS endpoint is backed by a CICS program, the team's `cics-analysis` mapping applies — use it
to name the contract precisely:

| CICS / mainframe construct | REST/JSON contract the React app consumes |
|---|---|
| COMMAREA fields (PIC clauses) | request/response JSON fields (+ types) |
| `DECLARE TABLE` / DB2 columns | response object fields |
| `SEND MAP` / `RECEIVE MAP` (BMS) | GET render payload / POST submit payload |
| `READ … RIDFLD` (by key) | `GET /resource/{id}` |
| `STARTBR/READNEXT` (browse) | paginated `GET /resource?page=` |

Keep this strictly for **wiring**. Visible copy, labels, columns, and validation text come from the
captured screen + `.properties` bundles — never from a backend payload.
