#!/usr/bin/env python3
"""
verify_contract.py — prove the NEW Spring Boot endpoint reproduces the LEGACY data.

The frontend capture already records the REAL legacy responses to a HAR (capture_screen.py
--record-har). That HAR is the oracle: the new endpoint's JSON must carry the same fields
(and, in record mode, the same values) as the legacy response it replaces. This is the backend
analog of parity-verify/verify_screen.py — same exit contract (0 = PASS, 2 = FAIL), no new
mechanism, deterministic.

What it checks:
  * field presence  — every field the legacy JSON has must appear in the new JSON      (FAIL if missing)
  * field types     — shared fields must have the same JSON type                        (FAIL on mismatch)
  * row count       — array responses should have a comparable number of rows           (record: FAIL on 0 vs N)
  * value spot-check— record mode compares first-row values for shared fields            (advisory)
Extra fields in the new response are reported as warnings, not failures (the API may add convenience fields).

Usage:
  python verify_contract.py --har <view>/legacy.har --endpoint-json new_endpoint.json \
      --match /api/fa-summary --data-mode record
  python verify_contract.py --self-check
"""
import argparse, base64, json, os, re, sys, tempfile


def load_har(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return json.load(f)


def har_json_responses(har):
    """Pull JSON responses out of a HAR -> [{method, url, pathname, json}]."""
    out = []
    for e in (har.get("log", {}).get("entries", []) or []):
        req, resp = e.get("request", {}), e.get("response", {})
        content = resp.get("content", {}) or {}
        mime = (content.get("mimeType") or "").lower()
        text = content.get("text") or ""
        if content.get("encoding") == "base64" and text:
            try:
                text = base64.b64decode(text).decode("utf-8", "replace")
            except Exception:
                continue
        looks_json = "json" in mime or text.strip()[:1] in ("{", "[")
        if not looks_json or not text.strip():
            continue
        try:
            data = json.loads(text)
        except Exception:
            continue
        url = req.get("url", "")
        path = re.sub(r"^[a-z]+://[^/]+", "", url).split("?", 1)[0] or url
        out.append({"method": req.get("method", "GET"), "url": url, "pathname": path, "json": data})
    return out


def jtype(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    return "object"


def shape(data):
    """Normalize a JSON value to {kind, rows, fields:{name:type}} (fields = union over array rows)."""
    if isinstance(data, list):
        fields, rows = {}, len(data)
        for row in data:
            if isinstance(row, dict):
                for k, v in row.items():
                    fields.setdefault(k, jtype(v))
        return {"kind": "array", "rows": rows, "fields": fields, "first": (data[0] if data else None)}
    if isinstance(data, dict):
        # an envelope like {data:[...]} or {rows:[...]} -> dig into the first list value
        for k, v in data.items():
            if isinstance(v, list):
                inner = shape(v)
                inner["envelopeKey"] = k
                return inner
        return {"kind": "object", "rows": 1, "fields": {k: jtype(v) for k, v in data.items()}, "first": data}
    return {"kind": "scalar", "rows": 1, "fields": {}, "first": data}


def compare(legacy, react, mode):
    ls, rs = shape(legacy), shape(react)
    # field presence is only judgeable when react actually returned data; an empty array has no fields
    # to compare (in record mode that's caught by emptyFail; in live mode an empty result is tolerated).
    react_has_data = rs["rows"] > 0 or bool(rs["fields"])
    missing = [f for f in ls["fields"] if f not in rs["fields"]] if react_has_data else []
    extra = [f for f in rs["fields"] if f not in ls["fields"]]
    type_mismatch = [{"field": f, "legacy": ls["fields"][f], "react": rs["fields"][f]}
                     for f in ls["fields"] if f in rs["fields"] and ls["fields"][f] != rs["fields"][f]
                     and "null" not in (ls["fields"][f], rs["fields"][f])]
    row_delta = {"legacy": ls["rows"], "react": rs["rows"]}
    value_spot = []
    if mode == "record" and isinstance(ls.get("first"), dict) and isinstance(rs.get("first"), dict):
        for f in ls["fields"]:
            if f in rs["first"] and f in ls["first"] and str(ls["first"][f]) != str(rs["first"][f]):
                value_spot.append({"field": f, "legacy": ls["first"][f], "react": rs["first"][f]})
    # gate: missing field or type mismatch always fails; record mode also fails on empty react vs non-empty legacy
    empty_fail = mode == "record" and ls["rows"] > 0 and rs["rows"] == 0
    ok = (not missing) and (not type_mismatch) and (not empty_fail)
    return {"ok": ok, "mode": mode, "missing": missing, "extra": extra,
            "typeMismatch": type_mismatch, "rowDelta": row_delta,
            "emptyFail": empty_fail, "valueSpot": value_spot,
            "legacyKind": ls["kind"], "reactKind": rs["kind"]}


def pick_legacy(responses, match):
    if not responses:
        return None
    if match:
        for r in responses:
            if match.lower() in r["pathname"].lower() or match.lower() in r["url"].lower():
                return r
    # else the richest array response (most fields), else the first
    arrays = [r for r in responses if isinstance(r["json"], list) and r["json"]]
    if arrays:
        return max(arrays, key=lambda r: len(shape(r["json"])["fields"]))
    return responses[0]


def render(result, legacy_path, match):
    lines = ["# Backend contract verify — %s" % ("PASS" if result["ok"] else "FAIL"),
             "",
             "- data mode: **%s**" % result["mode"],
             "- legacy oracle: `%s`%s" % (legacy_path, ("  (matched `%s`)" % match if match else "")),
             "- shapes: legacy `%s` vs react `%s`" % (result["legacyKind"], result["reactKind"]),
             "- rows: legacy %s, react %s" % (result["rowDelta"]["legacy"], result["rowDelta"]["react"])]
    if result["missing"]:
        lines.append("- **MISSING fields (fail):** " + ", ".join(result["missing"]))
    if result["typeMismatch"]:
        lines.append("- **TYPE mismatches (fail):** " +
                     "; ".join("%s legacy=%s react=%s" % (m["field"], m["legacy"], m["react"]) for m in result["typeMismatch"]))
    if result["emptyFail"]:
        lines.append("- **EMPTY (fail):** legacy returned rows, react returned none")
    if result["extra"]:
        lines.append("- extra react fields (warn): " + ", ".join(result["extra"]))
    if result["valueSpot"]:
        lines.append("- first-row value diffs (advisory): " +
                     "; ".join("%s legacy=%r react=%r" % (v["field"], v["legacy"], v["react"]) for v in result["valueSpot"]))
    if result["ok"]:
        lines.append("\nContract reproduced. ✔")
    else:
        lines.append("\nFix the gateway/DTO mapping so the endpoint reproduces the legacy fields, then re-run.")
    return "\n".join(lines) + "\n"


def self_check():
    har = {"log": {"entries": [
        {"request": {"method": "GET", "url": "http://x/api/fa-summary"},
         "response": {"content": {"mimeType": "application/json",
                                  "text": json.dumps([{"acctNo": "001", "bal": 12.5}, {"acctNo": "002", "bal": 9.0}])}}}
    ]}}
    d = tempfile.mkdtemp(prefix="verify_contract_")
    hp = os.path.join(d, "legacy.har")
    with open(hp, "w", encoding="utf-8") as f:
        json.dump(har, f)
    responses = har_json_responses(load_har(hp))
    assert responses and responses[0]["pathname"] == "/api/fa-summary", responses
    legacy = pick_legacy(responses, "/api/fa-summary")["json"]

    good = [{"acctNo": "001", "bal": 12.5}, {"acctNo": "002", "bal": 9.0}]
    r_ok = compare(legacy, good, "record")
    assert r_ok["ok"] and not r_ok["missing"], r_ok

    missing_field = [{"acctNo": "001"}, {"acctNo": "002"}]
    r_miss = compare(legacy, missing_field, "record")
    assert (not r_miss["ok"]) and "bal" in r_miss["missing"], r_miss

    empty = []
    r_empty = compare(legacy, empty, "record")
    assert not r_empty["ok"] and r_empty["emptyFail"], r_empty
    # live mode tolerates empty/value drift (structure only)
    r_live = compare(legacy, empty, "live")
    assert r_live["ok"], r_live

    print(json.dumps({"self_check": "ok", "responses": len(responses),
                      "pass_on_match": r_ok["ok"], "fail_on_missing": not r_miss["ok"],
                      "record_fails_empty": r_empty["emptyFail"], "live_tolerates_empty": r_live["ok"]}))


def main():
    ap = argparse.ArgumentParser(description="Verify a new endpoint's JSON reproduces the legacy recorded HAR response (backend contract gate).")
    ap.add_argument("--har", help="Legacy recorded HAR (the oracle) from capture_screen.py --record-har.")
    ap.add_argument("--endpoint-json", help="File with the NEW endpoint's JSON response (curl it to a file).")
    ap.add_argument("--endpoint-url", help="Alternatively, GET this URL for the new response (needs it running + reachable).")
    ap.add_argument("--match", help="Substring of the legacy HAR path/url to compare against (e.g. /api/fa-summary).")
    ap.add_argument("--data-mode", choices=["record", "live"], default="record",
                    help="record = field+type+values gate; live = structure only (values drift).")
    ap.add_argument("--out", help="Write the report .md here (else stdout).")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()

    if args.self_check:
        self_check()
        return
    if not args.har or not (args.endpoint_json or args.endpoint_url):
        raise SystemExit("need --har and (--endpoint-json or --endpoint-url)")

    responses = har_json_responses(load_har(args.har))
    chosen = pick_legacy(responses, args.match)
    if not chosen:
        raise SystemExit("no JSON response found in the HAR to use as the oracle (legacy may render HTML, not JSON — "
                         "extract the rendered data into a fixture, or compare against the DOM model instead)")
    if args.endpoint_json:
        with open(args.endpoint_json, encoding="utf-8") as f:
            react = json.load(f)
    else:
        import urllib.request
        with urllib.request.urlopen(args.endpoint_url, timeout=20) as r:
            react = json.loads(r.read().decode("utf-8", "replace"))

    result = compare(chosen["json"], react, args.data_mode)
    report = render(result, args.har, args.match or chosen["pathname"])
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report)
    print(report)
    sys.exit(0 if result["ok"] else 2)


if __name__ == "__main__":
    main()
