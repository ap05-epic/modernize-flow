---
name: react-replica-kit
description: Scaffold and conventions for the fresh Vite + React + TypeScript app that holds the 1:1 legacy replicas, built FROM the JSP source model + the extracted legacy theme, fed REAL backend data (record mode replays recorded responses via MSW; live mode proxies the real backend via Vite), with a rebuilt login and a navigable evidence index. Use when starting the jsp2react target app and when building each view. Enforces faithful HTML/CSS porting (no component library, no restyling) so nothing is added or "modernized" beyond the framework swap.
---

# react-replica-kit

The target side of **jsp2react**. Each view is rebuilt 1:1 **from its source model + the legacy theme**,
fed **real backend data**. Deliberately minimal: Vite + React + TS, plain CSS Modules using theme CSS
variables, **no component library** (a library would impose its own look and violate "no new artifacts").

## Extract the theme (once, before building)
```bash
python scripts/extract_theme.py --css-dir <webapp>/theme --css-dir <webapp>/platform/styleSheets \
  --out-dir <evidence>/theme        # -> tokens.json + theme.css   (--self-check for a no-file run)
```
Colors/fonts come from these tokens, not per-element guesses (fixes color drift). See `references/theme-extraction.md`.

## Scaffold (once per project)
```bash
bash scripts/scaffold_app.sh <target-dir> <evidence>/theme/theme.css   # path also recorded in status.md
```
Creates a Vite React-TS app, imports `theme.css` globally, wires BOTH data modes (MSW record-replay +
Vite live proxy in `vite.config.ts`), seeds the **Login screen (F000)**, and installs `msw` +
`pixelmatch`/`pngjs`. Data mode: `VITE_DATA_MODE=record` (default, MSW replays REAL recorded responses)
or `VITE_DATA_MODE=live VITE_BACKEND=<url>` (Vite proxy to the real backend). See `references/backend-data-modes.md`.

## Build one view (the driver agent does this per iteration)

1. **Real data** (record mode) — replay this view's REAL recorded responses:
   ```bash
   python <…>/legacy-crawl-capture/scripts/capture_fixtures.py \
     --har <evidence>/<id>/legacy.har --out <target>/src/mocks/<id>
   ```
   The aggregator picks it up automatically. (Live-mode views skip this — the Vite proxy serves the real backend.)
2. **Component FROM SOURCE** — one view → `src/screens/<Name>/`:
   - `<Name>.tsx` — structure translated from `<id>/source-model.json` (loops→`.map()`, `<html:*>`→inputs,
     message keys→exact labels); confirm against the captured DOM model. See `references/jsp-to-react-mapping.md`.
   - `<Name>.module.css` — styles via the theme CSS variables (`var(--color-01)`…); geometry from the captured
     box. See `references/css-porting.md` (tokens-first).
   - fetch through `src/api.ts` (same endpoint paths from `source-model.ajaxEndpoints`). Types from spec.md Appendix B.
   - route by status.md id (hash route `#/<id>`), matching `serve_review.py`.
3. **Render the real data at the same viewport** the legacy capture used.

## Capture the React render for parity (same tool + profile as the legacy side)
```bash
python <…>/legacy-crawl-capture/scripts/capture_screen.py --profile profiles/<id>.json \
  --url http://localhost:5173/#/<id> --out-dir <evidence>/<id> --name react
```
Then `parity-verify/verify_screen.py --data-mode <record|live>` with the legacy + react `model.json`/`png`.
Same capture script + profile on both sides is what makes the diff valid.

## Review side by side
```bash
python scripts/build_index.py --manifest <evidence>/MANIFEST.json    # -> evidence/INDEX.html (static, navigable)
python scripts/serve_review.py --work-dir <evidence> --react-base-url http://localhost:5173 --port 8800
```
`INDEX.html` is the navigable per-view index (thumbnails, status, data mode, links, quarantined captures).
`serve_review.py` adds PASS/FAIL + the `side-by-side.png` + an optional live iframe.

## References
- `references/jsp-to-react-mapping.md` — source-model → React+TS construct mapping, "no new artifacts" rules.
- `references/css-porting.md` — tokens-first CSS porting; fonts, icons, assets, geometry.
- `references/theme-extraction.md` — extracting the legacy palette/fonts into theme tokens.
- `references/backend-data-modes.md` — record (HAR replay) vs live (Vite proxy), session reuse, login.

## Dependencies (open source, MIT — see SETUP.md)
- Vite + React + TypeScript (`npm create vite -- --template react-ts`).
- `msw` (record-mode replay + error injection); `pixelmatch` + `pngjs` for parity. `extract_theme.py`/
  `build_index.py` are stdlib Python (no extra deps).
