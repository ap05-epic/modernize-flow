#!/usr/bin/env python3
"""
dom_diff.py — deterministic structural/semantic diff between two normalized screen models.

Compares legacy.model.json vs react.model.json (both produced by capture_screen.py) and emits a
CONCRETE, actionable delta list — the thing the builder fixes from. This is the "1:1 fidelity" lane:
it does NOT judge visual look (that's pixel_diff.js); it enforces that copy, labels, field/tab order,
table columns, validation text, and the set of controls match EXACTLY.

CRITICAL deltas (fail the gate): missing/extra control or text, text mismatch, label/name/type mismatch,
table column missing/extra/reordered, field or tab order mismatch.
ADVISORY deltas (do not fail; guide pixel fixes): per-element style value differences.

Importable: build_diff(legacy_model, react_model) -> dict. Also a CLI.
Stdlib only.
"""
import argparse, json, sys, difflib, os, re

# style props compared for advisory hints, with how to compare them
PX_PROPS = {"font-size", "line-height", "letter-spacing", "width", "height", "min-width", "min-height",
            "margin-top", "margin-right", "margin-bottom", "margin-left",
            "padding-top", "padding-right", "padding-bottom", "padding-left",
            "border-top-width", "border-bottom-width", "border-left-width", "border-right-width"}
EXACT_PROPS = {"font-family", "font-weight", "font-style", "color", "background-color", "text-align",
               "text-transform", "text-decoration-line", "display", "border-radius"}
PX_TOL = 1.0  # px tolerance for advisory style hints


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def px(v):
    m = re.match(r"^(-?\d+(?:\.\d+)?)px$", (v or "").strip())
    return float(m.group(1)) if m else None


def salient_key(el):
    """A stable identity for a parity-critical element, or None if not salient."""
    inp = el.get("input")
    if inp:
        ident = inp.get("name") or inp.get("placeholder") or el.get("name") or norm(el.get("text"))
        return f'CTRL:{el["tag"]}:{inp.get("type","")}:{ident}'
    t = norm(el.get("text"))
    if t:
        return f'TEXT:{t}'
    if el["tag"] == "img" and el.get("name"):
        return f'IMG:{norm(el["name"])}'
    return None


def salient_list(model):
    out = []
    for el in model.get("elements", []):
        k = salient_key(el)
        if k:
            out.append((k, el))
    return out


def where(el):
    sel = el["tag"]
    if el.get("id"):
        sel += "#" + el["id"]
    elif el.get("classes"):
        sel += "." + ".".join(el["classes"].split()[:2])
    b = el.get("box", {})
    return {"selector": sel, "path": el.get("path"), "box": b, "text": norm(el.get("text"))[:80]}


def diff_salient(legacy, react, deltas):
    lk = [k for k, _ in legacy]
    rk = [k for k, _ in react]
    sm = difflib.SequenceMatcher(a=lk, b=rk, autojunk=False)
    pending_del, pending_ins = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag in ("delete", "replace"):
            pending_del += [legacy[i] for i in range(i1, i2)]
        if tag in ("insert", "replace"):
            pending_ins += [react[j] for j in range(j1, j2)]
    # pair leftovers that are clearly the same element with changed text => "text mismatch"
    used_ins = set()
    for dk, del_el in pending_del:
        best, best_ratio = None, 0.0
        for idx, (ik, ins_el) in enumerate(pending_ins):
            if idx in used_ins:
                continue
            if dk.split(":", 1)[0] != ik.split(":", 1)[0]:
                continue  # only pair like-with-like (TEXT/CTRL/IMG)
            ratio = difflib.SequenceMatcher(a=dk, b=ik).ratio()
            if ratio > best_ratio:
                best, best_ratio = idx, ratio
        if best is not None and best_ratio >= 0.5:
            used_ins.add(best)
            ik, ins_el = pending_ins[best]
            deltas.append({"type": "text_mismatch", "severity": "critical",
                           "legacy": dk.split(":", 1)[1], "react": ik.split(":", 1)[1],
                           "where": where(ins_el),
                           "hint": "Make the React text/label exactly match the legacy value."})
        else:
            deltas.append({"type": "missing_in_react", "severity": "critical",
                           "legacy": dk, "react": None, "where": where(del_el),
                           "hint": "This control/text exists in the legacy screen but not in React. Add it."})
    for idx, (ik, ins_el) in enumerate(pending_ins):
        if idx in used_ins:
            continue
        deltas.append({"type": "extra_in_react", "severity": "critical",
                       "legacy": None, "react": ik, "where": where(ins_el),
                       "hint": "This exists in React but not in the legacy screen. Remove it (no new artifacts)."})


def diff_tables(legacy, react, deltas):
    lt, rt = legacy.get("tables", []), react.get("tables", [])
    for idx in range(max(len(lt), len(rt))):
        lh = lt[idx]["headers"] if idx < len(lt) else None
        rh = rt[idx]["headers"] if idx < len(rt) else None
        if lh is None:
            deltas.append({"type": "extra_table", "severity": "critical", "legacy": None, "react": rh,
                           "where": {"table_index": idx}, "hint": "Extra table in React; remove."}); continue
        if rh is None:
            deltas.append({"type": "missing_table", "severity": "critical", "legacy": lh, "react": None,
                           "where": {"table_index": idx}, "hint": "Table missing in React; add with these columns IN ORDER."}); continue
        if [norm(x) for x in lh] != [norm(x) for x in rh]:
            deltas.append({"type": "table_columns_mismatch", "severity": "critical",
                           "legacy": lh, "react": rh, "where": {"table_index": idx},
                           "hint": "Column set/order/text differ. Match columns exactly, in order."})


def focusable_seq(model):
    foc = []
    for el in model.get("elements", []):
        if el.get("input") or el["tag"] == "a":
            ti = el.get("tabindex")
            ti = int(ti) if (ti not in (None, "") and str(ti).lstrip("-").isdigit()) else None
            ident = (el.get("input", {}) or {}).get("name") or norm(el.get("text")) or el.get("href") or el.get("name")
            foc.append((ti, el["i"], ident, el))
    # tab order: positive tabindex first (by value), then DOM order
    foc.sort(key=lambda t: (0, t[0]) if (t[0] and t[0] > 0) else (1, t[1]))
    return [(norm(str(x[2])), x[3]) for x in foc if x[2]]


def diff_order(legacy, react, deltas):
    ls = [k for k, _ in focusable_seq(legacy)]
    rs = [k for k, _ in focusable_seq(react)]
    if ls != rs and set(ls) == set(rs):
        deltas.append({"type": "tab_order_mismatch", "severity": "critical",
                       "legacy": ls, "react": rs, "where": {},
                       "hint": "Same focusable controls but different field/tab order. Reorder to match legacy."})


def diff_styles(legacy, react, deltas):
    # advisory only: for text/control pairs that matched by key, compare curated styles
    lmap = {}
    for k, el in salient_list(legacy):
        lmap.setdefault(k, el)
    for k, rel in salient_list(react):
        lel = lmap.get(k)
        if not lel:
            continue
        ls, rs = lel.get("style", {}), rel.get("style", {})
        for p in EXACT_PROPS:
            lv, rv = norm(ls.get(p)), norm(rs.get(p))
            if lv and rv and lv != rv:
                deltas.append({"type": "style", "severity": "advisory", "prop": p,
                               "legacy": lv, "react": rv, "where": where(rel),
                               "hint": f"{p}: legacy {lv} vs react {rv}."})
        for p in PX_PROPS:
            a, b = px(ls.get(p)), px(rs.get(p))
            if a is not None and b is not None and abs(a - b) > PX_TOL:
                deltas.append({"type": "style", "severity": "advisory", "prop": p,
                               "legacy": ls.get(p), "react": rs.get(p), "where": where(rel),
                               "hint": f"{p}: legacy {ls.get(p)} vs react {rs.get(p)} (Δ{abs(a-b):.0f}px)."})


def build_diff(legacy, react):
    deltas = []
    diff_salient(salient_list(legacy), salient_list(react), deltas)
    diff_tables(legacy, react, deltas)
    diff_order(legacy, react, deltas)
    diff_styles(legacy, react, deltas)
    crit = [d for d in deltas if d["severity"] == "critical"]
    adv = [d for d in deltas if d["severity"] == "advisory"]
    return {"critical": crit, "advisory": adv,
            "summary": {"critical": len(crit), "advisory": len(adv),
                        "legacy_title": legacy.get("title"), "react_title": react.get("title")}}


def main():
    ap = argparse.ArgumentParser(description="Deterministic structural/semantic diff of two screen models.")
    ap.add_argument("--legacy", help="legacy *.model.json")
    ap.add_argument("--react", help="react *.model.json")
    ap.add_argument("--out", help="write deltas json here")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()

    if args.self_check:
        L = {"title": "x", "elements": [
            {"i": 0, "tag": "label", "text": "Account #", "box": {}, "style": {}, "path": "0/0"},
            {"i": 1, "tag": "input", "text": "", "box": {}, "style": {}, "path": "0/1",
             "input": {"name": "acct", "type": "text", "placeholder": ""}}], "tables": [], "forms": []}
        R = {"title": "x", "elements": [
            {"i": 0, "tag": "label", "text": "Acct #", "box": {}, "style": {}, "path": "0/0"},
            {"i": 1, "tag": "input", "text": "", "box": {}, "style": {}, "path": "0/1",
             "input": {"name": "acct", "type": "text", "placeholder": ""}}], "tables": [], "forms": []}
        d = build_diff(L, R)
        assert d["summary"]["critical"] == 1 and d["critical"][0]["type"] == "text_mismatch", d
        print(json.dumps({"self_check": "ok", "delta": d["critical"][0]}, indent=1)); return

    legacy = json.load(open(args.legacy, encoding="utf-8"))
    react = json.load(open(args.react, encoding="utf-8"))
    d = build_diff(legacy, react)
    if args.out:
        json.dump(d, open(args.out, "w", encoding="utf-8"), indent=1)
    print(json.dumps(d["summary"], indent=1))


if __name__ == "__main__":
    main()
