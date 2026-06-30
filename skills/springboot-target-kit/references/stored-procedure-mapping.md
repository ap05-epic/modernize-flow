# Stored-procedure mapping (legacy DAO → Spring Boot gateway)

`extract_backend.py` finds the stored proc and its contract; this is the reference for *reading* the legacy
source it parses and *writing* the gateway it scaffolds. The richest signal is the **sqlmap XML**, then
Spring `SimpleJdbcCall`, then raw JDBC.

## Where the SP contract lives in the legacy source (signal priority)

1. **iBATIS / MyBatis sqlmap XML** (best — typed params AND result columns, deterministically):
   ```xml
   <procedure id="getFaSummary" parameterMap="pm" resultMap="rm">{ call APP.GET_SUMMARY(?, ?) }</procedure>
   <parameterMap id="pm"> <parameter property="faNum" jdbcType="VARCHAR"/> ... </parameterMap>
   <resultMap   id="rm"> <result column="FA_NAME" property="faName" jdbcType="VARCHAR"/> ... </resultMap>
   ```
   MyBatis equivalent: `<select statementType="CALLABLE">{call …}</select>` with `#{prop,jdbcType=…}` inline
   params and a `resultMap`. Point `extract_backend.py --sqlmap-dir` at these (or set `db.sqlmapDir` in
   `project.json`).
2. **Spring `SimpleJdbcCall` / `JdbcTemplate`** in a DAO:
   `new SimpleJdbcCall(ds).withProcedureName("GET_FA_SUMMARY")` — gives the SP name (params often declared
   nearby with `declareParameters(new SqlParameter(...))`).
3. **Raw JDBC** `CallableStatement`: `con.prepareCall("{call APP.GET_SUMMARY(?, ?)}")` — SP name + the
   `?` count; types are inferred from the `setXxx(i, …)` calls (the extractor records the count; you confirm
   the types from the result usage).

## Param source resolution

`extract_backend.py` tags each in-param `source: session | param | form` by matching its name against the
session reads (`session.getAttribute`) and request reads (`request.getParameter`) it traced in the action.
This drives the controller: `param`/`form` → `@RequestParam`; `session` → bound from the authenticated
context (NOT a query param — see `session-auth-state.md`). Confirm anything the extractor marked `form`.

## JDBC type → Java/JSON (what the scaffold uses)

| jdbcType | Java (DTO) | JSON |
|---|---|---|
| VARCHAR/CHAR/CLOB | `String` | string |
| INTEGER/SMALLINT | `Integer` | number |
| BIGINT | `Long` | number |
| DECIMAL/NUMERIC | `java.math.BigDecimal` | number |
| DOUBLE/FLOAT | `Double` | number |
| DATE | `java.time.LocalDate` | string (ISO) |
| TIMESTAMP | `java.time.LocalDateTime` | string (ISO) |
| BIT/BOOLEAN | `Boolean` | bool |

## The result-set mapping you finish in the gateway

`SimpleJdbcCall.execute(in)` returns a `Map`; result sets are under `#result-set-1`, `#result-set-2`, …
(or named if you `returningResultSet("rows", rowMapper)`). Map each row to the DTO by column name from
`backend-model.outColumns`. Prefer an explicit `RowMapper`/`returningResultSet` over post-hoc Map digging.
Multiple result sets (`resultSets > 1`) → either multiple DTO lists or a composite DTO; note the choice.

## CICS / mainframe-backed procedures (only if COBOL/BMS source is in scope)

When the SP (or a feign/WS call behind it) is backed by a CICS program, the pod's separate `cics-analysis`
agent maps it. Use that mapping to name the contract precisely — keep it strictly for **wiring**:

| CICS / mainframe construct | REST/JSON contract |
|---|---|
| COMMAREA fields (PIC clauses) | request/response JSON fields (+ types) |
| `DECLARE TABLE` / DB2 columns | response object fields |
| `READ … RIDFLD` (by key) | `GET /resource/{id}` |
| `STARTBR/READNEXT` (browse) | paginated `GET /resource?page=` |

Visible copy, labels, columns, and validation text still come from the captured screen + `.properties`
bundles — never invented from a backend payload.
