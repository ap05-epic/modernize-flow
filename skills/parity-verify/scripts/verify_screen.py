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


def data_presence(legacy, react):
    """Did the React side actually render the data? Catches 'data missing/empty' regardless of mode."""
    le, re_ = len(legacy.get("elements", [])), len(react.get("elements", []))
    lrows = sum(t.get("rowCount", 0) for t in legacy.get("tables", []))
    rrows = sum(t.get("rowCount", 0) for t in react.get("tables", []))
    ratio = (re_ / le) if le else 1.0
    reasons = []
    if le and ratio < 0.5:
        reasons.append("react rendered %d of legacy's %d elements (%.0f%%) — content likely missing" % (re_, le, ratio * 100))
    if lrows > 0 and rrows == 0:
        reasons.append("legacy tables have %d rows but react tables are empty — data not wired/rendered" % lrows)
    return {"ok": not reasons, "legacy_elements": le, "react_elements": re_, "element_ratio": round(ratio, 3),
            "legacy_rows": lrows, "react_rows": rrows, "reasons": reasons}


def compute_gate(dom, data, ratio, size_ok, threshold, mode):
    """Fuse the lanes into the pass/fail decision. record mode gates on exact pixels; live mode treats pixels
    as advisory and gates on structure + data-presence + comparable size."""
    pixel_ok = (ratio is not None) and (ratio <= threshold) and size_ok
    pixel_gates = pixel_ok if mode == "record" else size_ok
    return {
        "pass": dom["summary"]["critical"] == 0 and data["ok"] and pixel_gates,
        "data_mode": mode,
        "critical_structural": dom["summary"]["critical"],
        "data_present": data["ok"],
        "pixel_ratio": ratio,
        "pixel_threshold": threshold,
        "pixel_ok": bool(pixel_ok),
        "pixel_gated": mode == "record",
    }


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
    d = result.get("data", {})
    lines.append(f"- data mode: **{g.get('data_mode','record')}** "
                 f"({'pixel GATED — exact' if g.get('pixel_gated') else 'pixel ADVISORY — live data drifts; gating on structure/style/data'})")
    px_tag = "" if g.get("pixel_gated") else "  _(advisory in live mode)_"
    lines.append(f"- pixel mismatch: **{(p.get('ratio') or 0)*100:.3f}%** (threshold {g['pixel_threshold']*100:.3f}%){px_tag}")
    lines.append(f"- critical structural deltas: **{g['critical_structural']}**")
    lines.append(f"- data present: **{'yes' if d.get('ok', True) else 'NO'}** "
                 f"(react {d.get('react_elements','?')}/{d.get('legacy_elements','?')} elements, "
                 f"rows {d.get('react_rows','?')}/{d.get('legacy_rows','?')})")
    for r in d.get("reasons", []):
        lines.append(f"  - ⚠️ {r}")
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
        lines.append("All gates passed. Mark this screen/state `verified` in status.md.")
    else:
        lines.append("Fix the criticals first (DOM lane), then the located pixel regions (use the style hints), then re-run verify_screen.py.")
    return "\n".join(lines) + "\n"


def self_check():
    """Exercise the gate fusion (compute_gate over the real dom_diff + data_presence lanes) without a browser."""
    def model(text="Account #", rows=3):
        return {"title": "x", "elements": [{"i": 0, "tag": "label", "text": text, "box": {}, "style": {}, "path": "0/0"}],
                "tables": [{"index": 0, "rowCount": rows, "headers": ["A", "B"]}], "forms": []}
    legacy = model()
    # identical + clean pixels -> PASS
    g = compute_gate(dom_diff.build_diff(legacy, model()), data_presence(legacy, model()), 0.0, True, 0.005, "record")
    assert g["pass"], g
    # text mismatch -> critical DOM delta -> FAIL
    g2 = compute_gate(dom_diff.build_diff(legacy, model("Acct #")), data_presence(legacy, model("Acct #")), 0.0, True, 0.005, "record")
    assert not g2["pass"] and g2["critical_structural"] > 0, g2
    # legacy has rows, react empty -> data-presence FAIL
    g3 = compute_gate(dom_diff.build_diff(legacy, model(rows=0)), data_presence(legacy, model(rows=0)), 0.0, True, 0.005, "record")
    assert not g3["pass"] and not g3["data_present"], g3
    # record mode gates pixels: over threshold -> FAIL ; live mode tolerates the same drift -> PASS
    g4 = compute_gate(dom_diff.build_diff(legacy, model()), data_presence(legacy, model()), 0.2, True, 0.005, "record")
    g5 = compute_gate(dom_diff.build_diff(legacy, model()), data_presence(legacy, model()), 0.2, True, 0.005, "live")
    assert not g4["pass"] and g5["pass"], (g4, g5)
    print(json.dumps({"self_check": "ok", "pass_identical": g["pass"], "fail_text_mismatch": not g2["pass"],
                      "fail_empty_data": not g3["pass"], "record_gates_pixels": not g4["pass"], "live_tolerates": g5["pass"]}))


def main():
    ap = argparse.ArgumentParser(description="Fuse DOM + pixel parity lanes into a gated, actionable report.")
    if "--self-check" in sys.argv:
        return self_check()
    ap.add_argument("--legacy-model", required=True)
    ap.add_argument("--legacy-png", required=True)
    ap.add_argument("--react-model", required=True)
    ap.add_argument("--react-png", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--name", required=True, help="e.g. f010_default")
    ap.add_argument("--pixel-threshold", type=float, default=0.005, help="max pixel mismatch ratio, default 0.005 (i.e. 0.5 percent).")
    ap.add_argument("--data-mode", choices=["record", "live"], default="record",
                    help="record: data is the SAME recorded responses -> pixel parity is GATED (exact). "
                         "live: data is real-time and drifts -> pixel is advisory, gate on structure+style+data-presence.")
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

    data = data_presence(legacy, react)
    ratio = pixel.get("ratio") if isinstance(pixel, dict) else None
    size_ok = isinstance(pixel, dict) and not pixel.get("dimMismatch") and not pixel.get("error")
    gate = compute_gate(dom, data, ratio, size_ok, args.pixel_threshold, args.data_mode)
    result = {"name": args.name, "gate": gate, "dom": dom, "pixel": pixel, "data": data}
    json.dump(result, open(os.path.join(args.out_dir, args.name + ".parity-report.json"), "w", encoding="utf-8"), indent=1)
    open(os.path.join(args.out_dir, args.name + ".parity-report.md"), "w", encoding="utf-8").write(build_report_md(args.name, result))

    print(json.dumps({"name": args.name, "pass": gate["pass"], "data_mode": args.data_mode,
                      "critical_structural": gate["critical_structural"], "data_present": data["ok"],
                      "pixel_ratio": ratio, "report": os.path.join(args.out_dir, args.name + ".parity-report.md")}, indent=1))
    sys.exit(0 if gate["pass"] else 2)


if __name__ == "__main__":
    main()
