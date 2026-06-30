# Parity thresholds & acceptable differences

The gate has two knobs. Tune them in status.md §3 and pass via `verify_screen.py --pixel-threshold`.

## Data mode changes what's gated (`verify_screen.py --data-mode`)

- **record mode** (REAL responses replayed via HAR — both sides show identical data): pixels are **GATED**
  exactly as below. This is the mode for proving pixel parity.
- **live mode** (Vite proxy to the live backend — data is real-time and drifts from the captured shot):
  pixels are **ADVISORY**; the gate is structure + style + **data-presence** (and comparable size). Don't
  fail a live-mode view on a pixel ratio caused by newer data — fail it on structure/style/missing data.
- **Data-presence (both modes):** the React side must actually render the real data — `verify_screen.py`
  fails the gate if React rendered far fewer elements than legacy or has empty tables where legacy had rows.

## The two gates

1. **Structural (DOM lane) — strict, non-negotiable.** Target: **0 critical deltas.** Copy, labels,
   field order, tab order, table columns, and validation/error text must match the legacy screen exactly.
   There is no tolerance here; a critical delta is a real fidelity defect. Do not "raise the threshold" —
   fix the React code.

2. **Visual (pixel lane) — thresholded.** Target: **pixel mismatch ratio ≤ 0.005 (0.5%)** by default.
   Exact-to-the-pixel parity between a JSP/Dojo-rendered page and a React port is not realistic because
   of font rasterization and anti-aliasing. The threshold + AA exclusion absorb that without hiding real
   layout/spacing/color defects (those show up as solid regions well above the floor).

   - `--pixel-threshold 0.005` → gate ratio. Tighten toward `0.001` for simple/static screens; loosen to
     `~0.01` only for dense, font-heavy grids, and say so in status.md.
   - `pixel_diff.js --threshold 0.1` → per-pixel pixelmatch sensitivity (how different a single pixel must
     be to count). Leave at 0.1 unless the legacy app uses sub-pixel text rendering that creates noise.

## Acceptable differences (don't chase these — the team's agents concede the same)

- **Font rendering** when the exact legacy font isn't installed in the capture browser. Install the
  legacy fonts (`theme/fonts/`) into the React app and the capture environment to minimize this; residual
  AA differences are expected.
- **Anti-aliasing** on text/edges/dashed borders. Excluded by `includeAA:false`.
- **Scrollbar styling** (browser/OS dependent). If a scrollbar causes a tall vertical diff band on the
  right edge, capture both sides at the same viewport with the same overflow, or mask that band.

## Making the comparison fair (do this BEFORE blaming the threshold)

A high pixel ratio is usually a capture mismatch, not a fidelity problem:

- **Same viewport** on both sides (`capture_screen.py --viewport` identical). A size mismatch fails the
  gate by design — render React at the legacy viewport.
- **Same data.** In record mode the React side replays the REAL recorded responses (HAR), so both screens
  show identical text/rows — different data ⇒ huge, meaningless pixel diff. (In live mode data legitimately
  differs, which is exactly why live mode gates on structure/style, not pixels.)
- **Fonts loaded / animations settled.** Use `--wait-ms` and the built-in `document.fonts.ready` wait;
  disable CSS transitions in the React app during capture if needed.
- **No transient overlays.** Capture the steady state (loaders gone), as the analyzer captured the legacy.

## When a screen genuinely can't be pixel-exact

Record it: keep the structural gate strict (it still proves the replica is *correct*), set a per-screen
pixel threshold in status.md §3 with a one-line reason, and attach the `side-by-side.png` so a human can
sign off the residual. Never relax the **structural** gate to make a screen pass.
