# Porting legacy CSS faithfully — TOKENS first (CSS Modules)

Colors and fonts come from the **extracted theme** (`extract_theme.py` → `theme.css` CSS variables +
`tokens.json`), imported globally. Style from those tokens, not per-element guesses — that's what keeps
color/typography consistent across screens and stops the drift that was reported. The captured computed
styles (`<id>.model.json` → each element's `style{}`) are how you pick WHICH token and fill gaps (box
geometry, spacing) — and how parity verifies the result.

## Method

1. Style each element with the theme tokens; use the captured `style{}` to choose the matching token and to
   set geometry (box metrics aren't in the palette). Don't paste a raw hex when a token exists.
   ```css
   /* FaTeamProfile.module.css — colors/fonts via theme vars; geometry from the captured box */
   .panel { color: var(--color-03); background-color: var(--color-07);
            font-family: var(--font-1); font-size: var(--fs-13); line-height: 15px; letter-spacing: 1px;
            width: 792px; padding: 8px 12px; border: 1px solid var(--color-11); box-sizing: border-box; }
   ```
2. If the captured value isn't in `tokens.json`, confirm it against the computed style, then add it (it's a
   real legacy value the harvest missed) — don't invent a "close" color.
3. The CSS Module class name is internal (parity compares computed styles, not class names). Match the *values*.
4. Use the parity report's **advisory style hints** as a punch-list: each names a prop with `legacy vs react`
   values for a located element — set the React value (usually: point it at the right token) and re-verify.

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
