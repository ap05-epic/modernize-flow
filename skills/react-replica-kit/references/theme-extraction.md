# Theme extraction — colors & fonts from the legacy CSS source

The reported defect was colors drifting. Cause: v1 pasted color/font values per element from runtime
pixels, so every screen re-guessed and small errors crept in. v2 harvests the **real theme from the
legacy CSS source once**, app-wide, and the driver agent styles from those tokens.

## Run it (once, app-wide)
```bash
python scripts/extract_theme.py \
  --css-dir <webapp>/theme --css-dir <webapp>/platform/styleSheets \
  --out-dir <evidence>/theme
# quick check, no files needed:
python scripts/extract_theme.py --self-check
```
Stdlib-only regex harvest (no Node dependency needed). It scans every `*.css` (pruning vendor dirs like
`dojo/`, `jquery*/`, `pdfjs/`), tallies declared **colors, font stacks, font sizes, weights, spacing,
radii**, ranks them by frequency, and writes:

- `tokens.json` — the ranked inventory (`value` + `count`) per category — the source of truth.
- `theme.css` — e.g. `:root { --color-01: #1f4e79; --font-1: '<App Brand Font>',sans-serif; --fs-13: 13px; … }`,
  top values as CSS variables, ordered by frequency (values shown are illustrative — yours come from the harvest).

## How the agent uses it
- `scaffold_app.sh <target> <evidence>/theme/theme.css` copies `theme.css` into the app and imports it
  globally (`src/main.tsx`), so every component can use `var(--color-01)`, `var(--font-1)`, `var(--fs-13)`.
- Style each element with the **token**, not a hard-coded hex. Use the captured computed value only to pick
  *which* token matches (or to fill a gap the harvest missed), never as a per-element copy-paste.
- Result: one consistent palette/type scale across all screens → color parity stops drifting.

## Optional upgrade: css-tree
For deeper CSS analysis (full AST, de-duping shorthands, resolving variables) you can swap in
`css-tree` (github.com/csstree/csstree, MIT) or `@projectwallace/css-design-tokens` (MIT). They give a
real CSS AST instead of a regex harvest. Not required — the stdlib harvester is enough for token
extraction and keeps the analysis tooling dependency-free; reach for css-tree only if the regex misses something.

## Rules
- Extract the theme **before** building any screen; record its path in status.md §1.
- Reuse the legacy **font files** from `theme/fonts/` (copy `.woff/.woff2/.ttf`, declare `@font-face` with the
  same family names the tokens reference) — don't substitute a lookalike system font.
- Tokens are app-wide; per-screen one-offs that aren't in the palette are a smell — confirm against the
  captured computed style before adding a non-token value.
