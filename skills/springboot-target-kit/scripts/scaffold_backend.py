#!/usr/bin/env python3
"""
scaffold_backend.py — generate a Spring Boot skeleton for one flow FROM backend-model.json.

Symmetric to react-replica-kit/scaffold_app.sh (the frontend target). From the stored-proc
contract that extract_backend.py produced, it writes the target layering:

    Controller (REST)  ->  Service (+Impl)  ->  Gateway (SimpleJdbcCall -> stored proc)  ->  DTO
    + an OpenAPI stub for the endpoint

The SP wiring, the declared param types, and the DTO field shape are DETERMINISTIC (from the
model). The Service body is a TODO the agent fills with the legacy business semantics — that part
is app-specific and is NOT auto-translated (see references/backend-layering.md).

Usage:
  python scaffold_backend.py --model <flow>/backend-model.json --out-dir <api>/src/main/java \
      --package com.example.app --project project.json
  python scaffold_backend.py --self-check        # generate from a synthetic model into a temp dir, assert
"""
import argparse, json, os, re, sys, tempfile

JDBC_TO_JAVA = {
    "VARCHAR": "String", "CHAR": "String", "NVARCHAR": "String", "LONGVARCHAR": "String", "CLOB": "String",
    "INTEGER": "Integer", "INT": "Integer", "SMALLINT": "Integer", "TINYINT": "Integer",
    "BIGINT": "Long", "DECIMAL": "java.math.BigDecimal", "NUMERIC": "java.math.BigDecimal",
    "DOUBLE": "Double", "FLOAT": "Double", "REAL": "Float",
    "DATE": "java.time.LocalDate", "TIME": "java.time.LocalTime", "TIMESTAMP": "java.time.LocalDateTime",
    "BIT": "Boolean", "BOOLEAN": "Boolean",
}
JDBC_TO_TYPES = {  # for java.sql.Types.* in declareParameters
    "VARCHAR": "VARCHAR", "CHAR": "CHAR", "INTEGER": "INTEGER", "INT": "INTEGER", "BIGINT": "BIGINT",
    "DECIMAL": "DECIMAL", "NUMERIC": "NUMERIC", "DATE": "DATE", "TIMESTAMP": "TIMESTAMP", "DOUBLE": "DOUBLE",
}


def camel(name):
    s = str(name)
    if re.search(r"[^A-Za-z0-9]", s):           # has separators -> snake/UPPER_CASE/etc: split + recombine
        parts = [p for p in re.split(r"[^A-Za-z0-9]+", s) if p]
        if not parts:
            return "col"
        return parts[0].lower() + "".join(p[:1].upper() + p[1:].lower() for p in parts[1:])
    if s.isupper():                              # single ALLCAPS token
        return s.lower()
    return s[:1].lower() + s[1:] if s else "col"  # already camel/Pascal -> preserve internal caps


def pascal(name):
    c = camel(name)
    return c[:1].upper() + c[1:]


def java_type(jdbc):
    return JDBC_TO_JAVA.get((jdbc or "").upper(), "String")


def types_const(jdbc):
    return "Types." + JDBC_TO_TYPES.get((jdbc or "").upper(), "VARCHAR")


def proc_parts(sp):
    """schema-qualified SP name -> (schema, proc). 'APP.GET_X' -> ('APP','GET_X')."""
    bits = [b for b in (sp or "").split(".") if b]
    if len(bits) >= 2:
        return bits[-2], bits[-1]
    return "", (bits[-1] if bits else "PROC")


def gen_dto(pkg, flow, cols):
    cls = pascal(flow) + "Dto"
    fields, getset = [], []
    for c in cols:
        jt = java_type(c.get("jdbcType"))
        fn = camel(c.get("property") or c.get("name"))
        fields.append("    private %s %s;   // column %s" % (jt, fn, c.get("name")))
        cap = fn[:1].upper() + fn[1:]
        getset.append("    public %s get%s() { return %s; }\n    public void set%s(%s v) { this.%s = v; }"
                      % (jt, cap, fn, cap, jt, fn))
    if not fields:
        fields.append("    // TODO(agent): no resultMap columns found in source — add fields from the captured response (HAR).")
    return cls, ("package %s.dto;\n\n/** Generated from backend-model.json — one field per stored-proc result column. */\npublic class %s {\n%s\n\n%s\n}\n"
                 % (pkg, cls, "\n".join(fields), "\n".join(getset)))


def gen_gateway(pkg, flow, proc):
    cls = pascal(flow) + "Gateway"
    dto = pascal(flow) + "Dto"
    schema, name = proc_parts(proc.get("sp"))
    in_params = proc.get("inParams", [])
    declare = ",\n            ".join(
        'new SqlParameter("%s", %s)' % (p["name"], types_const(p.get("jdbcType"))) for p in in_params) or "// no declared in-params"
    schema_line = ('\n                .withSchemaName("%s")' % schema) if schema else ""
    args = ", ".join("%s %s" % (java_type(p.get("jdbcType")), camel(p["name"])) for p in in_params)
    put = "\n        ".join('in.put("%s", %s);' % (p["name"], camel(p["name"])) for p in in_params)
    body = '''package {pkg}.gateway;

import {pkg}.dto.{dto};
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.simple.SimpleJdbcCall;
import org.springframework.stereotype.Repository;
import javax.sql.DataSource;
import java.sql.Types;
import java.util.*;

/** Calls the legacy stored procedure {sp} via SimpleJdbcCall — same SP the legacy DAO used. */
@Repository
public class {cls} {{

    private final SimpleJdbcCall call;

    @Autowired
    public {cls}(DataSource dataSource) {{
        this.call = new SimpleJdbcCall(dataSource){schema_line}
                .withProcedureName("{name}")
                .declareParameters(
            {declare});
        // ponytail: result-set mapping left to the agent — confirm the returned column keys against the HAR.
    }}

    @SuppressWarnings("unchecked")
    public List<{dto}> execute({args}) {{
        Map<String, Object> in = new HashMap<>();
        {put}
        Map<String, Object> out = call.execute(in);
        // TODO(agent): map the result-set rows (out.get("#result-set-1")) into {dto} per backend-model outColumns.
        List<{dto}> rows = new ArrayList<>();
        return rows;
    }}
}}
'''.format(pkg=pkg, dto=dto, cls=cls, sp=proc.get("sp", "?"), schema_line=schema_line, name=name,
           declare=declare, args=args, put=(put or "// no inputs"))
    return cls, body


def gen_service(pkg, flow, proc):
    iface = pascal(flow) + "Service"
    impl = iface + "Impl"
    dto = pascal(flow) + "Dto"
    gw = pascal(flow) + "Gateway"
    in_params = proc.get("inParams", []) if proc else []
    sig_args = ", ".join("%s %s" % (java_type(p.get("jdbcType")), camel(p["name"])) for p in in_params)
    call_args = ", ".join(camel(p["name"]) for p in in_params)
    iface_src = ("package %s.service;\n\nimport %s.dto.%s;\nimport java.util.List;\n\npublic interface %s {\n    List<%s> get%s(%s);\n}\n"
                 % (pkg, pkg, dto, iface, dto, pascal(flow), sig_args))
    impl_src = '''package {pkg}.service;

import {pkg}.dto.{dto};
import {pkg}.gateway.{gw};
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import java.util.List;

@Service
public class {impl} implements {iface} {{

    private final {gw} gateway;

    @Autowired
    public {impl}({gw} gateway) {{ this.gateway = gateway; }}

    @Override
    public List<{dto}> get{flow}({sig_args}) {{
        // TODO(agent): port the legacy service/builder business semantics here (filtering, derived
        // fields, formatting). Match legacy behavior BEFORE any improvement — verify against the HAR.
        return gateway.execute({call_args});
    }}
}}
'''.format(pkg=pkg, dto=dto, gw=gw, impl=impl, iface=iface, flow=pascal(flow),
           sig_args=sig_args, call_args=call_args)
    return iface, iface_src, impl, impl_src


def gen_controller(pkg, flow, proc):
    cls = pascal(flow) + "Controller"
    iface = pascal(flow) + "Service"
    dto = pascal(flow) + "Dto"
    route = re.sub(r"[^a-z0-9]+", "-", flow.lower()).strip("-")
    in_params = proc.get("inParams", []) if proc else []
    # request params get @RequestParam; session-sourced inputs get a TODO note
    req = [p for p in in_params if p.get("source") in ("param", "form")]
    sess = [p for p in in_params if p.get("source") == "session"]
    params = ", ".join('@RequestParam %s %s' % (java_type(p.get("jdbcType")), camel(p["name"])) for p in req)
    sess_note = ""
    if sess:
        sess_note = "\n        // TODO(agent): these come from the authenticated session/context, NOT query params: " + \
            ", ".join(camel(p["name"]) for p in sess) + " (see references/session-auth-state.md)."
    call_args = ", ".join(
        camel(p["name"]) if p.get("source") in ("param", "form") else "/*session*/ %s" % camel(p["name"])
        for p in in_params)
    body = '''package {pkg}.controller;

import {pkg}.dto.{dto};
import {pkg}.service.{iface};
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;
import java.util.List;

/** REST endpoint for the {flow} flow. Contract decoupled from JSP/Struts (clean DTO JSON). */
@RestController
@RequestMapping("/api/{route}")
public class {cls} {{

    private final {iface} service;

    @Autowired
    public {cls}({iface} service) {{ this.service = service; }}

    @GetMapping
    public List<{dto}> get({params}) {{{sess_note}
        return service.get{flowP}({call_args});
    }}
}}
'''.format(pkg=pkg, dto=dto, iface=iface, cls=cls, route=route or "flow", flow=flow,
           params=params, sess_note=sess_note, flowP=pascal(flow), call_args=call_args)
    return cls, route or "flow", body


def gen_openapi(flow, route, cols):
    def yt(c):
        return ("number" if java_type(c.get("jdbcType")) in
                ("java.math.BigDecimal", "Double", "Integer", "Long", "Float") else "string")
    props = "".join("                    %s:\n                      type: %s\n" %
                    (camel(c.get("property") or c.get("name")), yt(c)) for c in cols) \
        or "                    # TODO(agent): add properties from the HAR response\n"
    # expanded YAML (no inline braces — keeps it out of str.format's way)
    return ("openapi: 3.0.0\n"
            "info:\n"
            "  title: %s API\n"
            "  version: 0.1.0\n"
            "paths:\n"
            "  /api/%s:\n"
            "    get:\n"
            "      summary: %s flow (generated stub)\n"
            "      responses:\n"
            "        '200':\n"
            "          description: OK\n"
            "          content:\n"
            "            application/json:\n"
            "              schema:\n"
            "                type: array\n"
            "                items:\n"
            "                  type: object\n"
            "                  properties:\n%s" % (flow, route, flow, props))


def scaffold(model, out_dir, pkg):
    flow = pascal(model.get("flow") or "Flow")
    procs = model.get("storedProcs") or []
    proc = procs[0] if procs else {"sp": "", "inParams": [], "outColumns": []}
    cols = proc.get("outColumns", [])
    pkg_path = pkg.replace(".", "/")
    written = []

    def w(sub, fname, text):
        d = os.path.join(out_dir, pkg_path, sub)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, fname)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        written.append(p)
        return p

    dto_cls, dto_src = gen_dto(pkg, flow, cols)
    w("dto", dto_cls + ".java", dto_src)
    gw_cls, gw_src = gen_gateway(pkg, flow, proc)
    w("gateway", gw_cls + ".java", gw_src)
    iface, iface_src, impl, impl_src = gen_service(pkg, flow, proc)
    w("service", iface + ".java", iface_src)
    w("service", impl + ".java", impl_src)
    ctrl_cls, route, ctrl_src = gen_controller(pkg, flow, proc)
    w("controller", ctrl_cls + ".java", ctrl_src)
    # openapi at out_dir root (not under package)
    api_dir = os.path.join(out_dir, "..", "openapi")
    os.makedirs(api_dir, exist_ok=True)
    api_path = os.path.join(api_dir, route + ".openapi.yaml")
    with open(api_path, "w", encoding="utf-8") as f:
        f.write(gen_openapi(flow, route, cols))
    written.append(api_path)
    return written, route


def balanced(text):
    return text.count("{") == text.count("}") and text.count("(") == text.count(")")


def self_check():
    model = {
        "flow": "FaSummary",
        "storedProcs": [{
            "sp": "APP.GET_SUMMARY", "source": "sqlmap",
            "inParams": [{"name": "faNum", "jdbcType": "VARCHAR", "source": "session"},
                         {"name": "period", "jdbcType": "VARCHAR", "source": "param"}],
            "outColumns": [{"name": "FA_NAME", "jdbcType": "VARCHAR", "property": "faName"},
                           {"name": "YTD_AMT", "jdbcType": "DECIMAL", "property": "ytdAmt"}],
        }],
        "sessionInputs": ["faNum"], "requestParams": ["period"],
    }
    d = tempfile.mkdtemp(prefix="scaffold_backend_")
    out = os.path.join(d, "src", "main", "java")
    written, route = scaffold(model, out, "com.example.app")
    names = {os.path.basename(p) for p in written}
    for need in ("FaSummaryController.java", "FaSummaryService.java", "FaSummaryServiceImpl.java",
                 "FaSummaryGateway.java", "FaSummaryDto.java"):
        assert need in names, "missing " + need
    gw = next(p for p in written if p.endswith("Gateway.java"))
    gw_txt = open(gw, encoding="utf-8").read()
    assert 'withProcedureName("GET_SUMMARY")' in gw_txt, "SP not wired"
    assert 'withSchemaName("APP")' in gw_txt, "schema not wired"
    assert "Types.VARCHAR" in gw_txt, "param type not declared"
    dto = next(p for p in written if p.endswith("Dto.java"))
    dto_txt = open(dto, encoding="utf-8").read()
    assert "faName" in dto_txt and "ytdAmt" in dto_txt, "DTO fields missing"
    assert "java.math.BigDecimal ytdAmt" in dto_txt, "DECIMAL not mapped to BigDecimal"
    ctrl = open(next(p for p in written if p.endswith("Controller.java")), encoding="utf-8").read()
    assert "@RequestParam" in ctrl and "period" in ctrl, "request param not surfaced"
    assert "authenticated session" in ctrl and "faNum" in ctrl, "session input note missing"
    for p in written:
        if p.endswith(".java"):
            assert balanced(open(p, encoding="utf-8").read()), "unbalanced braces in " + p
    print(json.dumps({"self_check": "ok", "files": len(written), "route": route,
                      "sp_wired": True, "dto_fields": 2}))


def main():
    ap = argparse.ArgumentParser(description="Generate a Spring Boot skeleton (controller/service/gateway/DTO/OpenAPI) from backend-model.json.")
    ap.add_argument("--model", help="backend-model.json from extract_backend.py.")
    ap.add_argument("--out-dir", help="Target Java source root, e.g. <api>/src/main/java.")
    ap.add_argument("--package", default="com.example.app", help="Base Java package (default com.example.app).")
    ap.add_argument("--project", help="project.json (unused for now; reserved for targetBackendDir/package).")
    ap.add_argument("--check", action="store_true", help="Quick sanity (python present), exit.")
    ap.add_argument("--self-check", action="store_true", help="Generate from a synthetic model into a temp dir and assert, exit.")
    args = ap.parse_args()

    if args.check:
        print("scaffold_backend: ok (python %d.%d)" % sys.version_info[:2])
        return
    if args.self_check:
        self_check()
        return
    if not args.model or not args.out_dir:
        raise SystemExit("--model and --out-dir are required")
    with open(args.model, encoding="utf-8") as f:
        model = json.load(f)
    written, route = scaffold(model, args.out_dir, args.package)
    print("wrote %d files for flow '%s' (route /api/%s):" % (len(written), model.get("flow"), route))
    for p in written:
        print("  " + p)


if __name__ == "__main__":
    main()
