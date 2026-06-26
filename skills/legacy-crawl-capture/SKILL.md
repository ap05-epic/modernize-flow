---
name: legacy-crawl-capture
description: Discover every screen in a legacy JSP/Struts web app and capture each screen state as comparable evidence (screenshot + normalized DOM model + a11y + network), plus turn captured network traffic into MSW fixtures. Use when converting a legacy JSP/Java/Struts UI to React and you need to enumerate all screens and capture the source-of-truth evidence the jsp2react agents replicate and verify against. Reuses the pod's webapp-snapshot (login/screenshots) and webapp-testing (Playwright/server) skills; adds discovery, normalized capture, and fixture generation that those skills do not provide.
---

# legacy-crawl-capture

Source-of-truth capture for the **jsp2react** system. fig2code extracts a static Figma design; this
skill extracts a **live, running legacy screen** — and the original JSP/Struts source behind it.

It does three things the pod's existing skills don't:
1. **Discover** the full screen graph from `struts-config.xml` + JSP scan (so nothing is missed).
2. **Capture** each screen state into a *normalized model* that can be diffed deterministically
   against the React render (the SAME script captures both sides → always comparable).
3. **Fixture** the captured network so the React replica renders identical data with no backend.

> Always run a script with `--help` (and `--self-check` where offered) before first use — the CLI is
> the contract. These are black-box tools; do not read the source unless customizing.

## Prerequisites (reused pod skills — do not reinvent)

- **Login** → produce `auth_state.json` once via `webapp-snapshot/scripts/save_auth_state.py`
  (or creds-form / env-bypass / token-query per that skill's `SSO_AUTH_GUIDE.md`). All capture
  commands reuse it with `--auth-state auth_state.json`.
- **Playwright** is available because `webapp-testing` uses it. If a launch fails, see webapp-testing.
- **Screenshots-only** quick checks can still use `webapp-snapshot/scripts/snapshot_single.py`;
  this skill's `capture_screen.py` is for the *full evidence bundle* parity needs.

## Scripts

### crawl_screens.py — enumerate every screen (deterministic-first)
```bash
# Authoritative inventory from source (no browser): actions + JSPs + links, reconciled by family.
python scripts/crawl_screens.py \
  --struts-config <…>/WEB-INF/struts-config.xml \
  --webapp-dir   <…>/BAA/src/main/webapp \
  --out screens.json

# Optional: also harvest the live reachable set (bounded BFS) once logged in.
python scripts/crawl_screens.py --webapp-dir <…> --runtime-url <summary-url> \
  --auth-state auth_state.json --max-pages 60 --out screens.json
```
Vendor/build dirs (`pdfjs`, `dojo`, `jquery*`, `lib`, `locale`, `node_modules`, `coverage`,
`target`, `dist`, `build`) are pruned automatically. `screens.json.reconciliation` is the
"did we miss a screen?" gate — every screen JSP/action must become a STATUS.md row or an explicit
unmatched entry in spec.md §4.

### capture_screen.py — capture ONE state as comparable evidence (legacy OR react)
```bash
python scripts/capture_screen.py --url <legacy-screen-url> \
  --out-dir work/screenshots --name f010_default \
  --auth-state auth_state.json --viewport 1920x1080 --wait-ms 8000
```
Outputs `f010_default.{png,dom.html,model.json,a11y.json,network.json}`.
- Use the **same `--viewport`** for the legacy screen and the React render — parity depends on it.
- `--wait-for SELECTOR` / `--wait-ms N` handle hydration (stateful Struts shells appear before usable).
- `--workflow steps.json` navigates to a deep state first (vocab: navigate/click/fill/select/wait),
  the same way `webapp-snapshot/snapshot_workflow.py` does — use it for tabs/modals/drill-downs.
- `<name>.model.json` is the normalized structural model that `parity-verify/dom_diff.py` consumes.
  **The builder captures the React render with this very script**, guaranteeing both models match shape.

### capture_fixtures.py — captured traffic → MSW fixtures + handlers
```bash
python scripts/capture_fixtures.py --network work/screenshots/f010_default.network.json \
  --out <react-app>/src/mocks
```
Writes `fixtures.json` + `handlers.ts` (MSW v2) keyed by `METHOD pathname`. Data calls (xhr/fetch)
only by default; `--include-documents` to also keep HTML responses. See react-replica-kit for wiring.

## Typical analyzer flow
```
save_auth_state.py            → auth_state.json            (login skill; once)
crawl_screens.py              → screens.json               (full inventory)
for each screen/state:
  capture_screen.py           → png + model + network      (evidence bundle)
capture_fixtures.py           → src/mocks/{fixtures,handlers}
→ analyzer writes spec.md, seeds STATUS.md, updates MANIFEST.json
```

## Reference
- `references/struts-jsp-endpoint-mapping.md` — how to derive each screen's endpoints and data
  contracts from JSP/Struts source across the 3 backend layers (Struts `.do`, Spring REST,
  WS/feign→mainframe), and how that maps to fixtures + React data wiring.
