#!/usr/bin/env python3
"""
extract_jsp.py — pragmatic JSP/JSTL/Struts source extractor.

Turns ONE JSP (and the *.js it references) into a structured `source-model.json` the
jsp2react-builder builds FROM — so the React port comes from the actual source structure,
labels, loops, forms, and AJAX endpoints, NOT from guessing at a screenshot.

It is deliberately a *pragmatic* parser (regex + stdlib only — JSP with scriptlets/taglibs
is not valid XML, so a real XML/AST parser chokes on it). It does not aim to be a compiler;
it surfaces the high-value, hard-to-eyeball structure:

  taglibs        prefix -> uri (so the agent knows which tag family is in play)
  includes       static <%@include%>, <jsp:include>, Tiles inserts (the composition graph)
  loops          <c:forEach items/var/varStatus>           -> React .map() targets
  conditionals   <c:if test>, <c:choose>/<c:when test>      -> conditional rendering
  forms          <html:*>/<s:*>/plain form fields           -> controlled inputs + ActionForm names
  ajaxEndpoints  .do / /api/ / $.ajax / .load / dataTables / dojo.xhr / fetch / XHR.open
                 found in the JSP AND its referenced *.js   -> which interaction calls what
  messageKeys    <bean:message>/<fmt:message>/<spring:message>/<s:text>  -> .properties keys
  outputs        ${...} bindings                            -> data fields the screen shows

Output schema is stable and additive; see build_model() / --self-check.

Usage:
  python extract_jsp.py --jsp <file.jsp> [--webapp-dir <root>] [--out source-model.json]
  python extract_jsp.py --self-check
"""
import argparse, json, os, re, sys

# ---- regexes (compiled once) ------------------------------------------------
RE_TAGLIB   = re.compile(r"<%@\s*taglib\b([^%]*)%>", re.I)
RE_ATTR     = lambda name: re.compile(name + r'\s*=\s*"([^"]*)"', re.I)
RE_INC_STAT = re.compile(r'<%@\s*include\b[^%]*?file\s*=\s*"([^"]+)"', re.I)
RE_INC_JSP  = re.compile(r'<jsp:include\b[^>]*?page\s*=\s*"([^"]+)"', re.I)
RE_TILES    = re.compile(r'<tiles:(insert|insertTemplate|insertAttribute|put|putAttribute|definition)\b([^>]*)>', re.I)
RE_FOREACH  = re.compile(r'<[\w-]+:forEach\b([^>]*)>', re.I)
RE_IF       = re.compile(r'<[\w-]+:if\b([^>]*)>', re.I)
RE_WHEN     = re.compile(r'<[\w-]+:when\b([^>]*)>', re.I)
RE_FORMTAG  = re.compile(r'<(html|s|struts|spring):(form|text|textarea|select|checkbox|checkboxes|multibox|radio|hidden|password|submit|button|file|errors|option|options|optionsCollection)\b([^>]*?)/?>', re.I)
RE_PLAINFRM = re.compile(r'<form\b([^>]*)>', re.I)
RE_PLAININP = re.compile(r'<(input|select|textarea|button)\b([^>]*?)/?>', re.I)
RE_MESSAGE  = re.compile(r'<(?:bean|fmt|s|spring|html):(?:message|text)\b[^>]*?\b(?:key|code|name)\s*=\s*"([^"]+)"', re.I)
RE_OUTPUT   = re.compile(r'\$\{\s*([^}]+?)\s*\}')
RE_SCRIPT   = re.compile(r'<script\b[^>]*?\bsrc\s*=\s*"([^"]+)"', re.I)

# AJAX endpoint patterns: (label, regex with the URL in group 1)
AJAX_PATTERNS = [
    (".do",        re.compile(r'["\']([^"\']+\.do(?:\?[^"\']*)?)["\']', re.I)),
    ("/api/",      re.compile(r'["\']([^"\']*/api/[^"\']*)["\']', re.I)),
    (".load",      re.compile(r'\.load\(\s*["\']([^"\']+)["\']', re.I)),
    ("$.ajax url", re.compile(r'\burl\s*:\s*["\']([^"\']+)["\']', re.I)),
    ("$.get/post", re.compile(r'\$\.(?:get|post|getJSON)\(\s*["\']([^"\']+)["\']', re.I)),
    ("dataTables", re.compile(r'(?:sAjaxSource|["\']ajax["\'])\s*:\s*["\']([^"\']+)["\']', re.I)),
    ("fetch",      re.compile(r'\bfetch\(\s*["\']([^"\']+)["\']', re.I)),
    ("XHR.open",   re.compile(r'\.open\(\s*["\'][A-Z]+["\']\s*,\s*["\']([^"\']+)["\']')),
]


def lineno(text, pos):
    return text.count("\n", 0, pos) + 1


def attrs_of(s):
    """Pull a few common attributes out of a tag's attribute string."""
    out = {}
    for k in ("items", "var", "varStatus", "test", "property", "name", "action",
              "method", "type", "value", "page", "template", "styleId", "id"):
        m = RE_ATTR(k).search(s)
        if m:
            out[k] = m.group(1)
    return out


def find_ajax(text, source_label):
    found = []
    for label, rx in AJAX_PATTERNS:
        for m in rx.finditer(text):
            url = m.group(1).strip()
            if not url or url.startswith(("data:", "javascript:", "#")):
                continue
            ln = lineno(text, m.start())
            ctx = text.splitlines()[ln - 1].strip()[:160] if 0 < ln <= text.count("\n") + 1 else ""
            found.append({"url": url, "via": label, "source": source_label, "line": ln, "context": ctx})
    return found


def dedup(items, key):
    seen, out = set(), []
    for it in items:
        k = key(it)
        if k in seen:
            continue
        seen.add(k); out.append(it)
    return out


def build_model(jsp_text, jsp_rel, webapp_dir=None, scan_js=True):
    m = {"jsp": jsp_rel, "taglibs": [], "includes": [], "loops": [], "conditionals": [],
         "forms": [], "ajaxEndpoints": [], "messageKeys": [], "outputs": [], "scripts": [], "warnings": []}

    for tl in RE_TAGLIB.finditer(jsp_text):
        body = tl.group(1)
        pm, um = RE_ATTR("prefix").search(body), RE_ATTR("uri").search(body)
        if pm and um:
            m["taglibs"].append({"prefix": pm.group(1), "uri": um.group(1)})

    for mm in RE_INC_STAT.finditer(jsp_text):
        m["includes"].append({"type": "static", "path": mm.group(1), "line": lineno(jsp_text, mm.start())})
    for mm in RE_INC_JSP.finditer(jsp_text):
        m["includes"].append({"type": "jsp:include", "path": mm.group(1), "line": lineno(jsp_text, mm.start())})
    for mm in RE_TILES.finditer(jsp_text):
        a = attrs_of(mm.group(2))
        m["includes"].append({"type": "tiles:" + mm.group(1), "path": a.get("page") or a.get("template") or a.get("name", ""),
                              "attrs": a, "line": lineno(jsp_text, mm.start())})

    for mm in RE_FOREACH.finditer(jsp_text):
        a = attrs_of(mm.group(1))
        m["loops"].append({"items": a.get("items", ""), "var": a.get("var", ""),
                           "varStatus": a.get("varStatus", ""), "line": lineno(jsp_text, mm.start())})
    for kind, rx in (("if", RE_IF), ("when", RE_WHEN)):
        for mm in rx.finditer(jsp_text):
            a = attrs_of(mm.group(1))
            m["conditionals"].append({"kind": kind, "test": a.get("test", ""), "line": lineno(jsp_text, mm.start())})

    # forms: Struts/Spring tag fields + plain HTML fields, grouped loosely by nearest <form>/<html:form>
    fields = []
    for mm in RE_FORMTAG.finditer(jsp_text):
        if mm.group(2).lower() == "form":   # the <html:form> wrapper is recorded as an action, not a field
            continue
        a = attrs_of(mm.group(3))
        fields.append({"tag": "%s:%s" % (mm.group(1), mm.group(2)),
                       "property": a.get("property") or a.get("name", ""),
                       "type": a.get("type", ""), "line": lineno(jsp_text, mm.start())})
    for mm in RE_PLAININP.finditer(jsp_text):
        a = attrs_of(mm.group(2))
        fields.append({"tag": mm.group(1).lower(), "property": a.get("name", ""),
                       "type": a.get("type", ""), "line": lineno(jsp_text, mm.start())})
    form_actions = [attrs_of(mm.group(1)) for mm in RE_PLAINFRM.finditer(jsp_text)]
    htmlform = [attrs_of(mm.group(3)) for mm in RE_FORMTAG.finditer(jsp_text) if mm.group(2).lower() == "form"]
    if fields or form_actions or htmlform:
        m["forms"].append({"actions": [a.get("action", "") for a in (form_actions + htmlform) if a.get("action")],
                           "fields": fields})

    m["messageKeys"] = dedup([{"key": mm.group(1), "line": lineno(jsp_text, mm.start())}
                              for mm in RE_MESSAGE.finditer(jsp_text)], lambda x: x["key"])
    m["outputs"] = dedup([{"expr": mm.group(1)} for mm in RE_OUTPUT.finditer(jsp_text)], lambda x: x["expr"])[:200]
    m["scripts"] = dedup([mm.group(1) for mm in RE_SCRIPT.finditer(jsp_text)], lambda x: x) if False else \
                   list(dict.fromkeys(mm.group(1) for mm in RE_SCRIPT.finditer(jsp_text)))

    ajax = find_ajax(jsp_text, "jsp")
    if scan_js and webapp_dir:
        for src in m["scripts"]:
            if src.startswith(("http://", "https://", "//")):
                continue
            cand = os.path.normpath(os.path.join(webapp_dir, src.lstrip("/")))
            if os.path.isfile(cand):
                try:
                    ajax += find_ajax(open(cand, encoding="utf-8", errors="replace").read(), src)
                except Exception as e:
                    m["warnings"].append("could not scan %s: %s" % (src, e))
            else:
                m["warnings"].append("referenced script not found under webapp-dir: %s" % src)
    m["ajaxEndpoints"] = dedup(ajax, lambda x: (x["url"], x["via"]))

    if not (m["loops"] or m["forms"] or m["outputs"] or m["includes"]):
        m["warnings"].append("no structure extracted — JSP may be a pure layout/fragment or use unusual tags")
    return m


def main():
    ap = argparse.ArgumentParser(description="Extract a pragmatic source-model.json from one JSP (+ its referenced JS).")
    ap.add_argument("--jsp", help="Path to the JSP file. Required for a real run.")
    ap.add_argument("--webapp-dir", help="Webapp root, used to resolve <script src> for AJAX scanning and includes.")
    ap.add_argument("--out", help="Write source-model.json here (default: stdout).")
    ap.add_argument("--no-scan-js", action="store_true", help="Do not scan referenced *.js files for AJAX endpoints.")
    ap.add_argument("--self-check", action="store_true", help="Run on a built-in sample and assert extraction works; no file needed.")
    args = ap.parse_args()

    if args.self_check:
        sample = r'''
        <%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>
        <%@ taglib prefix="html" uri="/WEB-INF/struts-html.tld" %>
        <%@ include file="/jsp/inc/header.jspf" %>
        <html:form action="/fateamprofile.do">
          <html:text property="faNumber"/>
          <html:select property="entityLevel"/>
        </html:form>
        <c:forEach items="${comp.rows}" var="row" varStatus="s">
          <c:if test="${row.active}">${row.name}</c:if>
        </c:forEach>
        <bean:message key="fa.profile.title"/>
        <script src="js/fa.js"></script>
        <script> $.ajax({ url: "/BAA/fadetail.do?tab=comp" }); $("#g").load("/BAA/grid.do"); </script>
        '''
        m = build_model(sample, "sample.jsp", scan_js=False)
        assert any(t["prefix"] == "c" for t in m["taglibs"]), "taglib miss"
        assert m["loops"] and m["loops"][0]["items"] == "${comp.rows}" and m["loops"][0]["var"] == "row", "loop miss"
        assert any(c["kind"] == "if" for c in m["conditionals"]), "conditional miss"
        assert m["forms"] and any(f["property"] == "faNumber" for f in m["forms"][0]["fields"]), "form field miss"
        assert all(f["tag"] != "html:form" for f in m["forms"][0]["fields"]), "form wrapper leaked into fields"
        assert any(k["key"] == "fa.profile.title" for k in m["messageKeys"]), "message key miss"
        urls = {e["url"] for e in m["ajaxEndpoints"]}
        assert "/BAA/fadetail.do?tab=comp" in urls and "/BAA/grid.do" in urls, "ajax miss: %s" % urls
        assert "js/fa.js" in m["scripts"], "script ref miss"
        print(json.dumps({"self_check": "ok", "loops": len(m["loops"]), "fields": len(m["forms"][0]["fields"]),
                          "ajax": len(m["ajaxEndpoints"]), "messageKeys": len(m["messageKeys"])}))
        return

    if not args.jsp:
        raise SystemExit("--jsp is required (or use --self-check)")
    if not os.path.isfile(args.jsp):
        raise SystemExit("JSP not found: %s" % args.jsp)
    text = open(args.jsp, encoding="utf-8", errors="replace").read()
    rel = os.path.relpath(args.jsp, args.webapp_dir) if args.webapp_dir else os.path.basename(args.jsp)
    model = build_model(text, rel.replace("\\", "/"), webapp_dir=args.webapp_dir, scan_js=not args.no_scan_js)

    out = json.dumps(model, indent=1)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        open(args.out, "w", encoding="utf-8").write(out)
        print(json.dumps({"ok": True, "out": args.out, "loops": len(model["loops"]),
                          "forms": len(model["forms"]), "ajaxEndpoints": len(model["ajaxEndpoints"]),
                          "messageKeys": len(model["messageKeys"]), "warnings": model["warnings"]}))
    else:
        print(out)


if __name__ == "__main__":
    main()
