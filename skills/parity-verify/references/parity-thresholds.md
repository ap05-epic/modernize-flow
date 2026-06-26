# Parity thresholds & acceptable differences

The gate has two knobs. Tune them in STATUS.md §3 and pass via `verify_screen.py --pixel-threshold`.

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
     `~0.01` only for dense, font-heavy grids, and say so in STATUS.md.
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
- **Same data.** The React side must render the captured fixture (MSW on), so both screens show identical
  text/rows. Different data ⇒ huge, meaningless pixel diff.
- **Fonts loaded / animations settled.** Use `--wait-ms` and the built-in `document.fonts.ready` wait;
  disable CSS transitions in the React app during capture if needed.
- **No transient overlays.** Capture the steady state (loaders gone), as the analyzer captured the legacy.

## When a screen genuinely can't be pixel-exact

Record it: keep the structural gate strict (it still proves the replica is *correct*), set a per-screen
pixel threshold in STATUS.md §3 with a one-line reason, and attach the `side-by-side.png` so a human can
sign off the residual. Never relax the **structural** gate to make a screen pass.
