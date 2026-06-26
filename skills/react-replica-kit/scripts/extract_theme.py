#!/usr/bin/env python3
"""
extract_theme.py — harvest a real design theme from the LEGACY CSS SOURCE.

Colors/fonts in v1 were pasted per-element from runtime pixels, so they drifted. This builds
the React app's theme from the actual legacy stylesheets instead: it scans the legacy CSS
(theme/, platform/styleSheets/, etc.), tallies every declared color / font stack / font size /
weight / spacing, ranks them by frequency, and emits:

  tokens.json   the ranked inventory (value + count) for colors, fontFamilies, fontSizes,
                fontWeights, spacing, radii  — the source of truth for the palette
  theme.css     :root { --color-01: #006286; --font-1: 'Frutiger 45 Light', sans-serif;
                --fs-13: 13px; ... }  — imported globally by the React app so every screen
                starts from the legacy palette, not a guess.

Stdlib only (regex harvest — no Node/css-tree needed). css-tree is a fine optional upgrade for
deep AST analysis; for token harvesting this is enough and keeps the analyzer dependency-free.

Usage:
  python extract_theme.py --css-dir <webapp>/theme --css-dir <webapp>/platform/styleSheets --out-dir evidence/theme
  python extract_theme.py --css a.css --css b.css --out-dir out
  python extract_theme.py --self-check
"""
import argparse, json, os, re

PRUNE = re.compile(r"(^|[\\/])(dojo|dijit|jquery[^\\/]*|pdfjs|node_modules|dist|build|target|coverage|locale)([\\/]|$)", re.I)
RE_COMMENT = re.compile(r"/\*.*?\*/", re.S)
RE_HEX     = re.compile(r"#([0-9a-fA-F]{3,8})\b")
RE_FUNCCOL = re.compile(r"\b(rgba?|hsla?)\(([^)]*)\)", re.I)
RE_FONTFAM = re.compile(r"font-family\s*:\s*([^;}{]+)", re.I)
RE_FONTSZ  = re.compile(r"font-size\s*:\s*([0-9.]+)(px|rem|em|pt|%)", re.I)
RE_FONTWT  = re.compile(r"font-weight\s*:\s*(\d{3}|bold|bolder|lighter|normal)\b", re.I)
RE_SPACE   = re.compile(r"\b(?:margin|padding|gap|top|left|right|bottom)[a-z-]*\s*:\s*([^;}{]+)", re.I)
RE_PXVAL   = re.compile(r"(-?\d+(?:\.\d+)?)px")
RE_RADIUS  = re.compile(r"border-radius\s*:\s*([0-9.]+)(px|rem|em|%)", re.I)


def norm_hex(h):
    h = h.lower()
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) in (6, 8):
        return "#" + h
    return None


def tally(counter, key):
    if key:
        counter[key] = counter.get(key, 0) + 1


def harvest(css):
    css = RE_COMMENT.sub(" ", css)
    colors, fonts, sizes, weights, spacing, radii = {}, {}, {}, {}, {}, {}
    for m in RE_HEX.finditer(css):
        tally(colors, norm_hex(m.group(1)))
    for m in RE_FUNCCOL.finditer(css):
        tally(colors, "%s(%s)" % (m.group(1).lower(), re.sub(r"\s+", "", m.group(2))))
    for m in RE_FONTFAM.finditer(css):
        stack = re.sub(r"\s+", " ", m.group(1).strip()).rstrip("!important").strip()
        if stack and "var(" not in stack:
            tally(fonts, stack)
    for m in RE_FONTSZ.finditer(css):
        tally(sizes, m.group(1) + m.group(2).lower())
    for m in RE_FONTWT.finditer(css):
        tally(weights, m.group(1).lower())
    for m in RE_SPACE.finditer(css):
        for px in RE_PXVAL.findall(m.group(1)):
            tally(spacing, px + "px")
    for m in RE_RADIUS.finditer(css):
        tally(radii, m.group(1) + m.group(2).lower())
    return colors, fonts, sizes, weights, spacing, radii


def ranked(counter, limit=None):
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    items = items[:limit] if limit else items
    return [{"value": v, "count": c} for v, c in items]


def build_theme_css(tokens):
    lines = [":root {"]
    lines.append("  /* colors (ranked by frequency in the legacy CSS) */")
    for i, c in enumerate(tokens["colors"][:24], 1):
        lines.append("  --color-%02d: %s;  /* x%d */" % (i, c["value"], c["count"]))
    lines.append("  /* font stacks */")
    for i, f in enumerate(tokens["fontFamilies"][:6], 1):
        lines.append("  --font-%d: %s;  /* x%d */" % (i, f["value"], f["count"]))
    lines.append("  /* font sizes */")
    for s in tokens["fontSizes"][:12]:
        key = re.sub(r"[^0-9a-z]", "", s["value"])
        lines.append("  --fs-%s: %s;" % (key, s["value"]))
    if tokens["spacing"]:
        lines.append("  /* spacing scale */")
        for s in tokens["spacing"][:12]:
            key = re.sub(r"[^0-9a-z]", "", s["value"])
            lines.append("  --space-%s: %s;" % (key, s["value"]))
    lines.append("}")
    return "\n".join(lines) + "\n"


def collect_css_files(css_files, css_dirs):
    paths = list(css_files or [])
    for d in (css_dirs or []):
        for root, _, files in os.walk(d):
            if PRUNE.search(root):
                continue
            for fn in files:
                if fn.lower().endswith(".css"):
                    p = os.path.join(root, fn)
                    if not PRUNE.search(p):
                        paths.append(p)
    return list(dict.fromkeys(paths))


def run(css_files, css_dirs):
    colors, fonts, sizes, weights, spacing, radii = {}, {}, {}, {}, {}, {}
    files = collect_css_files(css_files, css_dirs)
    for p in files:
        try:
            c, f, s, w, sp, r = harvest(open(p, encoding="utf-8", errors="replace").read())
        except Exception:
            continue
        for src, dst in ((c, colors), (f, fonts), (s, sizes), (w, weights), (sp, spacing), (r, radii)):
            for k, v in src.items():
                dst[k] = dst.get(k, 0) + v
    tokens = {"sources": files, "colors": ranked(colors), "fontFamilies": ranked(fonts),
              "fontSizes": ranked(sizes), "fontWeights": ranked(weights),
              "spacing": ranked(spacing), "radii": ranked(radii)}
    return tokens


def main():
    ap = argparse.ArgumentParser(description="Harvest a design theme (tokens.json + theme.css) from legacy CSS source.")
    ap.add_argument("--css", action="append", help="A CSS file to include (repeatable).")
    ap.add_argument("--css-dir", action="append", help="A directory to scan recursively for *.css (repeatable).")
    ap.add_argument("--out-dir", help="Write tokens.json + theme.css here. Required for a real run.")
    ap.add_argument("--self-check", action="store_true", help="Run on built-in sample CSS and assert harvest works.")
    args = ap.parse_args()

    if args.self_check:
        sample = """
        /* c */ .panel { color:#006286; background-color:#E6E3E0; font-family:'Frutiger 45 Light',sans-serif;
                 font-size:13px; padding:8px 8px; border-radius:3px; }
        .h { color:#006286; font-size:18px; font-weight:700; margin:4px; }
        a { color: rgba(0,98,134,1); }
        """
        c, f, s, w, sp, r = harvest(sample)
        assert norm_hex("006286") in c and c[norm_hex("006286")] == 2, "color tally wrong: %s" % c
        assert any("Frutiger" in k for k in f), "font miss"
        assert "13px" in s and "18px" in s, "size miss"
        assert "8px" in sp and "4px" in sp, "spacing miss"
        css = build_theme_css({"colors": ranked(c), "fontFamilies": ranked(f), "fontSizes": ranked(s),
                               "spacing": ranked(sp), "radii": ranked(r), "fontWeights": ranked(w)})
        assert "--color-01: #006286;" in css, "theme.css color miss"
        print(json.dumps({"self_check": "ok", "colors": len(c), "fonts": len(f), "sizes": len(s), "spacing": len(sp)}))
        return

    if not args.out_dir:
        raise SystemExit("--out-dir is required (or use --self-check)")
    if not (args.css or args.css_dir):
        raise SystemExit("pass at least one --css or --css-dir")
    tokens = run(args.css, args.css_dir)
    os.makedirs(args.out_dir, exist_ok=True)
    json.dump(tokens, open(os.path.join(args.out_dir, "tokens.json"), "w", encoding="utf-8"), indent=1)
    open(os.path.join(args.out_dir, "theme.css"), "w", encoding="utf-8").write(build_theme_css(tokens))
    print(json.dumps({"ok": True, "out_dir": args.out_dir, "files_scanned": len(tokens["sources"]),
                      "colors": len(tokens["colors"]), "fontFamilies": len(tokens["fontFamilies"]),
                      "fontSizes": len(tokens["fontSizes"])}))


if __name__ == "__main__":
    main()
