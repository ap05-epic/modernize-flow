# SETUP — standing up the modernization toolkit on the pod (by hand)

Fastest path: clone the repo and run **one command**, choosing a mode. The rest of this file explains what
that does and how to run your first flow. Later, DigitCode (`dc agent install modernize-flow`) replaces it.

```bash
git clone https://github.com/ap05-epic/jsp2react.git
cd jsp2react
bash install.sh full        # React + Spring Boot   (agent: modernize-flow)
# or
bash install.sh frontend    # React only — fallback (agent: jsp2react)
```

## 1. File tree

```
jsp2react/
├── install.sh                    # clean install, MODE = full | frontend
├── README.md
├── SETUP.md
├── docs/HOW-IT-WORKS.md
├── agents/
│   ├── modernize-flow.agent.md   # FULL: React + Spring Boot
│   └── jsp2react.agent.md        # FRONTEND fallback: React only
├── skills/
│   ├── legacy-crawl-capture/
│   │   ├── SKILL.md
│   │   ├── scripts/{extract_jsp.py, crawl_ajax.py, crawl_screens.py, capture_screen.py, capture_fixtures.py}
│   │   └── references/{jsp-source-extraction.md, ajax-crawl-and-viewgraph.md,
│   │                   struts-jsp-endpoint-mapping.md, runtime-readiness-and-auth.md}
│   ├── parity-verify/
│   │   ├── SKILL.md · package.json   # pixelmatch + pngjs (install.sh runs `npm install` here)
│   │   ├── scripts/{verify_screen.py, dom_diff.py, pixel_diff.js}
│   │   └── references/parity-thresholds.md
│   ├── react-replica-kit/
│   │   ├── SKILL.md
│   │   ├── scripts/{extract_theme.py, scaffold_app.sh, build_index.py, serve_review.py}
│   │   └── references/{jsp-to-react-mapping.md, css-porting.md, theme-extraction.md, backend-data-modes.md}
│   └── springboot-target-kit/        # FULL mode only
│       ├── SKILL.md
│       ├── scripts/{extract_backend.py, scaffold_backend.py, verify_contract.py}
│       └── references/{backend-layering.md, stored-procedure-mapping.md, session-auth-state.md}
├── templates/{status.md, spec.md, MANIFEST.json, capture-profile.json, project.json}
└── examples/baa.project.json
```

## 2. What `install.sh <mode>` does

A **clean install**: it removes this toolkit's managed skills + agents (and the retired v2 `jsp2react-analyzer`/
`jsp2react-builder`) from the target dirs, then installs exactly the chosen mode's set — so the pod never runs
stale files. It only touches files this toolkit owns (by name); your other `~/.copilot` skills/agents are safe.

| Step | full | frontend |
|---|---|---|
| skills → `~/.copilot/skills/` | legacy-crawl-capture, react-replica-kit, parity-verify, **springboot-target-kit** | the first three |
| agent → `~/.copilot/agents/` | `modernize-flow.agent.md` | `jsp2react.agent.md` |
| pixel deps | `npm install` in `parity-verify` (pixelmatch+pngjs) | same |
| checks | Node, Python 3 + Playwright, **JDK + Maven/Gradle** | Node, Python 3 + Playwright |

Override targets: `COPILOT_SKILLS_DIR=… COPILOT_AGENTS_DIR=… bash install.sh <mode>`. Templates are blueprints
the driver agent copies and fills itself — you don't edit them by hand (§5).

> **Revert / fallback:** v2 (frontend‑only) is tagged `v2.0-frontend-only` + branch `v2-backup`. Restore with
> `git reset --hard v2.0-frontend-only`, or just `bash install.sh frontend` for the functional fallback.

## 3. Prerequisites already on the pod (verify, don't install)

- **Python 3** with **Playwright** (`webapp-testing` uses it). If missing: `pip install playwright && playwright install chromium`.
- **Node 18+ / npm** (React app, Vite, `pixel_diff.js`).
- **FULL mode:** a **JDK 17+** and **Maven/Gradle** (or the target project's `./mvnw`) for the Spring Boot target,
  and a JDBC `DataSource` to the legacy DB.
- Skills present: `webapp-snapshot`, `webapp-testing`, `digimem` (optionally `playwright-cli`).

## 4. Open‑source dependencies to pull (manual, pinned)

| Package | Source | Install | Used by |
|---|---|---|---|
| `pixelmatch` | github.com/mapbox/pixelmatch | `npm i -D pixelmatch@^5.3.0` | `parity-verify/scripts/pixel_diff.js` |
| `pngjs` | github.com/lukeapage/pngjs | `npm i -D pngjs@^7.0.0` | `parity-verify/scripts/pixel_diff.js` |
| `msw` | github.com/mswjs/msw | `npm i -D msw@^2.0.0` | `react-replica-kit` (record‑mode HAR replay) |
| Vite + React + TS | github.com/vitejs/vite | `npm create vite@latest <app> -- --template react-ts` | `scaffold_app.sh` (runs this for you) |
| Spring Boot + `spring-jdbc` | start.spring.io | in the target backend's `pom.xml`/`build.gradle` | `springboot-target-kit` (gateway uses `SimpleJdbcCall`) |
| **Crawljax** (OPTIONAL) | github.com/crawljax/crawljax (Apache‑2.0) | download jar/CLI; run separately | exhaustive AJAX state‑graph, normalized into `viewgraph.json`. `crawl_ajax.py` already covers this — a booster, not required. |

> All the Python extractors (`extract_jsp`, `extract_theme`, `extract_backend`, …), `scaffold_backend.py`, and
> `build_index.py` are **stdlib Python** — no extra installs. `scaffold_app.sh` installs Vite/React/TS + `msw` +
> `pixelmatch`/`pngjs` into the React app for you; `install.sh` installs the pixel libs into `parity-verify`.

Verify the engines:
```bash
node   ~/.copilot/skills/parity-verify/scripts/pixel_diff.js --self-check        # {"self_check":"ok","identical_diff_pixels":0}
python ~/.copilot/skills/springboot-target-kit/scripts/extract_backend.py --self-check   # FULL mode
```

## 5. Configuration — `project.json` + the agent fills `status.md`

Two config surfaces, neither hand-filled screen-by-screen:
- **`project.json`** (machine config every script reads via `--project`) — the app-specific values: context root,
  `legacyBaseUrl`, `loginAction` + `loginFields`, `families`/`pathConventions`, `viewport`, `ports`, and (FULL)
  `db.sqlmapDir`. Copy `templates/project.json`, fill it (or start from `examples/baa.project.json`). This is what
  makes the toolkit **generic** — no app name is hardcoded in the scripts.
- **`status.md`** — the driver agent **creates and seeds it** on its first run; you do not hand-fill it. The only
  things a human supplies in the kickoff prompt are the **legacy URL**, **how to log in**, and the **`project.json`
  path** (source root + target paths optional — the agent discovers/defaults them). Edit `status.md` afterward only
  to override a default or scope the run.

## 6. First‑run smoke test — OPTIONAL manual wiring check (one flow, by hand)

Proves the pipeline works on the pod *before* you trust the agent with a full sweep. The autonomous run is §6b.

```bash
S=~/.copilot/skills ; P=work/project.json     # your filled project.json (from examples/baa.project.json)
# 0. sanity: every script answers --self-check without a browser
for f in legacy-crawl-capture/scripts/extract_jsp legacy-crawl-capture/scripts/crawl_ajax \
         legacy-crawl-capture/scripts/crawl_screens legacy-crawl-capture/scripts/capture_screen \
         react-replica-kit/scripts/extract_theme react-replica-kit/scripts/build_index \
         parity-verify/scripts/dom_diff springboot-target-kit/scripts/extract_backend \
         springboot-target-kit/scripts/scaffold_backend springboot-target-kit/scripts/verify_contract ; do
  python $S/$f.py --self-check ; done
node $S/parity-verify/scripts/pixel_diff.js --self-check

# 1. login once (the session everything reuses)
python $S/webapp-snapshot/scripts/save_auth_state.py --url <login-url> --output work/auth_state.json

# 2. THEME from the legacy CSS source (colors/fonts come from here)
python $S/react-replica-kit/scripts/extract_theme.py --css-dir <webapp>/theme --out-dir work/evidence/theme

# 3. DISCOVER views: static + AJAX (from the start) -> one viewgraph  (--project for the app taxonomy + login markers)
python $S/legacy-crawl-capture/scripts/crawl_screens.py --struts-config <…>/struts-config.xml \
  --webapp-dir <webapp> --project $P --out work/screens.json --emit-viewgraph work/static-viewgraph.json
python $S/legacy-crawl-capture/scripts/crawl_ajax.py --start-url <post-login start> --project $P \
  --auth-state work/auth_state.json --merge work/static-viewgraph.json --out work/evidence/viewgraph.json

# 4. PARSE one flow's JSP -> source-model.json (UI build input)
python $S/legacy-crawl-capture/scripts/extract_jsp.py --jsp <webapp>/jsp/<flow>.jsp \
  --webapp-dir <webapp> --out work/evidence/<flow>_default/source-model.json

# 5. CAPTURE that view (real responses via --record-har; error pages auto-quarantine to _rejected/)
python $S/legacy-crawl-capture/scripts/capture_screen.py --profile work/profiles/<flow>_default.json \
  --out-dir work/evidence/<flow>_default --name legacy --auth-state work/auth_state.json --project $P --record-har
#   -> check work/evidence/<flow>_default/legacy.capture.json has "usable": true (not an error page)

# 6. FRONTEND: real data (record) + scaffold the app with the theme + project defaults
python $S/legacy-crawl-capture/scripts/capture_fixtures.py \
  --har work/evidence/<flow>_default/legacy.har --out <app>/src/mocks/<flow>_default
bash $S/react-replica-kit/scripts/scaffold_app.sh <app> work/evidence/theme/theme.css $P    # once

# 7. (agent builds src/screens/<Flow> FROM source-model + theme, runs npm run dev, captures react with the SAME profile)
python $S/legacy-crawl-capture/scripts/capture_screen.py --profile work/profiles/<flow>_default.json \
  --url http://localhost:5173/#/<flow>_default --out-dir work/evidence/<flow>_default --name react

# 8. PROVE frontend parity (record = exact pixels; live = structure/style+data)
python $S/parity-verify/scripts/verify_screen.py \
  --legacy-model work/evidence/<flow>_default/legacy.model.json --legacy-png work/evidence/<flow>_default/legacy.png \
  --react-model  work/evidence/<flow>_default/react.model.json  --react-png  work/evidence/<flow>_default/react.png \
  --out-dir work/evidence/<flow>_default/parity --name <flow>_default --data-mode record --pixel-threshold 0.005

# 8b. FULL MODE — backend: trace the data layer, scaffold Spring Boot, verify the endpoint vs the legacy HAR
python $S/springboot-target-kit/scripts/extract_backend.py --action <src>/.../<Flow>Action.java \
  --source-dir <java-root> --project $P --out work/evidence/<flow>_default/backend-model.json
python $S/springboot-target-kit/scripts/scaffold_backend.py \
  --model work/evidence/<flow>_default/backend-model.json --out-dir <api>/src/main/java --package com.example.app
#   (agent fills the ServiceImpl business logic + result-set->DTO mapping + session binding, then runs the app)
curl -s 'http://localhost:8081/api/<flow>' > work/new_<flow>.json
python $S/springboot-target-kit/scripts/verify_contract.py --har work/evidence/<flow>_default/legacy.har \
  --endpoint-json work/new_<flow>.json --match /api/<flow> --data-mode record    # exit 0 = PASS

# 9. INDEX + review
python $S/react-replica-kit/scripts/build_index.py --manifest work/evidence/MANIFEST.json   # -> INDEX.html
python $S/react-replica-kit/scripts/serve_review.py --work-dir work/evidence --react-base-url http://localhost:5173
```

## 6b. What to type into Copilot (after `install.sh <mode>`)

Copilot auto-discovers the skills; invoke the agent by name. Use **`modernize-flow`** (full) or **`jsp2react`**
(frontend) — match the mode you installed.

**Step A — sanity check (no crawling):**
> "Read jsp2react/SETUP.md and README.md. Confirm the skills are under ~/.copilot/skills and the **<modernize-flow |
> jsp2react>** agent is discoverable, then run the §6 self‑checks (`--self-check`) and report results. Don't crawl yet."

**Step B — analyze (run once; builds the source‑driven contract for ALL flows). You give URL + login + project.json:**
> "Use the **<modernize-flow | jsp2react>** agent. Legacy URL = `<…>`. Log in via webapp-snapshot/save_auth_state.py
> (creds/auth_state at `<…>`). project.json = `<…>` (copied from examples/baa.project.json). Legacy source at `<…>`
> *(omit to discover)*. **Bootstrap status.md yourself**, then: run pre‑capture triage; **extract the theme**;
> **discover every view including AJAX** (crawl_screens --emit-viewgraph + crawl_ajax from the start → viewgraph.json
> — never open deep links directly); for each flow **parse its JSP → source-model.json**, capture evidence + the
> **REAL responses** (--record-har; error pages auto‑quarantine — look around again)**, and (FULL mode) **trace the
> data layer → backend-model.json** (extract_backend). Write spec.md + status.md + MANIFEST.json, then build_index →
> evidence/INDEX.html. Begin with the login flow + one flow, then continue across all flows."

**Step C — implement (run repeatedly; one control/slice per turn):**
> "Use the **<modernize-flow | jsp2react>** agent. Read status.md and implement the next slice end to end: build it
> 1:1 **from its source-model.json + theme tokens** (structure/labels/colors from source, screenshot only to verify);
> **(FULL) scaffold the Spring Boot endpoint from backend-model.json and fill the ServiceImpl with the legacy business
> logic + session binding**; wire **real data** for its data mode (record = HAR replay / live = proxy / api = the new
> endpoint); render + capture with the same profile; run parity-verify --data-mode (**and verify_contract vs the HAR,
> FULL**) and fix from the report until it PASSES; then update status.md + regenerate INDEX.html. Build the login
> flow first. Do one slice, then show me its parity report (+ contract report) and side‑by‑side."

Then: **"Continue with the next slice."** (repeat) — or, once you trust it,
**"Implement all remaining slices, verifying each before moving on; stop and tell me about any blocker."**

**Review:**
> "Run react-replica-kit/scripts/serve_review.py against the work dir and the running React app so I can review
> legacy vs React side by side."

## 7. Assumptions to verify on the pod (correct as needed)

1. `~/.copilot/skills/` is the skills dir and your Copilot agents dir is where your other agents live. Override with
   `COPILOT_SKILLS_DIR` / `COPILOT_AGENTS_DIR` if not.
2. `project.json` is filled (context root, login, families, and FULL: `db.sqlmapDir`). Legacy source (incl.
   `struts-config*.xml`, `.properties`, and FULL: the Java/DAO + sqlmaps) is readable.
3. Login yields a reusable `auth_state.json` (one manual SSO step may be needed — a pre‑step, not the agent loop).
4. Data is REAL in every mode: **record** replays the HAR; **live** proxies the real backend; **api** (FULL) is the
   new endpoint, checked against the HAR. Never hand‑author data. Use `cics-analysis` for COMMAREA/DB2 contracts only
   if that source is in scope.
5. Pixel‑exact JSP↔React isn't realistic; the frontend gate is **strict structural + data‑presence + (record) pixel /
   (live) style** (`--pixel-threshold` per view; never relax the structural gate). The backend gate
   (`verify_contract.py`) is **field/type/value vs the recorded HAR**.
6. Script CLIs here are the contract; if a reused pod skill's flags differ (OCR drift), run `--help` and adjust.

## 8. If something fails
- Script `--self-check` fails → missing Python/Playwright or Node deps (§3, §4).
- Capture `usable:false` / unstyled / error / missing data → it "rendered" but isn't real evidence. Usually a
  misleading direct `*.do` route (use the real login→dispatcher flow), CSS/JS 404s, or async data captured too early.
  Runbook: `legacy-crawl-capture/references/runtime-readiness-and-auth.md`.
- Pixel ratio huge → almost always a capture mismatch (viewport/data/fonts), not a real defect — `parity-thresholds.md`.
- **FULL: `verify_contract` finds no JSON oracle** → the legacy screen renders HTML, not JSON. Record the grid's AJAX
  XHR, or derive the expected JSON from the captured DOM model — see `springboot-target-kit/references/backend-layering.md`.
- **FULL: endpoint returns wrong/empty data** → check the gateway is calling the same SP with the same session/entity
  context the capture used; fix the result‑set→DTO mapping. `stored-procedure-mapping.md`.
- Login redirects reappear mid‑run → session expired; re‑run login; note it in `status.md`.
