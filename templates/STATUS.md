<!--
  STATUS.md  —  jsp2react control-plane (the single source of truth for a run)
  ----------------------------------------------------------------------------
  This file is the project dashboard. BOTH agents read it FIRST and write it LAST.
  - jsp2react-analyzer SEEDS it (config + screen inventory + coverage matrix).
  - jsp2react-builder CONSUMES it, implements ONE screen per iteration, and updates it.

  Rules:
  - Always read this file before doing anything. It tells you what is done and what is next.
  - Never advance "Current Iteration" past a screen whose parity is still failing and fixable.
  - Status values are STRICT (see legend). Never write `verified` without a passing parity report.
  - Keep this file small. Detail lives in spec.md and the per-screen artifacts.
  Replace every <ANGLE_BRACKET> placeholder. Delete the example rows once real ones exist.
-->

# jsp2react — Run Status

## 1. Project Config  (set once by analyzer; treat as runtime configuration)

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
| Evidence root | <ABS path to ./jsp2react-work>  (screenshots/, dom/, fixtures/, parity/) |

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

- **Login** is performed by the login step, NOT by these agents. <Describe: which skill/script, where creds live (e.g. /home/devpod/.copilot/BAX-BusinessAnalysis/.env), whether one manual SSO step is needed.>
- **Render-without-backend**: the React app is served by MSW from captured fixtures by default. Same endpoint paths are wired; live backend is opt-in only (data-wiring QA).
- **Parity gate**: PASS = 0 critical structural deltas AND pixel-mismatch ≤ threshold (see parity-thresholds.md). <note any tolerance override>
- **Component library**: none. Faithful HTML/CSS port only.
- <other decisions: FA/search context needed to reach screens, entitlements, env (dev/qa), etc.>

## 4. Screen Inventory  (one row per user-visible screen OR distinct state/control)

Granularity: a row per distinct screen, tab, sub-tab, modal, empty state, error state, and per distinct
control group. Split coarse rows the moment runtime evidence shows separate states. (Heuristic in spec.md.)

Status legend (STRICT):
`not-started` · `analyzed` (evidence captured, spec row written) · `in-progress` (coding) ·
`implemented` (code done, NOT yet parity-verified) · `verified` (parity report PASSED) ·
`blocked` (record the blocker) · `deferred` (out of this run's scope, with reason)

| ID | Family | Screen / State | Route / action (`.do`) | Depends on | Status | Evidence (shot/dom/fixture) | Parity | Notes |
|----|--------|----------------|------------------------|-----------|--------|------------------------------|--------|-------|
| F000 | shell | Login page | /BAA/jsp/login.jsp | — | analyzed | login.png / login.dom.html / — | — | pre-auth; example row |
| F001 | shell | Summary shell (post-login) | <action> | F000 | not-started | <…> | — | hydration wait ~10s |
| F010 | fa | FA Team Profile | fateamprofile.do | F001 | not-started | <…> | — | table; export PDF/Excel |
| … | … | … | … | … | … | … | … | … |

## 5. Coverage Matrix  (the completion gate — a run is NOT done until targets are met)

| Dimension | Discovered | Analyzed | Verified | % Verified | Target |
|---|---|---|---|---|---|
| Top-level families | <n> | <n> | <n> | <%> | 100% reachable |
| Screens | <n> | <n> | <n> | <%> | 100% reachable |
| Distinct states (tabs/empty/error/modal) | <n> | <n> | <n> | <%> | 100% reachable |
| Endpoints mapped (fixtures captured) | <n> | <n> | — | <%> | 100% of screens' endpoints |

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
