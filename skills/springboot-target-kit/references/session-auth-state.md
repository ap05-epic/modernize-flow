# Session, auth & state model (the part that is NOT JSP-to-React)

Legacy modernization is not just JSP→React + SP→gateway. Most flows depend on **server-side state** that the
old app carried implicitly. Flatten it into naive query params and the new endpoint looks right but is wrong
(wrong user's data, missing entitlement check, broken drill-down). `extract_backend.py` surfaces the inputs;
**you** decide how each is carried.

## Identify, per flow, whether it depends on:

- **authenticated user session** — who is logged in (drives entitlements + audit).
- **current viewing entity** — the FA / client / account / org the screen is scoped to.
- **selected split or sub-entity** — a secondary selection within the entity.
- **selected period / filter context** — usually a real request param (safe to pass).
- **entitlements / authorization** — can this user see this entity? (legacy often checks in the action/base).
- **legacy handoff cookies** — cookies the old pages set to hand off context to one another (and that the
  React app must preserve while some screens remain legacy).

The extractor lists these as `sessionInputs` (from `session.getAttribute`) and `requestParams` (from
`request.getParameter`). **Rule of thumb:** `requestParams` → `@RequestParam`; `sessionInputs` → bound from
the authenticated context, never accepted from the client.

## The rule (from the modernize-flow contract)

> **Never flatten stateful legacy behavior into naive query params without documenting the tradeoff.**

If you intentionally simplify auth/session for a POC (e.g. pass `faNum` as a query param instead of deriving
it from the session), you MUST record it in `spec.md` (§6 Shared State/Auth/Session), `status.md` (Decisions),
and the demo/runbook. If parity requires session-backed context, implement it as session-backed context.

## How to carry each input in Spring Boot

| Legacy source | Target binding |
|---|---|
| `session.getAttribute("userId")` | `SecurityContextHolder` principal, or a `@SessionScope` context bean |
| `session.getAttribute("faNum")` (selected entity) | a request-scoped **context filter** populated from session/security, injected into the service — NOT a `@RequestParam` |
| `request.getParameter("period")` | `@RequestParam` (genuine user input) |
| entitlement check in a base action / auth filter | a Spring Security check (`@PreAuthorize`) or an explicit service guard that reproduces the legacy rule |
| legacy handoff cookie | the Vite proxy already forwards cookies (`cookieDomainRewrite`); keep them flowing so half-migrated flows still hand off. See react-replica-kit `references/backend-data-modes.md`. |

## Login / session bootstrap

The React app rebuilds the **Login screen** and posts the real login action, establishing the session the
backend calls reuse (frontend side: `scaffold_app.sh` seeds it; field names come from `project.loginFields`).
For the Spring Boot side in a POC you may reuse that same session (forward the cookie) rather than
reimplementing SSO — **document it** as a POC simplification per the rule above.

## Verify state, not just shape

When you run `verify_contract.py`, make sure the new endpoint was called **with the same session/entity
context** the legacy capture used (same logged-in user, same selected FA). Otherwise you are comparing two
different users' data and the field/value diff is meaningless.
