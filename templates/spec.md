<!--
  spec.md  —  jsp2react screen catalog & parity contract
  ------------------------------------------------------
  Written/refreshed by jsp2react-analyzer. Read selectively by jsp2react-builder
  (Section 1 once on first run, then only the assigned screen's section).

  This is the DURABLE baseline: what every legacy screen is, the evidence proving it,
  its states, its endpoints/data contracts, and its acceptance criteria. STATUS.md is the
  live journal; this file is the contract. Keep them reconciled.

  EVIDENCE TAGS (every visible requirement carries at least one):
    [SRC:source-model.json:loops|forms|ajax]  parsed JSP source structure (extract_jsp.py) — BUILD INPUT
    [THEME:tokens.json:--color-NN]  legacy palette/font token (extract_theme.py) — colors/fonts come from here
    [SHOT:file.png]        captured legacy screenshot            — visual VERIFICATION target
    [DOM:selector]         from captured legacy rendered DOM     — structural VERIFICATION
    [CSS:file:selector]    from captured computed styles         — exact style values (verify)
    [JSP:path:line]        confirmed in JSP/fragment source      — structure/conditionals
    [ACTION:Class#method]  Struts action / Spring controller     — behavior/forward/endpoint
    [ENDPOINT:METHOD path] the data call (struts .do / REST / WS-feign) — REAL response recorded in HAR
    [MSG:bundle:key]       exact label/validation text from a .properties bundle
    [ASSET:path]           existing icon/font/image to REUSE (never recreate)
    [INFERRED]             assumed, no direct evidence           — low confidence, keep easy to change
  Build from SOURCE ([SRC]/[THEME]/[MSG]); use [SHOT]/[DOM]/[CSS] to VERIFY, not to guess from.
  Rule: NEVER infer a visible state. If a visible state has no [SHOT]/[DOM] evidence AND no [SRC],
  capture it or mark the view `blocked` in STATUS.md — do not invent layout, copy, columns, or controls.
-->

# <Project> — Screen Catalog & Parity Contract

## Section 1 — Legacy & Target Context  (read fully once)

**Legacy stack.** <e.g. Struts 1 + JSP (Tiles) on Spring Boot; client JS = Dojo/jQuery/dataTables;
server: struts/action → service → builder → dao → WS-feign (mainframe).>
**Where truth lives.** Build from SOURCE: each view's `source-model.json` (JSP loops/forms/labels/AJAX
endpoints) gives structure; `tokens.json`/`theme.css` give colors/fonts; `.properties` give exact copy.
The rendered DOM + screenshot are the VERIFICATION target (do not port the Dojo/jQuery framework — match
the observable result). Don't reproduce structure from the image when `source-model.json` states it.
**Real data (two modes).** `record` = MSW replays the REAL recorded responses (responses.har), exact
parity. `live` = Vite proxy to the real backend, real-time data. No hand-authored fixtures. (react-replica-kit.)
**Target conventions.** Fresh Vite + React + TS. One view → one route + one component tree. Plain HTML/CSS
via CSS Modules using the theme CSS variables; no component library. Login (F000) is rebuilt for real auth.
**Naming.** View `<id>_<state>` → `src/screens/<Name>/` (`<Name>.tsx`, `<Name>.module.css`).

## Section 2 — Flow / Family Overview

| Family | Purpose | # Screens | Reach path (how to navigate there) | Key dependencies |
|--------|---------|-----------|-------------------------------------|------------------|
| shell | login + summary scaffold | <n> | entry URL → login → summary hydrates (~Ns) | — |
| fa | <…> | <n> | summary menu → … | FA context (e.g. AB10) |
| … | … | … | … | … |

**Recommended build sequence:** shell → <family> → … (foundational screens first).

## Section 3 — Per-Screen Specs

> One subsection per Screen Inventory row. Template below; copy per screen.

### <id_state> — <View name>  ·  family: <fa>  ·  data mode: `<record|live>`

- **Description.** <what it is / what the user does here>
- **Reach path (from start).** <the FULL click-path from login → … → this view; mirrors nav-path.json.
  NEVER reached by opening a deep link directly. AJAX views come from viewgraph.json.>
- **Source model** ([SRC:source-model.json]; this is the BUILD INPUT — structure from source, not the image):
  - JSP(s): `[JSP:jsp/fateamprofile.jsp]` (+ includes/Tiles: `<…>`)
  - loops → `.map()`: `<c:forEach items=${comp.rows} var=row>` → table rows [SRC:…:loops]
  - conditionals: `<c:if test=${row.active}>` → conditional render [SRC:…:conditionals]
  - form fields (name/type → ActionForm): `<faNumber:text, entityLevel:select>` [SRC:…:forms]
  - AJAX endpoint → trigger → inject: `<GET fadetail.do?tab=comp  ← click "Compensation"  → #compPanel>` [SRC:…:ajax]
  - message keys (exact copy): `<fa.profile.title, …>` [MSG:bundle:key]
- **Theme.** colors/fonts from `[THEME:tokens.json]` (e.g. `--color-01`, `--font-1`, `--fs-13`) — not per-element guesses.
- **Capture contract** (mirrors `profiles/<id_state>.json`; the builder reuses it to capture React):
  - canonical route: `<dispatcherAction.do?page=…&fanum=…>` (works only with a live session)
  - misleading routes (NOT verification targets): `<e.g. direct loginAction.do → error page>`
  - auth context: <pre-auth | authenticated via login-form submit; reuse auth_state.json> · viewport: `1920x1080`
  - readiness: waitFor `<#anchor>` · mustContain `<"Compensation","FA Profile">` · waitForGone `<.loadingMask>`
  - settle: `~Nms` after readiness (data-heavy detail screens need more — see runtime-readiness-and-auth.md)
  - expected assets: `<theme/…, platform/styleSheets/…>` (must be 200; styled-vs-unstyled guard)
  - known failure modes: <e.g. opening the .do without a session shows login; widgets hydrate ~Ns late>
- **Visible states** (enumerate ALL; each needs evidence):
  - default — [SHOT:f0xx_default.png] [DOM:#main]
  - empty — [SHOT:f0xx_empty.png]
  - error/validation — [SHOT:f0xx_error.png] [MSG:errors.properties:fa.required]
  - <tab/modal/expanded/selected/loading/read-only…>
- **Layout & controls** (the 1:1 inventory — copy, labels, field order, tab order, columns):
  - <region/control> — label "<exact>" [MSG:…] · order <n> · [CSS:f0xx.computed.json:.label]
  - table columns (in order): <Col1 | Col2 | …> [DOM:table#grid thead]
  - buttons/actions: <Go | Export PDF | Export Excel> [ASSET:platform/images/pdf.svg]
- **Endpoints / data contract** (REAL responses recorded to responses.har; trigger = the interaction that fires it):
  | METHOD | path | layer (struts/REST/WS-feign) | trigger (click/tab) | response shape | source |
  |---|---|---|---|---|---|
  | GET | <…/fateamprofile.do?…> | struts | <click "Compensation"> | <fields…> | [ACTION:FaTeamProfileAction] |
- **Assets to reuse.** [ASSET:theme/fonts/…] [ASSET:js/lib/ubs-icons/…]
- **Success criteria** (ALL must pass before `verified`):
  - [ ] built from `source-model.json` + theme tokens (structure/labels/colors from source, not the image)
  - [ ] legacy + React captures both `usable:true` and NOT quarantined (.capture.json: readiness ok, not an error page)
  - [ ] data present: React rendered the REAL data (rows/elements match; verify_screen data-presence ok)
  - [ ] parity-verify PASS — record: 0 critical deltas + pixel ≤ threshold; live: 0 critical deltas + style match
  - [ ] copy/labels/validation exact (DOM-diff clean); field order, tab order, table columns exact
  - [ ] record mode renders standalone (HAR replay); live mode renders real-time via proxy (same paths)

## Section 4 — JSP / Struts Inventory Reconciliation

Every `*.jsp` and every `struts-config` action is accounted for (mapped to a screen, a shared
fragment/bucket, or explicitly unresolved). Counts must reconcile against the repo.

- JSPs found in repo: <n>  ·  JSP rows recorded: <n>  ·  unmatched: <list>
- Struts actions found: <n>  ·  rows recorded: <n>  ·  unmatched: <list>

| JSP / action | type (screen/fragment/layout/contentlet/ipad/alt-root) | maps to | relationship (Tiles/forward/include) |
|---|---|---|---|
| <jsp/fateamprofile.jsp> | screen | F0xx | forward from fateamprofile.do |
| <jsp/inc/header.jspf> | fragment | shared:header | included by many |

## Section 5 — Open Questions

| # | Question | Status (RESOLVED/PENDING/N-A) | Default assumption to implement | Source |
|---|----------|-------------------------------|---------------------------------|--------|
| 1 | — | PENDING | — | — |

## Appendix A — Target File Tree (to create)
<the React app screens/components to create, mirroring Section 3 IDs>

## Appendix B — Shared Types / API Contracts
<TypeScript interfaces for the endpoint responses captured as fixtures>
