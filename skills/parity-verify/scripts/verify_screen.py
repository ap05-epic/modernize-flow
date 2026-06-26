#!/usr/bin/env python3
"""
verify_screen.py — run both parity lanes, fuse them, gate, and emit an ACTIONABLE report.

Inputs: legacy + react model.json and png (all from capture_screen.py, same viewport/fixture).
Pipeline:
  1. dom_diff.build_diff(legacy, react)         -> critical structural deltas + advisory style hints
  2. pixel_diff.js                              -> mismatch ratio + located changed-regions
  3. map each pixel region -> the React element under it (so "where" is concrete)
  4. GATE: PASS iff 0 critical structural deltas AND pixel ratio <= threshold AND no size mismatch
  5. write parity-report.json + parity-report.md + reference side-by-side.png ; exit 0 (pass) / 2 (fail)

The report is written FOR THE BUILDER: it says exactly what differs and where, so the model makes
small targeted edits and re-runs. The model fixes from findings; it does not judge the match.
"""
import argparse, json, os, sys, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dom_diff  # same folder


def overlap_area(a, b):
    ix = max(0, min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]))
    iy = max(0, min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]))
    return ix * iy


def element_under(region, react_model):
    best, best_score = None, 0
    for el in react_model.get("elements", []):
        b = el.get("box") or {}
        if not b or b.get("w", 0) <= 0:
            continue
        ov = overlap_area(region, b)
        if ov <= 0:
            continue
        area = max(1, b["w"] * b["h"])
        score = ov / area  # prefer the smallest element well-covered by the region
        if score > best_score:
            best, best_score = el, score
    if not best:
        return None
    return dom_diff.where(best)


def run_pixel(node, script, legacy_png, react_png, out_dir, name, threshold):
    regions_path = os.path.join(out_dir, name + ".regions.json")
    cmd = [node, script, "--legacy", legacy_png, "--react", react_png,
           "--out-diff", os.path.join(out_dir, name + ".diff.png"),
           "--out-sxs", os.path.join(out_dir, name + ".side-by-side.png"),
           "--out-regions", regions_path, "--threshold", str(threshold)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return json.load(open(regions_path, encoding="utf-8"))
    except FileNotFoundError:
        return {"error": "node not found — install Node and pixelmatch/pngjs (see parity-thresholds.md)"}
    except subprocess.CalledProcessError as e:
        return {"error": "pixel_diff.js failed", "stderr": e.stderr[-800:] if e.stderr else ""}


def build_report_md(name, result):
    g = result["gate"]
    lines = [f"# Parity report — {name}   ·   RESULT: {'PASS ✅' if g['pass'] else 'FAIL ❌'}", ""]
    p = result["pixel"]
    lines.append(f"- pixel mismatch: **{(p.get('ratio') or 0)*100:.3f}%** (threshold {g['pixel_threshold']*100:.3f}%)")
    lines.append(f"- critical structural deltas: **{g['critical_structural']}**")
    if p.get("dimMismatch"):
        lines.append(f"- ⚠️ size mismatch legacy {p['dimMismatch']['legacy']} vs react {p['dimMismatch']['react']} — render the React screen at the legacy viewport.")
    if p.get("error"):
        lines.append(f"- ⚠️ pixel lane error: {p['error']}")
    lines.append(f"- side-by-side: `{name}.side-by-side.png`")
    lines.append("")

    crit = result["dom"]["critical"]
    if crit:
        lines.append("## Critical structural deltas — MUST fix (these fail the gate)")
        for i, d in enumerate(crit, 1):
            w = d.get("where", {})
            loc = w.get("selector") or w.get("table_index") or ""
            lines.append(f"{i}. **{d['type']}** — legacy `{d.get('legacy')}` → react `{d.get('react')}`  @ `{loc}`")
            lines.append(f"   ↳ {d.get('hint','')}")
        lines.append("")

    regs = result["pixel"].get("regions_annotated", [])
    if regs:
        lines.append("## Pixel difference regions (visual, located)")
        for i, r in enumerate(regs, 1):
            near = (r.get("near") or {}).get("selector", "?")
            txt = (r.get("near") or {}).get("text", "")
            lines.append(f"{i}. region x={r['x']} y={r['y']} w={r['w']} h={r['h']} (~{r['changedPixels']}px) near `{near}` {('· “'+txt+'”') if txt else ''}")
            for h in r.get("style_hints", []):
                lines.append(f"   ↳ {h['hint']}")
        lines.append("")

    adv = result["dom"]["advisory"]
    if adv and not regs:
        lines.append("## Advisory style hints")
        for d in adv[:40]:
            lines.append(f"- `{(d.get('where') or {}).get('selector','')}` {d.get('hint','')}")
        lines.append("")

    if g["pass"]:
        lines.append("All gates passed. Mark this screen/state `verified` in STATUS.md.")
    else:
        lines.append("Fix the criticals first (DOM lane), then the located pixel regions (use the style hints), then re-run verify_screen.py.")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Fuse DOM + pixel parity lanes into a gated, actionable report.")
    ap.add_argument("--legacy-model", required=True)
    ap.add_argument("--legacy-png", required=True)
    ap.add_argument("--react-model", required=True)
    ap.add_argument("--react-png", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--name", required=True, help="e.g. f010_default")
    ap.add_argument("--pixel-threshold", type=float, default=0.005, help="max pixel mismatch ratio, default 0.005 (i.e. 0.5 percent).")
    ap.add_argument("--node", default="node")
    ap.add_argument("--pixel-diff", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "pixel_diff.js"))
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    legacy = json.load(open(args.legacy_model, encoding="utf-8"))
    react = json.load(open(args.react_model, encoding="utf-8"))

    dom = dom_diff.build_diff(legacy, react)
    pixel = run_pixel(args.node, args.pixel_diff, args.legacy_png, args.react_png,
                      args.out_dir, args.name, args.pixel_threshold)

    # annotate pixel regions with the react element under them + co-located style hints
    adv = dom["advisory"]
    if isinstance(pixel, dict) and pixel.get("regions"):
        annotated = []
        for r in pixel["regions"]:
            near = element_under(r, react)
            hints = []
            if near:
                sel = near.get("selector")
                hints = [d for d in adv if (d.get("where") or {}).get("selector") == sel]
            annotated.append({**r, "near": near, "style_hints": hints})
        pixel["regions_annotated"] = annotated

    ratio = pixel.get("ratio") if isinstance(pixel, dict) else None
    pixel_ok = (ratio is not None) and (ratio <= args.pixel_threshold) and not pixel.get("dimMismatch") and not pixel.get("error")
    gate = {
        "pass": dom["summary"]["critical"] == 0 and pixel_ok,
        "critical_structural": dom["summary"]["critical"],
        "pixel_ratio": ratio,
        "pixel_threshold": args.pixel_threshold,
        "pixel_ok": bool(pixel_ok),
    }
    result = {"name": args.name, "gate": gate, "dom": dom, "pixel": pixel}
    json.dump(result, open(os.path.join(args.out_dir, args.name + ".parity-report.json"), "w", encoding="utf-8"), indent=1)
    open(os.path.join(args.out_dir, args.name + ".parity-report.md"), "w", encoding="utf-8").write(build_report_md(args.name, result))

    print(json.dumps({"name": args.name, "pass": gate["pass"], "critical_structural": gate["critical_structural"],
                      "pixel_ratio": ratio, "report": os.path.join(args.out_dir, args.name + ".parity-report.md")}, indent=1))
    sys.exit(0 if gate["pass"] else 2)


if __name__ == "__main__":
    main()
