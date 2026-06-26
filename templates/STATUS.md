<!--
  STATUS.md  —  jsp2react control-plane (the single source of truth for a run)
  ----------------------------------------------------------------------------
  This file is the project dashboard. BOTH agents read it FIRST and write it LAST.
  - jsp2react-analyzer SEEDS it (config + screen inventory + coverage matrix).
  - jsp2react-builder CONSUMES it, implements ONE screen per iteration, and updates it.

  Autonomy: the HUMAN does NOT hand-fill this file. The analyzer CREATES and seeds it on first run, from
  the kickoff prompt (legacy URL + login) plus repo discovery and sensible defaults (see the analyzer
  agent §2). A human edits it only to OVERRIDE a default or steer scope. The <ANGLE_BRACKET> placeholders
  below show what the analyzer fills in — they are not a to-do list for a person.

  Rules:
  - Always read this file before doing anything. It tells you what is done and what is next.
  - Never advance "Current Iteration" past a screen whose parity is still failing and fixable.
  - Status values are STRICT (see legend). Never write `verified` without a passing parity report.
  - Keep this file small. Detail lives in spec.md and the per-screen artifacts.
-->

# jsp2react — Run Status

## 1. Project Config  (analyzer fills this on first run; human only overrides)
## ↳ Human-provided via the kickoff prompt: **Legacy app URL** + **login**. Everything else: discovered or defaulted.

| Key | Value |
|---|---|
| Project name | <e.g. BAA UI modernization> |
| Legacy app URL (entry) | <https://.../BAA/jsp/login.jsp> |
| Legacy source root | <ABS path, e.g. /home/devpod/.copilot/BAX-Test-MainRepo/BAX-BusinessAnalysis> |
| Legacy webapp dir | <…/BAA/src/main/webapp> |
| struts-config path(s) | <…/WEB-INF/struts-config*.xml> |
| message-bundle paths | <…/webapp/**/*.properties ; …/BAX-config/{env}/baa/resources> |
| Target React app path | <ABS path to scaffold, e.g. …/jsp2react-ui> |
| Run command (target) | <npm run dev>  →  serves on <http://localhost:5173> |
| Capture viewport | <1920x1080>  (used identically for legacy capture AND react render) |
| Evidence root | <ABS path to ./jsp2react-work/evidence>  (ONE folder per view: `<id>_<state>/` with legacy.* + react.* + source-model.json + nav-path.json + parity/) |
| Theme (from legacy CSS) | evidence/theme/theme.css + tokens.json  (extract_theme.py — colors/fonts come from here) |
| View graph | evidence/viewgraph.json  (every static + AJAX view, each with a from-start click-path) |
| Default data mode | <record | live>  (record = replay REAL recorded responses, exact parity; live = Vite proxy to real backend) |
| Live backend (for live mode) | <http://127.0.0.1:8080>  (Vite proxy target; VITE_BACKEND) |

## 2. Tool Config  (paths the scripts/skills resolve on this pod)

| Key | Value |
|---|---|
| Login: auth_state file | <…/auth_state.json>  (produced by the login step; see §3) |
| Login method | <auth-state | creds-form | env-bypass | token-query>  (see legacy-crawl-capture SKILL) |
| Skills root | <~/.copilot/skills> |
| webapp-snapshot scripts | <~/.copilot/skills/webapp-snapshot/scripts> |
| webapp-testing scripts | <~/.copilot/skills/webapp-testing/scripts> |
| legacy-crawl-capture scripts | <~/.copilot/skills/legacy-crawl-capture/scripts> |
| parity-verify scripts | <~/.copilot/skills/parity-verify/scripts> |
| react-replica-kit scripts | <~/.copilot/skills/react-replica-kit/scripts> |
| digimem domain | ui-legacy_modernization |

## 3. Key Decisions  (high-impact answers known upfront)

- **Build from SOURCE, not the image**: the builder implements each view from its `source-model.json` (JSP loops/forms/labels/AJAX endpoints, from extract_jsp.py) + the legacy `theme.css` tokens. The screenshot/DOM only VERIFY the result.
- **Real data, two modes** (Copilot picks per view): `record` = MSW replays the REAL responses recorded into responses.har at capture time (exact parity); `live` = Vite proxy forwards to the real backend (real-time data, structure/style parity). **No hand-authored/fake fixtures in either mode.**
- **Login** is rebuilt as a real screen (F000); the session it establishes authenticates backend data calls. <Describe: where creds live (e.g. …/BAX-BusinessAnalysis/login.env), the real login action, whether one manual SSO step is needed.>
- **Parity gate**: record mode → 0 critical structural deltas AND pixel ≤ threshold AND data present. live mode → 0 critical deltas AND style match AND data present (pixel advisory; live data drifts). See parity-thresholds.md.
- **Colors/fonts** come from the extracted legacy theme tokens (theme.css), not per-element guesses.
- **Component library**: none. Faithful HTML/CSS port only.
- <other decisions: FA/search context needed to reach screens, entitlements, env (dev/qa), etc.>

## 4. Screen Inventory  (one row per user-visible screen OR distinct state/control)

Granularity: a row per distinct view/state — including every AJAX-loaded view from `viewgraph.json`
(tabs, hover-menu items, dropdowns, drill-downs), not just static routes. Split coarse rows the moment
the viewgraph or runtime evidence shows separate states. Each row's evidence is one folder
(`evidence/<id>_<state>/`) holding legacy.*, react.*, source-model.json, nav-path.json, parity/.

Status legend (STRICT):
`not-started` · `analyzed` (evidence captured + source-model written) · `in-progress` (coding) ·
`implemented` (code done, NOT yet parity-verified) · `verified` (parity report PASSED) ·
`blocked` (record the blocker) · `deferred` (out of this run's scope, with reason)

| ID | Family | View / State | Reach from start (nav-path) | Data mode | Status | Evidence folder | Parity | Notes |
|----|--------|--------------|-----------------------------|-----------|--------|-----------------|--------|-------|
| f000_default | shell | Login page | navigate login.jsp | live | analyzed | evidence/f000_default/ | — | rebuilt; session feeds data |
| f001_default | shell | Summary shell (post-login) | login → submit | record | not-started | <…> | — | hydration wait ~10s |
| f010_default | fa | FA Summary (AB10) | login → search AB10 | record | not-started | <…> | — | from-start path; ~13s settle |
| f010_comp | fa | FA Summary ▸ Compensation tab | login → search AB10 → click Compensation | record | not-started | <…> | — | AJAX view (viewgraph) |
| … | … | … | … | … | … | … | … | … |

## 5. Coverage Matrix  (the completion gate — a run is NOT done until targets are met)

| Dimension | Discovered | Analyzed | Verified | % Verified | Target |
|---|---|---|---|---|---|
| Top-level families | <n> | <n> | <n> | <%> | 100% reachable |
| Views (static + AJAX, from viewgraph.json) | <n> | <n> | <n> | <%> | 100% reachable |
| AJAX views (tabs/menus/drilldowns) | <n> | <n> | <n> | <%> | 100% reachable |
| Source models extracted (extract_jsp.py) | <n> | <n> | — | <%> | 100% of views' JSPs |
| Theme extracted (extract_theme.py) | <yes/no> | — | — | — | once, app-wide |
| Endpoints recorded (HAR / real responses) | <n> | <n> | — | <%> | 100% of views' data calls |

Blocked/unreachable items MUST be listed in §7 with recovery attempts, or the run is incomplete.

## 6. Current Iteration

- **Now building:** <F0xx — screen name>   (exactly one screen unless explicitly batched)
- **Next up:** <F0xx, F0xx>  (per dependency order; never start a screen whose deps aren't `verified`)
- **Last completed:** <F0xx @ date>

## 7. Blockers & Notes  (what the next iteration must know)

| ID | Type (blocker/note) | Detail | Recovery attempts | State |
|----|---------------------|--------|-------------------|-------|
| — | — | — | — | — |

## 8. Completion Log

| Date | Screen(s) | From → To status | Parity result | Notes |
|------|-----------|------------------|---------------|-------|
| — | — | — | — | — |
