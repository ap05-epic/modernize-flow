#!/usr/bin/env python3
"""
serve_review.py — browse legacy-vs-React side by side with the parity verdict.

Reads the parity reports already produced by parity-verify and serves a single page that, per screen,
shows: PASS/FAIL + pixel% + critical count, the side-by-side.png (legacy | react | diff), a link to the
full report, and (optionally) a live iframe to the running React app.

Usage:
  python scripts/serve_review.py --work-dir work --react-base-url http://localhost:5173 --port 8800
Then open http://localhost:8800
Stdlib only.
"""
import argparse, json, glob, os, html, functools
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler


def collect(work_dir):
    rows = []
    for rep in sorted(glob.glob(os.path.join(work_dir, "parity", "*.parity-report.json"))):
        try:
            d = json.load(open(rep, encoding="utf-8"))
        except Exception:
            continue
        name = d.get("name") or os.path.basename(rep).split(".")[0]
        g = d.get("gate", {})
        rows.append({
            "name": name,
            "pass": bool(g.get("pass")),
            "ratio": g.get("pixel_ratio"),
            "critical": g.get("critical_structural"),
            "sxs": f"parity/{name}.side-by-side.png",
            "legacy": f"screenshots/{name}.png",
            "report": f"parity/{name}.parity-report.md",
        })
    return rows


def render(rows, react_base):
    passed = sum(1 for r in rows if r["pass"])
    cards = []
    for r in rows:
        badge = "✅ PASS" if r["pass"] else "❌ FAIL"
        color = "#137333" if r["pass"] else "#c5221f"
        ratio = f"{(r['ratio'] or 0)*100:.3f}%" if r["ratio"] is not None else "n/a"
        live = (f'<iframe src="{html.escape(react_base)}#/{html.escape(r["name"])}" '
                f'width="480" height="300" style="border:1px solid #ccc"></iframe>') if react_base else ""
        cards.append(f"""
        <section style="margin:24px 0;border-top:1px solid #eee;padding-top:16px">
          <h2 style="font:600 16px sans-serif">{html.escape(r['name'])}
            <span style="color:{color}">{badge}</span>
            <small style="color:#555;font-weight:400">· pixel {ratio} · critical {r['critical']}</small>
            <a href="{r['report']}" style="font-size:12px;margin-left:8px">report.md</a>
          </h2>
          <p style="font:12px sans-serif;color:#777">legend: legacy | react | diff</p>
          <img src="{r['sxs']}" style="max-width:100%;border:1px solid #ddd"
               onerror="this.replaceWith(Object.assign(document.createElement('em'),{{textContent:'no side-by-side.png yet — run verify_screen.py'}}))"/>
          {live}
        </section>""")
    return f"""<!doctype html><meta charset="utf-8"><title>jsp2react review</title>
    <body style="max-width:1100px;margin:24px auto;font-family:sans-serif">
    <h1>jsp2react — side-by-side review</h1>
    <p>{passed}/{len(rows)} screens verified. React app: {html.escape(react_base) or '(not provided)'}</p>
    {''.join(cards) or '<p>No parity reports found under work/parity/. Run verify_screen.py first.</p>'}
    </body>"""


def main():
    ap = argparse.ArgumentParser(description="Serve a legacy-vs-React side-by-side review page.")
    ap.add_argument("--work-dir", required=True, help="Evidence root (contains screenshots/ and parity/).")
    ap.add_argument("--react-base-url", default="", help="Running React dev server (optional live iframe).")
    ap.add_argument("--port", type=int, default=8800)
    args = ap.parse_args()

    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/", "/index.html"):
                body = render(collect(args.work_dir), args.react_base_url).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                super().do_GET()

    handler = functools.partial(Handler, directory=args.work_dir)
    print(f"review server on http://localhost:{args.port}  (serving {args.work_dir})")
    ThreadingHTTPServer(("0.0.0.0", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
