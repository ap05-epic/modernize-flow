#!/usr/bin/env python3
"""
crawl_screens.py — discover the legacy screen graph (deterministic-first).

Two layers:
  1. STATIC (authoritative, no browser): parse struts-config.xml action mappings + forwards,
     scan the webapp dir for JSPs, categorize them, and harvest *.do / *.jsp links found in markup.
     This yields the complete action/JSP inventory to reconcile against (the "did we miss a screen?"
     gate the team's baa-analysis enforces).
  2. RUNTIME (optional): BFS from a start URL clicking/visiting reachable links, recording which
     routes actually render. Stateful Struts apps need live menu traversal the analyzer drives by
     hand; this just harvests the easy reachable set.

Output: screens.json  { actions[], jsps[], links[], families{}, reconciliation{} }
The analyzer turns this into status.md §4 rows and spec.md Section 3/4.
"""
import argparse, json, os, re, sys, xml.etree.ElementTree as ET

PRUNE_DIRS = {"pdfjs", "dojo", "node_modules", "coverage", "target", "dist", "build", ".git",
              "lib", "locale", "cmaps", ".vscode"}
PRUNE_RE = re.compile(r"(jquery|lodash|d3|clusterize|dataTables)", re.I)

# App taxonomy is NOT hardcoded. FAMILIES (explicit list) and PATH_CONVENTIONS (category -> path substrings)
# come from project.json at runtime; when families is "auto"/empty the family is INFERRED from the source
# structure (the jsp subdir / the struts action package). See main().
FAMILIES = []            # e.g. ["fa","cefs",...]  from project.families (or [] => auto-infer)
PATH_CONVENTIONS = {}    # e.g. {"alt-root":["/pjsp/"], "contentlet":["/jsp/contentlet/"]} from project.pathConventions

SAMPLE_STRUTS = """<struts-config><action-mappings>
  <action path="/orderlist" type="com.example.app.struts.action.orders.OrderListAction" name="orderForm">
    <forward name="success" path="/jsp/orders/orderlist.jsp"/>
    <forward name="error" path="/jsp/error.jsp"/>
  </action>
  <action path="/login" type="com.example.app.struts.action.LoginAction">
    <forward name="success" path="/jsp/summary.jsp"/>
  </action>
</action-mappings></struts-config>"""


def infer_family(path):
    s = path.lower()
    if FAMILIES:                              # explicit taxonomy from project.json
        for f in FAMILIES:
            f = f.lower()
            if "/" + f in s or s.startswith(f) or "." + f + "." in s or "/" + f + "/" in s:
                return f
    # auto-infer from structure (generic): shell screens, then jsp subdir, then action package segment
    if any(w in s for w in ("login", "summary", "home", "dashboard", "index")):
        return "shell"
    m = re.search(r"/jsp/([a-z0-9_]+)/", s) or re.search(r"\.action\.([a-z0-9_]+)\.", s)
    return m.group(1) if m else "other"


def parse_struts(xml_text):
    """Return list of actions: {path, action_do, type, name, forwards:{name->jsp}, family}."""
    actions = []
    # strip DOCTYPE (DTD fetch would fail offline)
    xml_text = re.sub(r"<!DOCTYPE[^>]*>", "", xml_text, flags=re.S)
    root = ET.fromstring(xml_text)
    for am in root.iter("action-mappings"):
        for a in am.findall("action"):
            path = a.get("path", "")
            fwds = {}
            for f in a.findall("forward"):
                fwds[f.get("name", "")] = f.get("path", "")
            actions.append({
                "path": path, "action_do": (path.lstrip("/") + ".do") if path else "",
                "type": a.get("type", ""), "name": a.get("name", ""),
                "forwards": fwds, "family": infer_family(a.get("type", "") or path),
            })
    return actions


def categorize_jsp(rel):
    s = "/" + rel.lower().lstrip("/")                # normalize leading slash so "/jsp/x/" conventions match rel paths
    for cat, subs in PATH_CONVENTIONS.items():       # project-defined path conventions (e.g. alt-root/contentlet/ipad)
        for sub in subs:
            if str(sub).lower() in s:
                return cat
    if "/layouts/" in s or "layout" in os.path.basename(s):
        return "layout"
    if rel.endswith((".jspf", ".tag")) or "/inc/" in s or "fragment" in s:
        return "fragment"
    return "screen"


LINK_RE = re.compile(r"""(?:href|action|src|data-url)\s*=\s*['"]([^'"]*?\.(?:do|jsp)(?:\?[^'"]*)?)['"]""", re.I)
ONCLICK_RE = re.compile(r"""(?:location\.href|window\.open|\.load)\s*\(\s*['"]([^'"]*?\.(?:do|jsp)[^'"]*)['"]""", re.I)


def scan_webapp(webapp_dir):
    jsps, links = [], set()
    for dp, dns, fns in os.walk(webapp_dir):
        dns[:] = [d for d in dns if d not in PRUNE_DIRS and not PRUNE_RE.search(d)]
        for fn in fns:
            if not fn.lower().endswith((".jsp", ".jspf", ".jspx", ".tag", ".html")):
                continue
            full = os.path.join(dp, fn)
            rel = os.path.relpath(full, webapp_dir).replace("\\", "/")
            jsps.append({"path": rel, "type": categorize_jsp(rel), "family": infer_family(rel)})
            try:
                txt = open(full, encoding="utf-8", errors="replace").read()
            except Exception:
                continue
            for m in LINK_RE.findall(txt):
                links.add(m.strip())
            for m in ONCLICK_RE.findall(txt):
                links.add(m.strip())
    return jsps, sorted(links)


def runtime_harvest(start_url, auth_state, max_pages, viewport):
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print(f"[runtime skipped] Playwright unavailable: {e}", file=sys.stderr)
        return []
    w, h = (int(x) for x in viewport.lower().split("x"))
    seen, order, queue = set(), [], [start_url]
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": w, "height": h},
                            **({"storage_state": auth_state} if auth_state else {}))
        pg = ctx.new_page()
        while queue and len(order) < max_pages:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            try:
                pg.goto(url, wait_until="networkidle", timeout=30000)
            except Exception as e:
                order.append({"url": url, "ok": False, "error": str(e)[:120]}); continue
            order.append({"url": pg.url, "ok": True, "title": pg.title()})
            hrefs = pg.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            for hh in hrefs:
                if re.search(r"\.(do|jsp)(\?|$)", hh) and hh not in seen and not PRUNE_RE.search(hh):
                    queue.append(hh)
        b.close()
    return order


def main():
    ap = argparse.ArgumentParser(description="Discover the legacy screen graph (struts-config + JSP scan, optional runtime BFS).")
    ap.add_argument("--struts-config", nargs="*", default=[], help="One or more struts-config*.xml paths.")
    ap.add_argument("--webapp-dir", help="Legacy webapp dir to scan for JSPs/links.")
    ap.add_argument("--out", default="screens.json", help="Output JSON path.")
    ap.add_argument("--emit-viewgraph", help="Also write a viewgraph.json of the static routes (folds into crawl_ajax.py --merge for one reconciled inventory).")
    ap.add_argument("--runtime-url", help="Optional: start URL for a live BFS link harvest.")
    ap.add_argument("--auth-state", help="storage_state json for the runtime harvest.")
    ap.add_argument("--max-pages", type=int, default=60, help="Runtime BFS page cap.")
    ap.add_argument("--viewport", default="1920x1080")
    ap.add_argument("--project", help="project.json — supplies families (taxonomy) + pathConventions; both auto-infer if omitted.")
    ap.add_argument("--self-check", action="store_true", help="Parse an embedded struts-config sample and exit.")
    args = ap.parse_args()

    # load the app taxonomy from project.json (families=='auto'/absent => infer from structure)
    if getattr(args, "project", None):
        try:
            _p = json.load(open(args.project, encoding="utf-8"))
            _fam = _p.get("families")
            if isinstance(_fam, list):
                FAMILIES[:] = _fam
            PATH_CONVENTIONS.clear()
            PATH_CONVENTIONS.update(_p.get("pathConventions") or {})
        except Exception:
            pass

    if args.self_check:
        acts = parse_struts(SAMPLE_STRUTS)
        assert len(acts) == 2 and acts[0]["action_do"] == "orderlist.do", acts
        assert acts[0]["forwards"]["success"] == "/jsp/orders/orderlist.jsp"
        assert acts[0]["family"] == "orders", "auto-infer from action package failed: %s" % acts[0]["family"]
        assert acts[1]["family"] == "shell", "login should infer shell: %s" % acts[1]["family"]
        print(json.dumps({"self_check": "ok", "actions_parsed": len(acts), "sample": acts[0]}, indent=1))
        return

    actions = []
    for cfg in args.struts_config:
        try:
            actions += parse_struts(open(cfg, encoding="utf-8", errors="replace").read())
        except Exception as e:
            print(f"[warn] could not parse {cfg}: {e}", file=sys.stderr)

    jsps, links = ([], [])
    if args.webapp_dir:
        jsps, links = scan_webapp(args.webapp_dir)

    runtime = runtime_harvest(args.runtime_url, args.auth_state, args.max_pages, args.viewport) if args.runtime_url else []

    fams = {}
    for a in actions:
        fams.setdefault(a["family"], {"actions": 0, "screen_jsps": 0})["actions"] += 1
    for j in jsps:
        if j["type"] == "screen":
            fams.setdefault(j["family"], {"actions": 0, "screen_jsps": 0})["screen_jsps"] += 1

    out = {
        "actions": actions,
        "jsps": jsps,
        "links": links,
        "runtime": runtime,
        "families": fams,
        "reconciliation": {
            "action_count": len(actions),
            "jsp_count": len(jsps),
            "screen_jsp_count": sum(1 for j in jsps if j["type"] == "screen"),
            "fragment_count": sum(1 for j in jsps if j["type"] == "fragment"),
            "note": "Every screen JSP / action should map to a status.md row or an explicit unmatched entry in spec.md Section 4.",
        },
    }
    json.dump(out, open(args.out, "w", encoding="utf-8"), indent=1)

    if args.emit_viewgraph:
        # static routes as viewgraph states (domSignature 'static:<route>' so they never collide with
        # the AJAX crawler's DOM-hash sigs — purely additive when reconciled via crawl_ajax.py --merge).
        states = []
        for a in actions:
            route = a.get("action_do", "")
            states.append({"id": "s_" + route, "domSignature": "static:" + route,
                           "clickPathFromStart": [{"action": "navigate", "url": route}],
                           "triggeredEndpoints": [], "isError": False, "label": route,
                           "family": a.get("family", ""), "jsp": a.get("forwards", {}).get("success", "")})
        json.dump({"start_url": args.runtime_url or "", "count": len(states), "errors": 0,
                   "states": states, "source": "crawl_screens.py (static)"},
                  open(args.emit_viewgraph, "w", encoding="utf-8"), indent=1)

    print(json.dumps({"ok": True, "out": args.out, **out["reconciliation"], "families": fams,
                      "viewgraph": args.emit_viewgraph or None}, indent=1))


if __name__ == "__main__":
    main()
