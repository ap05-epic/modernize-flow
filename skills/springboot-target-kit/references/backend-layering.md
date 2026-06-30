# Target backend layering (React → Spring Boot → stored procedure)

The modernized flow keeps the legacy **business semantics** but replaces the presentation + controller
layers. Target layering (the order `scaffold_backend.py` generates, and the order to keep):

```
React page/components
  → frontend API client (src/api.ts; same paths as the new controller)
  → Spring Boot @RestController          # one endpoint per flow/slice
  → @Service (interface + impl)          # business semantics ported from the legacy service/builder
  → @Repository gateway (SimpleJdbcCall) # calls the SAME stored procedure the legacy DAO used
  → legacy DB / stored procedure
```

## What is generated vs. what you (the agent) write

`extract_backend.py` → `backend-model.json` (deterministic: SP name, typed in-params, result columns,
session/request inputs). `scaffold_backend.py` → the **skeleton** of all five files, with the SP wired
into the gateway and the DTO fields shaped from the result columns. **You fill:**

| File | Generated | You write |
|---|---|---|
| `<Flow>Dto.java` | one field per result column, typed | add any fields the HAR shows but the resultMap missed |
| `<Flow>Gateway.java` | `SimpleJdbcCall` + declared params | the result-set → DTO row mapping (`out.get("#result-set-1")`) |
| `<Flow>ServiceImpl.java` | calls the gateway | **the legacy business logic** (filtering, derived fields, formatting, ordering) |
| `<Flow>Controller.java` | REST endpoint, `@RequestParam` for request inputs | bind the session-sourced inputs (see `session-auth-state.md`) |
| `<flow>.openapi.yaml` | endpoint + response stub | tighten types / add error responses |

## Rules (from the modernize-flow contract)

1. **Preserve business semantics** even though the UI architecture changes. Match legacy behavior
   **before** inventing improvements; if you deviate, document it in `spec.md`, `status.md`, and the summary.
2. **Do not leak JSP/Struts into the API.** No `.do`, no `ActionForm`, no forward names, no Tiles concepts
   in the REST contract. The controller speaks clean DTO JSON; the gateway speaks SQL/SP.
3. **Keep the API contract decoupled from the UI.** The DTO is shaped by the data (the stored-proc result
   columns / the recorded response), not by what one screen happens to render.
4. **Reuse the target codebase's conventions** if a Spring Boot app already exists (package layout, base
   classes, datasource bean, error handling). `scaffold_backend.py --package <pkg>` sets the base package;
   inspect existing controllers/services first and match them.
5. **Verify against the legacy data, not by eye.** Run `verify_contract.py --har <view>/legacy.har
   --endpoint-json <new-response>` — the recorded legacy response is the oracle (record = field+type+values;
   live = structure only). Fix the gateway/DTO mapping from the concrete delta until it PASSES.

## When the legacy screen has no JSON endpoint

Many Struts screens render data **server-side into HTML** (the JSP iterates a bean). There is no JSON HAR
entry to use as the oracle. Two options, in order:
- If a later **AJAX/dataTables XHR** loads the grid, that XHR's response IS the JSON oracle — record it.
- Otherwise extract the rendered data from the captured **DOM model** (`model.json` table headers + rows)
  into a small expected-JSON fixture by hand, and compare the new endpoint against that. Note it in
  `spec.md` as a hand-derived oracle.
