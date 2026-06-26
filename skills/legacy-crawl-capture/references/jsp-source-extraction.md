# JSP source extraction — the build input (`source-model.json`)

v1 built from the screenshot and read the JSP only "to explain." v2 **builds from the JSP source**:
`extract_jsp.py` parses each JSP (and the `*.js` it references) into a `source-model.json` the builder
implements from. The screenshot/DOM then only *verify* the result. This is what stops the agent from
guessing structure off an image and is why final parity should be small deltas, not "whole UI missing."

## Run it
```bash
python scripts/extract_jsp.py --jsp <webapp>/jsp/fateamprofile.jsp --webapp-dir <webapp> \
  --out <evidence>/<id_state>/source-model.json
# quick check, no file needed:
python scripts/extract_jsp.py --self-check
```
Pragmatic regex parser, **stdlib only** (JSP with scriptlets/taglibs isn't valid XML, so a real
XML/AST parser chokes — regex is the robust pragmatic choice). `--webapp-dir` lets it resolve
`<script src>` and scan those JS files for AJAX endpoints.

## Schema (what the builder reads)
```jsonc
{
  "jsp": "jsp/fateamprofile.jsp",
  "taglibs":   [{"prefix":"c","uri":"…"}],                  // which tag families are in play
  "includes":  [{"type":"static|jsp:include|tiles:*","path":"…"}],  // composition graph -> components
  "loops":     [{"items":"${comp.rows}","var":"row","line":N}],     // -> .map() over the data field
  "conditionals":[{"kind":"if|when","test":"${row.active}","line":N}], // -> conditional render
  "forms":     [{"actions":["/fateamprofile.do"],
                 "fields":[{"tag":"html:text","property":"faNumber","type":"text"}]}], // -> controlled inputs, SAME name
  "ajaxEndpoints":[{"url":"/BAA/fadetail.do?tab=comp","via":"$.ajax url","source":"js/fa.js","context":"…"}],
  "messageKeys":[{"key":"fa.profile.title"}],               // exact copy (cross-ref the .properties bundle)
  "outputs":   [{"expr":"comp.total"}],                     // ${...} data bindings the screen shows
  "scripts":   ["js/fa.js"], "warnings": []
}
```

## How the builder uses each field
| source-model field | React translation |
|---|---|
| `loops[].items/var` | `data.rows.map(row => …)` |
| `conditionals[].test` | `{cond && <…/>}` / ternary |
| `forms[].fields[].property/type` | controlled `<input name="faNumber">` — keep the **ActionForm name** |
| `ajaxEndpoints[]` | `useEffect`→`apiFetch(url)` on the matching trigger; inject where the JSP did |
| `messageKeys[]` | exact label/validation strings (`[MSG:bundle:key]`) |
| `outputs[]` | the data fields to render from the (real) response |
| `includes[]` | shared fragment/Tiles → shared component |

## Rules
- The source model is the **structure source of truth**; the captured `model.json` **verifies** it. If they
  disagree, investigate (the JSP may branch on data the capture didn't exercise) — don't silently trust the image.
- Cross-check `ajaxEndpoints` against the captured HAR (authoritative for what actually fired) and the
  viewgraph's `triggeredEndpoints`.
- A JSP that yields an almost-empty model (pure layout/fragment) gets a `warnings` note — treat it as a shared
  layout component, not a screen.
- Custom/bespoke taglibs the regex doesn't know still surface as raw text in the JSP; read those by hand and
  record them in the spec as `[JSP:path:line]`.
