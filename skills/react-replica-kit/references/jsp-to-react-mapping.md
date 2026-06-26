# JSP / Struts / Dojo → React + TS mapping

The legacy DOM (what Dojo/jQuery/JSP produced at runtime) is the target. Port the **rendered result**,
not the framework. The captured `model.json` + `dom.html` show exactly what to reproduce; the JSP/JS
source explains structure, conditionals, and behavior.

## Construct mapping

| Legacy construct | Rendered as | React + TS equivalent | Notes |
|---|---|---|---|
| `<%@ include file="x.jspf" %>` / Tiles insert | inline fragment | child component `<X/>` | one fragment → one component; keep the same DOM nesting |
| `<c:if test>` / `<% if %>` scriptlet | conditional region | `{cond && <…/>}` / ternary | drive from fixture/state, never invent the branch |
| `<c:forEach items>` / JSP loop | repeated rows | `items.map(...)` | same element shape per row |
| Struts `<html:form action="x.do">` + ActionForm | `<form>` POST | controlled `<form onSubmit>` → POST same `x.do` | keep field `name`s identical (they're the contract) |
| `<html:text property="acct"/>` | `<input name="acct">` | `<input name="acct" value=… onChange=…/>` | name/type/placeholder must match exactly |
| jQuery dataTables / clusterize grid | `<table>` with thead/tbody | plain `<table>` (or minimal virtualized list) | columns IN ORDER; no library that restyles |
| Dojo widget (dijit) | the DOM it expands to | plain elements matching that DOM | inspect captured `dom.html`; reproduce output, drop Dojo |
| `<bean:message key="x"/>` / `.properties` lookup | resolved label text | the **exact captured string** as a literal | do NOT re-translate or "improve" copy |
| server-rendered data baked in HTML | static text/rows | render from fixture (`data.ts`) | same values the screenshot showed |
| later XHR/ajax populating a region | dynamic content | `useEffect`→fetch same path; MSW returns fixture | same endpoint path |
| `<img src="platform/images/x.svg">` | icon/image | `<img src="/assets/x.svg">` reuse the SAME asset | copy the asset; never recreate it |
| inline `onclick="location.href='y.do'"` | navigation | `onClick`→ route/POST to same target | preserve the action/target |

## "No new artifacts" — the hard rules

You may ONLY change the framework. You may NOT change what the user sees.

**Must match exactly** (DOM-lane gate enforces): every visible label and copy string, field order, tab
order, table columns (set + order + header text), validation/error text, the set of controls, the set of
visible elements, and reused asset identity.

**Must not do:** add a control/link/tooltip/empty-state the legacy screen doesn't have; remove one it
does; reword, re-case, or re-translate any copy; reorder fields or columns; swap an icon; introduce a
component-library look; add spacing/padding "to make it nicer"; collapse two states into one.

**May do:** use React/TS idioms (components, hooks, props, state), CSS Modules class names of your choosing
(the *class name* is internal; the *computed style* must match), and a router. Internal structure is free;
observable output is frozen.

## Forms & data wiring

- Keep input `name` attributes identical to the ActionForm properties — they are the request contract and
  the parity key.
- Submit to the same `*.do` / REST path. With MSW on, the fixture answers; with `VITE_MSW=off`, the real
  backend answers — both use the same path, so wiring is proven without a backend at render time.
- Validation messages come from the captured screen / `.properties` (`[MSG:bundle:key]`) — reproduce the
  exact text and the exact trigger condition; don't invent client validation the legacy screen lacks.

## When evidence is incomplete

If a visible state has no captured screenshot/DOM, STOP and capture it (analyzer) — do not infer layout,
copy, columns, or controls from a backend payload or an adjacent screen. (Mirrors fig2code's Missing
State Protocol and the team's "no visual inference" rule.)
