#!/usr/bin/env python3
"""
build_index.py — turn MANIFEST.json into a navigable evidence/INDEX.html.

v1 scattered each screen's files across screenshots/ dom/ fixtures/ parity/, so a human could not
follow what the agent produced. v2 uses one folder per view; this generates a single human entry
point: a grouped, thumbnailed table of every view with its status, data-mode, parity result, and
links to every artifact (and any quarantined error captures). Open evidence/INDEX.html in a browser.

Reads the per-view MANIFEST schema (see templates/MANIFEST.json):
  views[]: {id, screen, family, state, folder, data_mode, status, usable, isError,
            files{screenshot,dom,model,sourceModel,navPath,har,capture},
            parity{report,sideBySide,pass,pixel,criticalDeltas}, rejected[]}

Usage:
  python build_index.py --manifest evidence/MANIFEST.json [--out evidence/INDEX.html]
  python build_index.py --self-check
"""
import argparse, json, os, html

STATUS_COLOR = {"verified": "#1a7f37", "implemented": "#9a6700", "analyzed": "#0969da",
                "blocked": "#cf222e", "not-started": "#6e7781"}


def esc(s):
    return html.escape(str(s if s is not None else ""))


def rel(folder, name):
    return esc((folder.rstrip("/") + "/" + name) if name else "")


def view_row(v):
    folder = v.get("folder", v.get("id", ""))
    files = v.get("files", {})
    parity = v.get("parity", {})
    thumb_src = rel(folder, parity.get("sideBySide") or files.get("screenshot", ""))
    status = v.get("status", "analyzed")
    badge = '<span style="background:%s">%s</span>' % (STATUS_COLOR.get(status, "#6e7781"), esc(status))
    flags = []
    if v.get("isError"):
        flags.append('<span class="flag err">ERROR PAGE</span>')
    if v.get("usable") is False:
        flags.append('<span class="flag warn">not usable</span>')
    if v.get("rejected"):
        flags.append('<span class="flag warn">%d quarantined</span>' % len(v["rejected"]))
    if parity:
        ok = parity.get("pass")
        flags.append('<span class="flag %s">parity %s</span>' % ("ok" if ok else "err",
                     ("PASS" if ok else "FAIL")))
        if parity.get("pixel") is not None:
            flags.append('<span class="muted">pixel %s · crit %s</span>' %
                         (esc(parity.get("pixel")), esc(parity.get("criticalDeltas", "?"))))

    links = []
    for label, key in (("shot", "screenshot"), ("dom", "dom"), ("model", "model"),
                       ("source", "sourceModel"), ("nav", "navPath"), ("har", "har"), ("meta", "capture")):
        if files.get(key):
            links.append('<a href="%s">%s</a>' % (rel(folder, files[key]), label))
    if parity.get("report"):
        links.append('<a href="%s">parity report</a>' % rel(folder, parity["report"]))
    for rj in v.get("rejected", []):
        links.append('<a class="rej" href="%s">rejected</a>' % rel(folder, rj))

    thumb = ('<a href="%s"><img loading="lazy" src="%s"></a>' % (thumb_src, thumb_src)) if thumb_src else "—"
    return ("<tr>"
            '<td class="thumb">%s</td>'
            '<td><b>%s</b><div class="muted">%s · %s</div>'
            '<div class="muted">data: %s</div></td>'
            '<td>%s<div class="flags">%s</div></td>'
            '<td class="links">%s</td>'
            "</tr>") % (
        thumb, esc(v.get("screen", v.get("id", ""))), esc(v.get("id", "")), esc(v.get("state", "")),
        esc(v.get("data_mode", "—")), badge, " ".join(flags), " ".join(links))


def build_html(manifest):
    views = manifest.get("views", [])
    fams = {}
    for v in views:
        fams.setdefault(v.get("family", "other"), []).append(v)
    total = len(views)
    verified = sum(1 for v in views if v.get("status") == "verified")
    errors = sum(1 for v in views if v.get("isError"))
    sections = []
    for fam in sorted(fams):
        rows = "\n".join(view_row(v) for v in fams[fam])
        sections.append('<h2>%s <span class="muted">(%d)</span></h2><table>'
                        "<thead><tr><th>preview</th><th>view</th><th>status</th><th>artifacts</th></tr></thead>"
                        "<tbody>%s</tbody></table>" % (esc(fam), len(fams[fam]), rows))
    css = """
    body{font:13px/1.4 -apple-system,Segoe UI,Arial,sans-serif;margin:24px;color:#1f2328}
    h1{margin:0 0 4px} .sum{color:#57606a;margin-bottom:20px}
    h2{margin:28px 0 8px;border-bottom:1px solid #d0d7de;padding-bottom:4px}
    table{border-collapse:collapse;width:100%;margin-bottom:8px}
    th,td{border:1px solid #d0d7de;padding:6px 8px;text-align:left;vertical-align:top}
    th{background:#f6f8fa}
    .thumb img{max-width:240px;max-height:150px;border:1px solid #d0d7de;display:block}
    .muted{color:#57606a;font-size:12px} .links a{margin-right:8px;white-space:nowrap}
    .links a.rej,.flag.err{color:#cf222e} .links a.rej{font-weight:bold}
    span[style*=background]{color:#fff;padding:1px 6px;border-radius:6px;font-size:11px}
    .flags{margin-top:4px} .flag{padding:1px 6px;border-radius:6px;font-size:11px;margin-right:4px}
    .flag.ok{background:#dafbe1;color:#1a7f37} .flag.err{background:#ffebe9} .flag.warn{background:#fff8c5;color:#9a6700}
    """
    return ("<!doctype html><html><head><meta charset='utf-8'><title>jsp2react evidence</title>"
            "<style>%s</style></head><body>"
            "<h1>jsp2react — evidence index</h1>"
            "<div class='sum'>%d views · %d verified · %d error-pages · generated from MANIFEST.json</div>"
            "%s</body></html>") % (css, total, verified, errors, "\n".join(sections))


def main():
    ap = argparse.ArgumentParser(description="Generate evidence/INDEX.html from MANIFEST.json")
    ap.add_argument("--manifest", help="Path to MANIFEST.json. Required for a real run.")
    ap.add_argument("--out", help="Output HTML path (default: <manifest dir>/INDEX.html).")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()

    if args.self_check:
        sample = {"views": [
            {"id": "f000_login", "screen": "Login", "family": "shell", "state": "default", "folder": "f000_login",
             "data_mode": "live", "status": "verified", "usable": True, "isError": False,
             "files": {"screenshot": "screenshot.png", "model": "model.json", "sourceModel": "source-model.json"},
             "parity": {"report": "parity/report.md", "sideBySide": "parity/side-by-side.png", "pass": True,
                        "pixel": 0.002, "criticalDeltas": 0}},
            {"id": "f010_err", "screen": "FA Summary", "family": "fa", "state": "default", "folder": "f010_err",
             "data_mode": "record", "status": "blocked", "usable": False, "isError": True,
             "files": {"screenshot": "screenshot.png"}, "rejected": ["_rejected/a.png"]},
        ]}
        out = build_html(sample)
        assert "f000_login" in out and "FA Summary" in out, "rows missing"
        assert "ERROR PAGE" in out and "quarantined" in out, "error flags missing"
        assert "parity PASS" in out and "source-model.json" in out, "links/flags missing"
        assert "shell" in out and "fa" in out, "family grouping missing"
        print(json.dumps({"self_check": "ok", "html_bytes": len(out)}))
        return

    if not args.manifest:
        raise SystemExit("--manifest is required (or use --self-check)")
    manifest = json.load(open(args.manifest, encoding="utf-8"))
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.manifest)), "INDEX.html")
    open(out, "w", encoding="utf-8").write(build_html(manifest))
    print(json.dumps({"ok": True, "out": out, "views": len(manifest.get("views", []))}))


if __name__ == "__main__":
    main()
