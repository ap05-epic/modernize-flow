#!/usr/bin/env python3
"""
dom_diff.py — deterministic structural/semantic diff between two normalized screen models.

Compares legacy.model.json vs react.model.json (both produced by capture_screen.py) and emits a
CONCRETE, actionable delta list — the thing the builder fixes from. This is the "1:1 fidelity" lane:
it does NOT judge visual look (that's pixel_diff.js); it enforces that copy, labels, field/tab order,
table columns, validation text, and the set of controls match EXACTLY.

Three severities:
  CRITICAL — content differs: missing/extra control or text, text mismatch, label/name/type mismatch,
             DATA-table column missing/extra/reordered, field or tab order mismatch. Fails the gate.
  NESTING  — same content, different markup GROUPING: a text present on both sides but split/merged
             across different elements (punctuation-insensitively — "(All Branches)" vs "All Branches"),
             legacy's headerless layout-table soup vs clean React layout, a legacy section-title table
             rendered as a React heading, or columns re-segmented into different tables/sections.
             Reported (it explains pixel drift) but does NOT fail the gate — clean React must not be
             forced to reproduce 1998 nested-table markup. (verify_screen --strict-nesting gates it.)
  ADVISORY — per-element style value differences; guide pixel fixes.

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
            # ratio on the VALUE only: the shared "TEXT:" prefix inflates similarity of short values
            # (e.g. "TEXT:2023" vs "TEXT:39" pairs at ~0.7), producing nonsense text_mismatch pairs.
            ratio = difflib.SequenceMatcher(a=dk.split(":", 1)[1], b=ik.split(":", 1)[1]).ratio()
            if ratio > best_ratio:
                best, best_ratio = idx, ratio
        if best is not None and best_ratio >= 0.5:
            used_ins.add(best)
            ik, ins_el = pending_ins[best]
            deltas.append({"type": "text_mismatch", "severity": "critical", "kind": dk.split(":", 1)[0],
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
    """Diff DATA tables (>=1 non-empty header) aligned by header similarity — NOT by document index.
    Legacy pages use headerless nested tables for LAYOUT; pairing by index shifts every real data table
    and cascades false column mismatches. Layout-table count drift is markup shape, not content — the
    text/control lanes already check what's inside — so it's reported once, as a NESTING delta."""
    all_lt, all_rt = legacy.get("tables", []), react.get("tables", [])
    lt = [t for t in all_lt if any(norm(h) for h in t.get("headers", []))]
    rt = [t for t in all_rt if any(norm(h) for h in t.get("headers", []))]
    lk = [" | ".join(norm(h) for h in t["headers"]) for t in lt]
    rk = [" | ".join(norm(h) for h in t["headers"]) for t in rt]
    sm = difflib.SequenceMatcher(a=lk, b=rk, autojunk=False)
    pending_del, pending_ins = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag in ("delete", "replace"):
            pending_del += list(range(i1, i2))
        if tag in ("insert", "replace"):
            pending_ins += list(range(j1, j2))
    used = set()
    for li in pending_del:
        best, best_ratio = None, 0.0
        for pos, rj in enumerate(pending_ins):
            if pos in used:
                continue
            r = difflib.SequenceMatcher(a=lk[li], b=rk[rj], autojunk=False).ratio()
            if r > best_ratio:
                best, best_ratio = pos, r
        if best is not None and best_ratio >= 0.5:   # same table, columns drifted
            used.add(best)
            rj = pending_ins[best]
            deltas.append({"type": "table_columns_mismatch", "severity": "critical",
                           "legacy": lt[li]["headers"], "react": rt[rj]["headers"],
                           "where": {"table_index": li},
                           "hint": "Column set/order/text differ. Match columns exactly, in order."})
        else:
            deltas.append({"type": "missing_table", "severity": "critical", "legacy": lt[li]["headers"],
                           "react": None, "where": {"table_index": li},
                           "hint": "Data table missing in React; add with these columns IN ORDER."})
    for pos, rj in enumerate(pending_ins):
        if pos in used:
            continue
        deltas.append({"type": "extra_table", "severity": "critical", "legacy": None,
                       "react": rt[rj]["headers"], "where": {"table_index": rj},
                       "hint": "Extra data table in React; remove it (no new artifacts)."})
    ll, rl = len(all_lt) - len(lt), len(all_rt) - len(rt)
    if ll != rl:
        deltas.append({"type": "layout_table_shape", "severity": "nesting",
                       "legacy": "%d headerless layout tables" % ll, "react": "%d" % rl, "where": {},
                       "hint": "Legacy builds its LAYOUT from headerless nested tables; the React markup shape "
                               "differs but the content lanes above check everything inside them. Do NOT "
                               "recreate legacy table-soup markup to silence this."})


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


CHUNK_HINT = ("Same text exists on the other side, just split/merged/grouped differently (legacy "
              "markup nesting). No content is lost — do NOT restructure to legacy nesting to silence this.")
SEGMENT_HINT = ("This table's headers all exist as content on the other side — the section is rendered "
                "with a different table segmentation/markup, not missing. Do NOT rebuild legacy table "
                "structure to silence this.")


def _fold(s):
    """Punctuation-insensitive token form: legacy '(All Branches)' must match react 'All Branches' —
    parens/colons around the same words are markup dressing, not content. Case still matters."""
    return " " + re.sub(r"[^0-9A-Za-z]+", " ", s or "").strip() + " "


def _blob(model):
    """All visible text in DOM order (folded + raw forms), space-padded for boundary substring checks."""
    joined = " ".join(norm(el.get("text")) for el in model.get("elements", []) if norm(el.get("text")))
    return {"fold": _fold(joined), "raw": " " + joined + " "}


def _present(blob, t):
    # ponytail: folding means punctuation-only label drift ("Account #" -> "Account") classes as
    # nesting, not critical — it is still reported, and the pixel lane shows it in record mode.
    ft = _fold(t).strip()
    if ft:
        return (" %s " % ft) in blob["fold"]
    rt = norm(t)                       # pure-punctuation token ("#", "$"): check the raw text instead
    return bool(rt) and (" %s " % rt) in blob["raw"]


def reclassify_nesting(deltas, legacy, react):
    """Demote deltas whose CONTENT is present on the other side from critical to NESTING — different
    grouping/segmentation, not lost content. Covers: TEXT chunking (one legacy node -> two React spans),
    tables rendered with a different segmentation (a legacy section-title table -> a React heading), and
    column sets that moved between tables. CTRL/IMG identity deltas always stay critical (a missing
    control is missing even if its label text appears elsewhere); a reordered same-set column list stays
    critical (column ORDER is content)."""
    # ponytail: boundary-substring presence can misclass a lost DUPLICATE ("Delete" x3 -> x2) as
    # nesting; the delta is still reported. Add per-key occurrence counting if that ever bites.
    lblob, rblob = _blob(legacy), _blob(react)
    for d in deltas:
        if d["severity"] != "critical":
            continue
        if d["type"] == "text_mismatch" and d.get("kind") == "TEXT":
            if _present(rblob, norm(d.get("legacy"))) and _present(lblob, norm(d.get("react"))):
                d["severity"], d["hint"] = "nesting", CHUNK_HINT
        elif d["type"] in ("missing_in_react", "extra_in_react"):
            key = str(d["legacy"] if d["type"] == "missing_in_react" else d["react"])
            if not key.startswith("TEXT:"):
                continue
            blob = rblob if d["type"] == "missing_in_react" else lblob
            if _present(blob, key.split(":", 1)[1]):
                d["severity"], d["hint"] = "nesting", CHUNK_HINT
        elif d["type"] in ("missing_table", "extra_table"):
            headers = d["legacy"] if d["type"] == "missing_table" else d["react"]
            blob = rblob if d["type"] == "missing_table" else lblob
            heads = [h for h in (headers or []) if norm(h)]
            if heads and all(_present(blob, norm(h)) for h in heads):
                d["severity"], d["hint"] = "nesting", SEGMENT_HINT
        elif d["type"] == "table_columns_mismatch":
            lset = {norm(h) for h in (d.get("legacy") or []) if norm(h)}
            rset = {norm(h) for h in (d.get("react") or []) if norm(h)}
            if lset != rset:   # same set + different order = a true column reorder -> stays critical
                if all(_present(rblob, h) for h in lset - rset) and all(_present(lblob, h) for h in rset - lset):
                    d["severity"], d["hint"] = "nesting", SEGMENT_HINT


def build_diff(legacy, react):
    deltas = []
    diff_salient(salient_list(legacy), salient_list(react), deltas)
    diff_tables(legacy, react, deltas)
    diff_order(legacy, react, deltas)
    diff_styles(legacy, react, deltas)
    reclassify_nesting(deltas, legacy, react)
    crit = [d for d in deltas if d["severity"] == "critical"]
    nest = [d for d in deltas if d["severity"] == "nesting"]
    adv = [d for d in deltas if d["severity"] == "advisory"]
    return {"critical": crit, "nesting": nest, "advisory": adv,
            "summary": {"critical": len(crit), "nesting": len(nest), "advisory": len(adv),
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

        # NESTING (not critical): one legacy text node rendered as two React spans — content present,
        # grouping differs. Must NOT fail the gate; a truly changed label (above) still must.
        L2 = {"title": "x", "elements": [
            {"i": 0, "tag": "td", "text": "Total: $5m", "box": {}, "style": {}, "path": "0/0"}], "tables": [], "forms": []}
        R2 = {"title": "x", "elements": [
            {"i": 0, "tag": "span", "text": "Total:", "box": {}, "style": {}, "path": "0/0"},
            {"i": 1, "tag": "span", "text": "$5m", "box": {}, "style": {}, "path": "0/1"}], "tables": [], "forms": []}
        d2 = build_diff(L2, R2)
        assert d2["summary"]["critical"] == 0 and d2["summary"]["nesting"] >= 1, d2

        # NESTING (not critical): legacy headerless LAYOUT tables vs clean React markup — but a real
        # DATA table (has headers) still diffs critically, aligned by similarity not index.
        L3 = {"title": "x", "elements": [], "forms": [], "tables": [
            {"headers": [], "rowCount": 0}, {"headers": [], "rowCount": 2}, {"headers": [], "rowCount": 0},
            {"headers": ["Name", "Rank"], "rowCount": 5}]}
        R3 = {"title": "x", "elements": [], "forms": [], "tables": [{"headers": ["Name", "Rank"], "rowCount": 5}]}
        d3 = build_diff(L3, R3)
        assert d3["summary"]["critical"] == 0 and d3["summary"]["nesting"] == 1, d3
        R3bad = {"title": "x", "elements": [], "forms": [], "tables": [{"headers": ["Name", "Level"], "rowCount": 5}]}
        d3b = build_diff(L3, R3bad)
        assert d3b["summary"]["critical"] == 1 and d3b["critical"][0]["type"] == "table_columns_mismatch", d3b

        def m(elements=(), tables=()):
            els = [{"i": i, "tag": "td", "text": t, "box": {}, "style": {}, "path": "0/%d" % i}
                   for i, t in enumerate(elements)]
            return {"title": "x", "elements": els, "tables": list(tables), "forms": []}

        # regression (pod triage): short numeric values must NOT pair as text_mismatch — the shared
        # "TEXT:" key prefix used to inflate similarity ("2023" was pairing with "39").
        d4 = build_diff(m(["2023"]), m(["39"]))
        assert not any(x["type"] == "text_mismatch" for x in d4["critical"]), d4
        assert d4["summary"]["critical"] == 2, d4   # genuinely different content stays critical

        # regression (pod triage): punctuation must not defeat the presence check — legacy
        # "Rank (All Branches)" in one cell vs react "Rank" + "All Branches" cells is NESTING.
        d5 = build_diff(m(["Rank (All Branches)"]), m(["Rank", "All Branches"]))
        assert d5["summary"]["critical"] == 0 and d5["summary"]["nesting"] >= 1, d5

        # regression (pod triage): a legacy section-title table rendered as a React heading (content
        # present, no matching <table>) is NESTING, not missing_table.
        d6 = build_diff(m(["Compensation"], [{"headers": ["Compensation"], "rowCount": 2}]),
                        m(["Compensation"]))
        assert d6["summary"]["critical"] == 0 and d6["summary"]["nesting"] == 1, d6

        # regression (pod triage): columns re-segmented into other tables/sections (set differs, texts
        # present on the other side) is NESTING — but a same-set column REORDER stays critical.
        d7 = build_diff(m(["C"], [{"headers": ["A", "B", "C"], "rowCount": 1}]),
                        m(["C"], [{"headers": ["A", "B"], "rowCount": 1}]))
        assert d7["summary"]["critical"] == 0 and d7["summary"]["nesting"] == 1, d7
        d8 = build_diff(m((), [{"headers": ["A", "B"], "rowCount": 1}]),
                        m((), [{"headers": ["B", "A"], "rowCount": 1}]))
        assert d8["summary"]["critical"] == 1 and d8["critical"][0]["type"] == "table_columns_mismatch", d8

        print(json.dumps({"self_check": "ok", "delta": d["critical"][0]["type"],
                          "chunking_is_nesting": d2["summary"]["nesting"],
                          "layout_tables_are_nesting": d3["summary"]["nesting"],
                          "data_table_still_critical": d3b["summary"]["critical"],
                          "short_numerics_unpaired": d4["summary"]["critical"],
                          "punct_chunking_is_nesting": d5["summary"]["nesting"],
                          "section_title_table_is_nesting": d6["summary"]["nesting"],
                          "moved_columns_are_nesting": d7["summary"]["nesting"],
                          "column_reorder_still_critical": d8["summary"]["critical"]}, indent=1)); return

    legacy = json.load(open(args.legacy, encoding="utf-8"))
    react = json.load(open(args.react, encoding="utf-8"))
    d = build_diff(legacy, react)
    if args.out:
        json.dump(d, open(args.out, "w", encoding="utf-8"), indent=1)
    print(json.dumps(d["summary"], indent=1))


if __name__ == "__main__":
    main()
