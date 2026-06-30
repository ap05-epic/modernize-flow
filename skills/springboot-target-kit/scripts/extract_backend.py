#!/usr/bin/env python3
"""
extract_backend.py — reverse-engineer a legacy flow's DATA layer into backend-model.json.

The frontend side parses the JSP (extract_jsp.py); this parses the SERVER side: it traces
Struts action -> service/builder -> DAO -> stored procedure, and extracts the stored-proc
contract (name, typed input params, result-set columns) plus the session/request inputs the
flow depends on. That model is what scaffold_backend.py builds the Spring Boot target FROM
(controller/service/gateway/DTO), so the new endpoint reproduces the legacy data.

Deterministic, stdlib-only, pragmatic (regex/heuristic — NOT a Java compiler). It degrades
gracefully: each signal it can find contributes; missing pieces are noted, not fatal.

Source-signal priority (richest first):
  1. iBATIS / MyBatis sqlmap XML  — explicit {call SP(...)} + parameterMap (jdbcType) + resultMap (columns)
  2. Spring SimpleJdbcCall / JdbcTemplate  — .withProcedureName("SP")
  3. raw JDBC CallableStatement / prepareCall("{call SP(?,?)}")

Usage:
  python extract_backend.py --action <FaSummaryAction.java> --source-dir <java-root> \
      --sqlmap-dir <resources/sqlmaps> --project project.json --out <flow>/backend-model.json
  python extract_backend.py --self-check        # synthetic fixtures, no real source needed
"""
import argparse, json, os, re, sys, tempfile

# ---- regexes (tolerant; case varies across codebases) ------------------------------------
CALL_RE      = re.compile(r"\{?\s*call\s+([A-Za-z0-9_.$]+)\s*\(([^)]*)\)", re.I)
PREPARECALL  = re.compile(r"prepareCall\s*\(\s*[\"']([^\"']+)[\"']", re.I)
SIMPLEJDBC   = re.compile(r"\.with(?:Procedure|Function)Name\s*\(\s*[\"']([A-Za-z0-9_.$]+)[\"']", re.I)
STMT_REF     = re.compile(r"\b(?:queryForList|queryForObject|selectList|selectOne|insert|update|delete|execute|queryForMap)\s*\(\s*[\"']([A-Za-z0-9_.$]+)[\"']", re.I)
SESSION_GET  = re.compile(r"(?:getSession\(\)|session)\s*\.\s*getAttribute\s*\(\s*[\"']([^\"']+)[\"']", re.I)
REQ_PARAM    = re.compile(r"(?:request|req)\s*\.\s*getParameter\s*\(\s*[\"']([^\"']+)[\"']", re.I)
# class references worth following: service/builder/manager/delegate/dao layers
CLASS_REF    = re.compile(r"\b([A-Z][A-Za-z0-9_]*(?:Service|Builder|Manager|Delegate|BO|DAO|Dao|Repository))\b")
DAO_NAME     = re.compile(r"(?:DAO|Dao|Repository)$")

# iBATIS inline params  #prop#  or  #prop:VARCHAR#  ;  MyBatis  #{prop,jdbcType=VARCHAR}
IBATIS_PARAM = re.compile(r"#\{?\s*([A-Za-z0-9_.]+)\s*(?:[,:]\s*(?:jdbcType\s*=\s*)?([A-Za-z]+))?[^#}]*[}#]")
PARAM_TAG    = re.compile(r"<parameter\b([^>]*?)/?>", re.I)   # attrs parsed per-tag (order-independent) via _attr
RESULT_TAG   = re.compile(r"<result\b([^>]*?)/?>", re.I)


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def load_project(path):
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def index_java(source_dir):
    """Map simple class name -> file path, so we can follow a reference by class name."""
    idx = {}
    if not source_dir or not os.path.isdir(source_dir):
        return idx
    for dp, dns, fns in os.walk(source_dir):
        dns[:] = [d for d in dns if d not in (".git", "target", "build", "node_modules")]
        for fn in fns:
            if fn.endswith(".java"):
                idx.setdefault(fn[:-5], os.path.join(dp, fn))
    return idx


def parse_sqlmaps(sqlmap_dir):
    """statementId -> {sp, inParams[{name,jdbcType,source?}], outColumns[{name,jdbcType}], resultSets}.
    Handles iBATIS <procedure>/<statement statementType=CALLABLE> and MyBatis <select statementType=CALLABLE>."""
    out = {}
    if not sqlmap_dir or not os.path.isdir(sqlmap_dir):
        return out
    # statement blocks of any tag that may carry a CALLABLE/{call ...}
    block_re = re.compile(
        r"<(procedure|statement|select|insert|update)\b([^>]*)>(.*?)</\1>", re.I | re.S)
    for dp, _dns, fns in os.walk(sqlmap_dir):
        for fn in fns:
            if not fn.lower().endswith(".xml"):
                continue
            text = read(os.path.join(dp, fn))
            if "call" not in text.lower():
                continue
            # local parameterMaps / resultMaps in this file
            pmaps = _collect_maps(text, "parameterMap", PARAM_TAG)
            rmaps = _collect_result_maps(text)
            ns = re.search(r"<sqlMap\b[^>]*namespace\s*=\s*[\"']([^\"']+)[\"']", text, re.I)
            ns = ns.group(1) if ns else ""
            for m in block_re.finditer(text):
                attrs, body = m.group(2), m.group(3)
                call = CALL_RE.search(body)
                if not call and "callable" not in attrs.lower():
                    continue
                sid = _attr(attrs, "id")
                if not sid:
                    continue
                full_id = (ns + "." + sid) if ns else sid
                sp = call.group(1) if call else ""
                # in-params: explicit parameterMap ref, else inline #..# params
                pm_ref = _attr(attrs, "parameterMap")
                if pm_ref and pm_ref.split(".")[-1] in pmaps:
                    in_params = pmaps[pm_ref.split(".")[-1]]
                else:
                    in_params = _inline_params(body)
                # out-columns: explicit resultMap ref, else none (server-shaped)
                rm_ref = _attr(attrs, "resultMap")
                out_cols = rmaps.get(rm_ref.split(".")[-1], []) if rm_ref else []
                out[full_id] = {"sp": sp, "call": (call.group(0).strip() if call else ""),
                                "inParams": in_params, "outColumns": out_cols,
                                "resultSets": 1, "source": "sqlmap"}
                if sid not in out:           # also index by bare id for loose DAO refs
                    out[sid] = out[full_id]
    return out


def _attr(attrs, name):
    m = re.search(name + r"\s*=\s*[\"']([^\"']+)[\"']", attrs, re.I)
    return m.group(1) if m else ""


def _collect_maps(text, tag, tag_re):
    """parameterMap id -> [{name, jdbcType}]. Attributes parsed per <parameter> tag via _attr so order
    (property before/after jdbcType) doesn't matter."""
    maps = {}
    for m in re.finditer(r"<" + tag + r"\b[^>]*id\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</" + tag + r">",
                         text, re.I | re.S):
        mid, body = m.group(1), m.group(2)
        params = []
        for pm in tag_re.finditer(body):
            prop = _attr(pm.group(1), "property")
            if prop:
                params.append({"name": prop, "jdbcType": (_attr(pm.group(1), "jdbcType") or "VARCHAR").upper()})
        maps[mid] = params
    return maps


def _collect_result_maps(text):
    maps = {}
    for m in re.finditer(r"<resultMap\b[^>]*id\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</resultMap>",
                         text, re.I | re.S):
        mid, body = m.group(1), m.group(2)
        cols = []
        for rm in RESULT_TAG.finditer(body):
            col = _attr(rm.group(1), "column")
            if col:
                cols.append({"name": col, "jdbcType": (_attr(rm.group(1), "jdbcType") or "VARCHAR").upper(),
                             "property": _attr(rm.group(1), "property")})
        maps[mid] = cols
    return maps


def _inline_params(body):
    seen, params = set(), []
    for m in IBATIS_PARAM.finditer(body):
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)
        params.append({"name": name, "jdbcType": (m.group(2) or "").upper() or "VARCHAR"})
    return params


def parse_dao_java(text):
    """From a DAO .java body, pull stored-proc signals."""
    callables, stmt_refs, sjc = [], [], []
    for m in PREPARECALL.finditer(text):
        c = CALL_RE.search(m.group(1))
        if c:
            argc = len([a for a in c.group(2).split(",") if a.strip()])
            callables.append({"sp": c.group(1), "call": c.group(0).strip(), "argc": argc})
    for m in SIMPLEJDBC.finditer(text):
        sjc.append(m.group(1))
    for m in STMT_REF.finditer(text):
        stmt_refs.append(m.group(1))
    return {"callables": callables, "statementRefs": stmt_refs, "simpleJdbcCalls": sjc}


def trace(action_file, idx, max_depth=3):
    """Follow action -> service/builder -> DAO by class name. Collect chain + inputs + DAO files."""
    session_inputs, req_params, chain, dao_files, visited = [], [], [], [], set()

    def visit(name, file, depth):
        if not file or file in visited or depth > max_depth:
            return
        visited.add(file)
        text = read(file)
        for a in SESSION_GET.findall(text):
            if a not in session_inputs:
                session_inputs.append(a)
        for p in REQ_PARAM.findall(text):
            if p not in req_params:
                req_params.append(p)
        if DAO_NAME.search(name or ""):
            dao_files.append(file)
        for ref in set(CLASS_REF.findall(text)):
            if ref == name:
                continue
            if ref not in chain and DAO_NAME.search(ref) is None:
                chain.append(ref)
            visit(ref, idx.get(ref), depth + 1)

    aname = os.path.basename(action_file)[:-5] if action_file.endswith(".java") else action_file
    visit(aname, action_file if os.path.isfile(action_file) else idx.get(aname), 0)
    return {"serviceChain": chain, "daoFiles": dao_files,
            "sessionInputs": session_inputs, "requestParams": req_params}


def build_model(action_file, source_dir, sqlmap_dir, flow):
    idx = index_java(source_dir)
    sqlmaps = parse_sqlmaps(sqlmap_dir)
    tr = trace(action_file, idx)

    procs, notes = [], []
    seen_sp = set()

    def add_proc(p):
        key = (p.get("sp") or p.get("call") or json.dumps(p)).lower()
        if key in seen_sp:
            return
        seen_sp.add(key)
        # resolve param source against the traced inputs
        for ip in p.get("inParams", []):
            n = ip.get("name", "").lower()
            ip["source"] = ("session" if any(n == s.lower() for s in tr["sessionInputs"])
                            else "param" if any(n == r.lower() for r in tr["requestParams"])
                            else "form")
        procs.append(p)

    for daof in tr["daoFiles"]:
        dao = parse_dao_java(read(daof))
        for c in dao["callables"]:
            add_proc({"sp": c["sp"], "call": c["call"], "source": "callable",
                      "inParams": [{"name": "p%d" % (i + 1), "jdbcType": "VARCHAR"} for i in range(c["argc"])],
                      "outColumns": [], "resultSets": 1})
        for sp in dao["simpleJdbcCalls"]:
            add_proc({"sp": sp, "call": "{call %s(...)}" % sp, "source": "jdbctemplate",
                      "inParams": [], "outColumns": [], "resultSets": 1})
        for sid in dao["statementRefs"]:
            hit = sqlmaps.get(sid) or sqlmaps.get(sid.split(".")[-1])
            if hit:
                add_proc(dict(hit, flowStatement=sid))
    # sqlmaps referenced even if DAO tracing missed them — include any CALLABLE in the flow's maps
    if not procs and sqlmaps:
        for sid, hit in sqlmaps.items():
            if "." in sid and hit.get("sp"):
                add_proc(dict(hit, flowStatement=sid))
        if procs:
            notes.append("stored procs taken from sqlmap CALLABLE statements; DAO->statement link not resolved")

    if not procs:
        notes.append("no stored procedure found — flow may render from server-side beans only, or source/sqlmap dir not provided")

    return {
        "flow": flow or (os.path.basename(action_file).replace(".java", "") if action_file else "flow"),
        "action": {"class": os.path.basename(action_file).replace(".java", "") if action_file else "",
                   "file": action_file or ""},
        "serviceChain": tr["serviceChain"],
        "daoFiles": [os.path.basename(d) for d in tr["daoFiles"]],
        "storedProcs": procs,
        "sessionInputs": tr["sessionInputs"],
        "requestParams": tr["requestParams"],
        "notes": notes,
    }


# ---- self-check --------------------------------------------------------------------------
SAMPLE_ACTION = '''
package com.example.action;
import com.example.service.FaSummaryService;
public class FaSummaryAction extends BaseAction {
  public ActionForward execute(ActionMapping m, ActionForm f, HttpServletRequest request, HttpServletResponse r) {
    String faNum = (String) request.getSession().getAttribute("faNum");
    String period = request.getParameter("period");
    FaSummaryService svc = new FaSummaryService();
    request.setAttribute("rows", svc.getSummary(faNum, period));
    return m.findForward("success");
  }
}
'''
SAMPLE_SERVICE = '''
package com.example.service;
import com.example.dao.FaSummaryDao;
public class FaSummaryService {
  private FaSummaryDao dao = new FaSummaryDao();
  public java.util.List getSummary(String faNum, String period) { return dao.querySummary(faNum, period); }
}
'''
SAMPLE_DAO = '''
package com.example.dao;
public class FaSummaryDao extends SqlMapClientDaoSupport {
  public java.util.List querySummary(String faNum, String period) {
    return getSqlMapClientTemplate().queryForList("FaSummary.getFaSummary", buildParam(faNum, period));
  }
}
'''
SAMPLE_SQLMAP = '''<?xml version="1.0"?>
<sqlMap namespace="FaSummary">
  <parameterMap id="pm" class="map">
    <parameter property="faNum" jdbcType="VARCHAR"/>
    <parameter jdbcType="DATE" property="period"/>
  </parameterMap>
  <resultMap id="rm" class="map">
    <result column="FA_NAME" property="faName" jdbcType="VARCHAR"/>
    <result column="YTD_AMT" property="ytdAmt" jdbcType="DECIMAL"/>
  </resultMap>
  <procedure id="getFaSummary" parameterMap="pm" resultMap="rm">
    { call APP.GET_SUMMARY(?, ?) }
  </procedure>
</sqlMap>
'''


def self_check():
    d = tempfile.mkdtemp(prefix="extract_backend_")
    src = os.path.join(d, "src"); sql = os.path.join(d, "sqlmaps")
    os.makedirs(src); os.makedirs(sql)
    files = {"FaSummaryAction.java": SAMPLE_ACTION, "FaSummaryService.java": SAMPLE_SERVICE,
             "FaSummaryDao.java": SAMPLE_DAO}
    for fn, body in files.items():
        with open(os.path.join(src, fn), "w", encoding="utf-8") as f:
            f.write(body)
    with open(os.path.join(sql, "FaSummary.xml"), "w", encoding="utf-8") as f:
        f.write(SAMPLE_SQLMAP)

    model = build_model(os.path.join(src, "FaSummaryAction.java"), src, sql, "FaSummary")
    procs = model["storedProcs"]
    assert procs, "no stored proc extracted"
    sp = procs[0]
    assert sp["sp"] == "APP.GET_SUMMARY", sp.get("sp")
    names = [p["name"] for p in sp["inParams"]]
    assert "faNum" in names and "period" in names, names
    fa = next(p for p in sp["inParams"] if p["name"] == "faNum")
    assert fa["jdbcType"] == "VARCHAR" and fa["source"] == "session", fa
    per = next(p for p in sp["inParams"] if p["name"] == "period")
    assert per["jdbcType"] == "DATE", "parameterMap jdbcType not captured (order-independence): %s" % per
    cols = {c["name"]: c["jdbcType"] for c in sp["outColumns"]}
    assert cols.get("FA_NAME") == "VARCHAR" and cols.get("YTD_AMT") == "DECIMAL", "resultMap jdbcType not captured: %s" % cols
    assert "faNum" in model["sessionInputs"], model["sessionInputs"]
    assert "period" in model["requestParams"], model["requestParams"]
    assert "FaSummaryService" in model["serviceChain"], model["serviceChain"]
    print(json.dumps({"self_check": "ok", "sp": sp["sp"], "inParams": len(sp["inParams"]),
                      "outColumns": len(sp["outColumns"]), "sessionInputs": model["sessionInputs"],
                      "serviceChain": model["serviceChain"]}))


def main():
    ap = argparse.ArgumentParser(description="Trace a legacy flow's data layer (action->service->DAO->stored proc) into backend-model.json.")
    ap.add_argument("--action", help="The Struts action .java for the flow (entry point).")
    ap.add_argument("--source-dir", help="Java source root to resolve service/DAO classes by name.")
    ap.add_argument("--sqlmap-dir", help="iBATIS/MyBatis sqlmap XML dir (richest SP signal). Falls back to project.db.sqlmapDir.")
    ap.add_argument("--project", help="project.json (for db.sqlmapDir default).")
    ap.add_argument("--flow", help="Flow name for the model (default: action class name).")
    ap.add_argument("--out", help="Write backend-model.json here.")
    ap.add_argument("--self-check", action="store_true", help="Run on synthetic fixtures, print result, exit.")
    args = ap.parse_args()

    if args.self_check:
        self_check()
        return

    if not args.action and not (args.sqlmap_dir or args.project):
        raise SystemExit("need --action (with --source-dir) and/or --sqlmap-dir to extract a backend model")
    proj = load_project(args.project)
    sqlmap_dir = args.sqlmap_dir or (proj.get("db", {}) or {}).get("sqlmapDir") or ""
    model = build_model(args.action or "", args.source_dir or "", sqlmap_dir, args.flow)
    text = json.dumps(model, indent=2)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print("wrote %s (storedProcs=%d, sessionInputs=%d)" %
              (args.out, len(model["storedProcs"]), len(model["sessionInputs"])))
    else:
        print(text)


if __name__ == "__main__":
    main()
