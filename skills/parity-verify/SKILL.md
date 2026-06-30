---
name: parity-verify
description: Deterministically prove a React screen is a 1:1 replica of a legacy screen. Runs two lanes — a DOM/structure diff (copy, labels, field/tab order, table columns, validation text) and a pixel diff (pixelmatch) — and fuses them into a gated, actionable report that says exactly WHAT differs and WHERE, so the builder makes targeted edits and re-verifies. Use after implementing or changing any screen in the jsp2react flow, before marking it verified. This is the "fidelity proven, not claimed" engine; the model fixes from concrete findings, it does not judge the match by eye.
---

# parity-verify

The proof engine for **jsp2react**. fig2code asks the agent to eyeball two screenshots; that is
subjective. This skill replaces that with a **deterministic gate**: a screen is `verified` only when a
script says so. Two complementary lanes:

- **DOM lane** (`dom_diff.py`) — semantic exactness. Catches what pixels can't: a label typo that looks
  identical, a swapped field, a missing column, changed validation text. These are **critical** and fail
  the gate.
- **Pixel lane** (`pixel_diff.js`, pixelmatch) — visual exactness. Catches what the DOM can't: wrong
  spacing, color, font metrics. Emits a mismatch ratio **and located regions**, each mapped to the React
  element under it so the fix is targeted.
- **Data-presence check** — did the React side actually render the REAL data? Fails the gate if React
  rendered far fewer elements than legacy, or has empty tables where legacy had rows (catches "data missing").

**Two data modes** (`--data-mode`): in **record** mode both sides show the SAME recorded real data, so the
pixel lane is GATED (exact). In **live** mode the React side shows real-time backend data that drifts from
the captured shot, so the pixel lane is ADVISORY and the gate is structure + style + data-presence.

Both sides are captured by `legacy-crawl-capture/capture_screen.py` (same script, same viewport) → the two
`model.json` and the two `png` are always comparable.

> Run each script with `--help` / `--self-check` first.

## Scripts

### verify_screen.py — the one you usually call (fuses both lanes + gate)
```bash
python scripts/verify_screen.py \
  --legacy-model <evidence>/f010_default/legacy.model.json --legacy-png <evidence>/f010_default/legacy.png \
  --react-model  <evidence>/f010_default/react.model.json  --react-png  <evidence>/f010_default/react.png \
  --out-dir <evidence>/f010_default/parity --name f010_default --data-mode record --pixel-threshold 0.005
```
Writes `f010_default.parity-report.md` (read this), `.parity-report.json`, `.diff.png`,
`.side-by-side.png`. **Exit code 0 = PASS, 2 = FAIL** — gate on it in the implementation loop.
PASS (record) = **0 critical structural deltas AND data present AND pixel ratio ≤ threshold AND no size
mismatch**. PASS (live) = **0 critical deltas AND data present AND style match** (pixel advisory).

### dom_diff.py — structural lane alone (importable)
```bash
python scripts/dom_diff.py --legacy a.model.json --react b.model.json --out deltas.json
```
Critical delta types: `text_mismatch`, `missing_in_react`, `extra_in_react`, `table_columns_mismatch`,
`missing_table`/`extra_table`, `tab_order_mismatch`. Advisory: per-element `style` deltas (used as fix
hints for pixel regions, not gated).

### pixel_diff.js — pixel lane alone
```bash
node scripts/pixel_diff.js --legacy a.png --react b.png \
  --out-diff diff.png --out-sxs side-by-side.png --out-regions regions.json --threshold 0.1
```
`--threshold` is the per-pixel pixelmatch sensitivity (0.1 default); the **gate** ratio is the
`--pixel-threshold` in verify_screen.py. AA is excluded so font anti-aliasing doesn't create noise.

## How the driver agent uses it (the fix loop)
```
implement/edit screen → capture_screen.py (react url) → verify_screen.py
   PASS → mark status.md verified
   FAIL → read parity-report.md → fix the criticals, then the located pixel regions → re-run
```
The report is the spec for the next edit. Never mark `verified` without a PASS.

## Dependencies (open source, MIT — manual install, see SETUP.md)
- `pixelmatch` (github.com/mapbox/pixelmatch) + `pngjs` — `npm i -D pixelmatch pngjs`.
- DOM lane is Python stdlib only. Both `model.json` files come from capture_screen.py.

## Reference
- `references/parity-thresholds.md` — choosing thresholds, masking acceptable differences
  (fonts/AA/scrollbars), and what to do when JSP↔React can't be pixel-exact.
