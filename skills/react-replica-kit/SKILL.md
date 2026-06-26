---
name: react-replica-kit
description: Scaffold and conventions for the fresh Vite + React + TypeScript app that holds the 1:1 legacy replicas, wire captured fixtures via MSW so screens render with no live backend, and serve a side-by-side review of legacy vs React. Use when starting the jsp2react target app and when building each screen component. Enforces faithful HTML/CSS porting (no component library, no restyling) so nothing is added or "modernized" beyond the framework swap.
---

# react-replica-kit

The target side of **jsp2react**. The app's only job is to render each legacy screen 1:1 from captured
evidence. Deliberately minimal: Vite + React + TS, plain CSS Modules, **no component library** (a library
would impose its own look and violate "no new artifacts").

## Scaffold (once per project)
```bash
bash scripts/scaffold_app.sh <target-dir>     # path also recorded in STATUS.md
```
Creates a Vite React-TS app, installs `msw` + `pixelmatch`/`pngjs`, runs `msw init public/`, and wires
`src/mocks/` (auto-aggregating handlers) + an MSW bootstrap in `src/main.tsx`. MSW is ON by default;
`VITE_MSW=off npm run dev` hits the real backend (data-wiring QA only).

## Build one screen (the builder does this per iteration)

1. **Fixtures** — wire this screen's captured data:
   ```bash
   python <…>/legacy-crawl-capture/scripts/capture_fixtures.py \
     --network work/screenshots/<id>.network.json --out <target>/src/mocks/<id>
   ```
   The aggregator picks it up automatically (no manual registration).
2. **Component** — one screen → `src/screens/<Name>/`:
   - `<Name>.tsx` — structure ported from the captured DOM model + JSP source (see mapping reference).
   - `<Name>.module.css` — styles ported from the captured computed styles (see css-porting reference).
   - `data.ts` — fetch the same endpoint path(s); MSW returns the fixture. Types from spec.md Appendix B.
   - route it by its STATUS.md id (e.g. hash route `#/<id>`), matching what `serve_review.py` links to.
3. **Render the same data + viewport** the legacy screenshot used (MSW on).

## Capture the React render for parity (same tool as the legacy side)
```bash
python <…>/legacy-crawl-capture/scripts/capture_screen.py \
  --url http://localhost:5173/#/<id> --out-dir work/react --name <id>_default --viewport 1920x1080
```
Then run `parity-verify/verify_screen.py` with the legacy + react `model.json`/`png`. Using the same
capture script on both sides is what makes the diff valid.

## Review side by side
```bash
python scripts/serve_review.py --work-dir work --react-base-url http://localhost:5173 --port 8800
```
Per screen: PASS/FAIL, pixel %, the `side-by-side.png` (legacy | react | diff), a link to the report,
and an optional live iframe.

## References
- `references/jsp-to-react-mapping.md` — JSP/Struts/Dojo construct → React+TS construct, and the
  "no new artifacts" rules (what you may and may not change).
- `references/css-porting.md` — porting legacy CSS faithfully into CSS Modules; fonts, icons, assets.

## Dependencies (open source, MIT — see SETUP.md)
- Vite + React + TypeScript (`npm create vite -- --template react-ts`).
- `msw` (github.com/mswjs/msw); `pixelmatch` + `pngjs` for parity.
