#!/usr/bin/env python3
"""
capture_screen.py — capture ONE screen state as comparable evidence.

This is the single capture path used for BOTH the legacy screen and the React render,
so the two sides are always normalized identically and can be diffed deterministically.

Outputs (in --out-dir, prefixed by --name):
  <name>.png            screenshot at the exact viewport
  <name>.dom.html       raw page.content() (debug / reference)
  <name>.model.json     NORMALIZED structural model (the artifact parity-verify diffs)
  <name>.a11y.json      accessibility snapshot
  <name>.network.json   document/xhr/fetch responses (bodies for json/text, size-capped)

The .model.json schema is the contract consumed by parity-verify/dom_diff.py. Capturing the
legacy page and the React page with THIS script guarantees both models are shaped the same.

Requires Playwright (already on the pod via the webapp-testing skill):  pip install playwright ; playwright install chromium
"""
import argparse, json, sys, os, hashlib, datetime

# Curated computed-style properties — the ones that matter for 1:1 visual/structural parity.
STYLE_PROPS = [
    "display", "position", "visibility", "box-sizing",
    "font-family", "font-size", "font-weight", "font-style", "line-height", "letter-spacing",
    "text-align", "text-transform", "text-decoration-line", "white-space",
    "color", "background-color", "opacity",
    "border-top-width", "border-right-width", "border-bottom-width", "border-left-width",
    "border-top-style", "border-top-color", "border-radius",
    "margin-top", "margin-right", "margin-bottom", "margin-left",
    "padding-top", "padding-right", "padding-bottom", "padding-left",
    "width", "height", "min-width", "min-height",
]

# In-page extractor. Returns a JSON-serializable normalized model. Runs in BOTH legacy and react pages.
EXTRACTOR_JS = r"""
(STYLE_PROPS) => {
  const SKIP = new Set(["SCRIPT","STYLE","NOSCRIPT","META","LINK","HEAD","TEMPLATE"]);
  const out = { title: document.title, url: location.href,
                viewport: {w: window.innerWidth, h: window.innerHeight},
                elements: [], tables: [], forms: [] };

  function visible(el){
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden" || parseFloat(cs.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return false;
    return true;
  }
  function ownText(el){
    let t = "";
    for (const n of el.childNodes) if (n.nodeType === 3) t += n.nodeValue;
    return t.replace(/\s+/g, " ").trim().slice(0, 400);
  }
  function accName(el){
    return (el.getAttribute("aria-label") || el.getAttribute("title") || el.getAttribute("alt") || "").trim().slice(0,200);
  }
  function styleOf(el){
    const cs = getComputedStyle(el); const o = {};
    for (const p of STYLE_PROPS){ o[p] = cs.getPropertyValue(p); }
    return o;
  }

  // depth-first walk; path = stable child-index chain (e.g. "0/2/1"), idx = DOM order
  let idx = 0;
  function walk2(el, path){
    if (!el || el.nodeType !== 1 || SKIP.has(el.tagName) || !visible(el)) return;
    const r = el.getBoundingClientRect();
    const cls = (typeof el.className === "string") ? el.className : (el.getAttribute("class") || "");
    const rec = { i: idx++, path, tag: el.tagName.toLowerCase(), id: el.id || "", classes: cls.trim(),
      role: el.getAttribute("role") || "", name: accName(el), text: ownText(el),
      box: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
      style: styleOf(el), tabindex: el.getAttribute("tabindex"),
      href: el.tagName === "A" ? (el.getAttribute("href") || "") : null, input: null };
    const tag = el.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || tag === "BUTTON"){
      rec.input = { name: el.getAttribute("name") || "", type: (el.getAttribute("type") || tag.toLowerCase()),
        placeholder: el.getAttribute("placeholder") || "", value: (el.value !== undefined ? String(el.value).slice(0,200) : ""),
        disabled: !!el.disabled, required: !!el.required };
      if (tag === "SELECT") rec.input.options = Array.from(el.options).map(o => (o.text||"").trim()).slice(0,200);
    }
    out.elements.push(rec);
    let ci = 0;
    for (const c of el.children){ walk2(c, path + "/" + ci); ci++; }
  }
  walk2(document.body, "0");

  // tables: ordered column headers + row count (column order is a parity-critical signal)
  for (const t of document.querySelectorAll("table")){
    if (!visible(t)) continue;
    const headers = Array.from(t.querySelectorAll("thead th, thead td"))
                      .map(h => ownText(h)).filter(x => x.length);
    const rows = t.querySelectorAll("tbody tr").length;
    out.tables.push({ headers, rowCount: rows });
  }
  // forms: field order + labels (validation/labelling parity)
  for (const f of document.querySelectorAll("form")){
    const fields = [];
    let order = 0;
    for (const el of f.querySelectorAll("input,select,textarea,button")){
      let label = "";
      if (el.id){ const l = f.querySelector('label[for="'+el.id+'"]'); if (l) label = ownText(l); }
      fields.push({ order: order++, name: el.getAttribute("name")||"", type: el.getAttribute("type")||el.tagName.toLowerCase(), label });
    }
    out.forms.push({ action: f.getAttribute("action")||"", method: (f.getAttribute("method")||"get").toLowerCase(), fields });
  }
  return out;
}
"""


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_viewport(s):
    w, h = s.lower().split("x")
    return {"width": int(w), "height": int(h)}


def run_workflow(page, steps):
    """Navigate to a deep state before capture. Action vocabulary mirrors webapp-snapshot."""
    for st in steps:
        a = st.get("action")
        if a == "navigate":
            page.goto(st["url"], wait_until="networkidle")
        elif a == "click":
            page.click(st["selector"])
        elif a == "fill":
            page.fill(st["selector"], st.get("value", ""))
        elif a == "select":
            page.select_option(st["selector"], st.get("value"))
        elif a == "wait":
            if "selector" in st:
                page.wait_for_selector(st["selector"], timeout=st.get("timeout", 30000))
            else:
                page.wait_for_timeout(st.get("ms", 1000))
        else:
            raise SystemExit(f"unknown workflow action: {a!r}")


def main():
    ap = argparse.ArgumentParser(description="Capture one screen state as comparable evidence (png + normalized model + a11y + network).")
    ap.add_argument("--url", required=True, help="URL to capture (legacy screen OR react render).")
    ap.add_argument("--out-dir", required=True, help="Directory for output artifacts.")
    ap.add_argument("--name", required=True, help="Base name, e.g. f010_default.")
    ap.add_argument("--auth-state", help="Playwright storage_state json (login reuse; from save_auth_state.py).")
    ap.add_argument("--viewport", default="1920x1080", help="WIDTHxHEIGHT; use the SAME value for legacy and react.")
    ap.add_argument("--wait-for", help="CSS selector to wait for before capture.")
    ap.add_argument("--wait-ms", type=int, default=0, help="Extra settle wait after networkidle (hydration).")
    ap.add_argument("--workflow", help="JSON file: list of navigate/click/fill/select/wait steps to reach a deep state before capture.")
    ap.add_argument("--full-page", action="store_true", help="Full scrollable page (default: viewport only, recommended for parity).")
    ap.add_argument("--body-cap", type=int, default=500_000, help="Max response body bytes stored per request.")
    ap.add_argument("--self-check", action="store_true", help="Validate environment/args without launching a browser, then exit.")
    args = ap.parse_args()

    vp = parse_viewport(args.viewport)
    os.makedirs(args.out_dir, exist_ok=True)
    base = os.path.join(args.out_dir, args.name)

    if args.self_check:
        try:
            import playwright  # noqa
            ok = True
        except Exception:
            ok = False
        print(json.dumps({"self_check": "ok", "viewport": vp, "out_base": base, "playwright_importable": ok}))
        return

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise SystemExit(f"Playwright not available ({e}). On the pod: pip install playwright && playwright install chromium")

    steps = json.load(open(args.workflow)) if args.workflow else None
    network = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx_kwargs = {"viewport": vp, "device_scale_factor": 1}
        if args.auth_state:
            ctx_kwargs["storage_state"] = args.auth_state
        ctx = browser.new_context(**ctx_kwargs)
        page = ctx.new_page()

        def on_response(resp):
            try:
                rt = resp.request.resource_type
                if rt not in ("document", "xhr", "fetch"):
                    return
                rec = {"method": resp.request.method, "url": resp.url, "status": resp.status,
                       "resource_type": rt, "content_type": resp.headers.get("content-type", "")}
                ct = rec["content_type"]
                if ("json" in ct) or ("text" in ct) or ("xml" in ct):
                    body = resp.body()
                    if body and len(body) <= args.body_cap:
                        rec["body"] = body.decode("utf-8", "replace")
                network.append(rec)
            except Exception:
                pass  # opaque/redirected responses can't be read; skip quietly

        page.on("response", on_response)

        if steps:
            run_workflow(page, steps)
        else:
            page.goto(args.url, wait_until="networkidle")
        if args.wait_for:
            page.wait_for_selector(args.wait_for, timeout=30000)
        if args.wait_ms:
            page.wait_for_timeout(args.wait_ms)
        # fonts settled => stable text metrics for pixel parity
        try:
            page.evaluate("document.fonts && document.fonts.ready")
        except Exception:
            pass

        page.screenshot(path=base + ".png", full_page=args.full_page)
        open(base + ".dom.html", "w", encoding="utf-8").write(page.content())
        model = page.evaluate(EXTRACTOR_JS, STYLE_PROPS)
        json.dump(model, open(base + ".model.json", "w", encoding="utf-8"), indent=1)
        try:
            a11y = page.accessibility.snapshot()
        except Exception:
            a11y = None
        json.dump(a11y, open(base + ".a11y.json", "w", encoding="utf-8"), indent=1)
        json.dump(network, open(base + ".network.json", "w", encoding="utf-8"), indent=1)
        ctx.close()
        browser.close()

    print(json.dumps({
        "ok": True, "name": args.name,
        "png": base + ".png", "model": base + ".model.json",
        "elements": len(model["elements"]), "tables": len(model["tables"]),
        "network_records": len(network),
        "sha256": {"png": sha256(base + ".png"), "dom": sha256(base + ".dom.html")},
        "captured_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }, indent=1))


if __name__ == "__main__":
    main()
