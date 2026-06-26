# Porting legacy CSS faithfully (CSS Modules)

The captured **computed styles** (`<id>.model.json` → each element's `style{}`) are the source of truth
for visual values, backed by the legacy `*.css`. Copy exact values; do not round or approximate (same
discipline fig2code uses with Figma design-context values).

## Method

1. For each element you port, read its captured `style{}` (font, size, weight, color, background, border,
   box metrics) and paste those values into a CSS Module class. CSS values are already in `px`/hex — no
   conversion.
   ```css
   /* FaTeamProfile.module.css — values pasted from captured computed styles */
   .panel { color:#646464; background-color:#e6e3e0; font-family:'Frutiger 45 Light',sans-serif;
            font-size:13px; line-height:15px; letter-spacing:1px; width:792px;
            padding:8px 12px; border:1px solid #cccccc; box-sizing:border-box; }
   ```
2. The CSS Module class name is internal (parity compares computed styles, not class names). Match the
   *values*, not the legacy selectors.
3. Use the parity report's **advisory style hints** as a punch-list: each one names a prop with `legacy vs
   react` values for a located element — set the React value to the legacy value and re-verify.

## Fonts (biggest source of pixel noise)

- Reuse the legacy fonts from `theme/fonts/` — copy the `.woff/.woff2/.ttf` into the React app and declare
  `@font-face` with the **same family names** the computed styles reference. Matching the real font makes
  text metrics line up, which collapses most of the pixel diff.
- Install the same fonts in the capture environment too, so both screenshots rasterize identically.

## Icons, images, and other assets — reuse, never recreate

- Copy the exact legacy asset (`platform/images/*`, `*.svg`, `ubs-icons`) into `public/assets/` and
  reference it. Recreating an icon by hand is a "new artifact" and will fail parity.
- Match the rendered size/position of the asset from the captured box, not the intrinsic file size.

## Base/reset styles

- Legacy pages inherit browser defaults plus a global stylesheet. Port the relevant global rules
  (body font, default margins, table border-collapse, link colors) into `index.css` so inherited values
  match. A divergent UA default (e.g. default `<table>` spacing) shows up as a broad pixel diff.

## Layout

- Reproduce the legacy box model exactly: `width/height`, `padding`, `margin`, `border`, `box-sizing`,
  `display`, `position`. The captured `box{}` (x/y/w/h) is the geometry target; the captured `style{}` is
  how to achieve it.
- Prefer the same layout primitive the legacy used (table layout stays a table; float/flow stays in flow).
  Don't "modernize" a table grid into flexbox if it shifts pixels.

## Don't

- No CSS framework/reset library (Tailwind, Bootstrap, normalize.css) — they change values. Plain CSS only.
- No global restyling. Scope everything to the screen's module so one screen can't drift another.
