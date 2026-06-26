# jsp2react — Legacy JSP/Struts UI → React+TS, with proven 1:1 fidelity

A **skills + agents** system for GitHub Copilot CLI (GPT‑5.4). Given a legacy JSP/Java/Struts web app's
URL, it logs in, **extracts the real color/font theme**, discovers **every view including AJAX-loaded ones**
(reached from the start), **parses each JSP into a source model**, builds a **React + TypeScript 1:1 replica
from that source**, feeds it the **real backend data**, and **proves** each match deterministically — then
serves originals next to replicas for review.

It is the live-app analog of **fig2code** (Figma→code): same conventions and status‑driven loop, but it is
**source-driven** — the build input is the *JSP/AJAX/CSS source*, and the running screen is the verification
target (not a static design, and not a screenshot the AI guesses from).

## Quick start (manual phase)

```bash
git clone https://github.com/ap05-epic/jsp2react.git
cd jsp2react
bash install.sh        # copies skills+agents into ~/.copilot, installs pixel-diff deps, checks prereqs
```
Then in Copilot, run the **jsp2react-analyzer** agent and give it just the **legacy URL + how to log in** —
it bootstraps `STATUS.md` itself (no hand-editing) and captures every screen. Then run **jsp2react-builder**
repeatedly to build + verify one screen at a time (exact prompts in [SETUP.md §6b](SETUP.md)). Prereqs the
installer checks for: Node.js, Python 3 + Playwright. *(Later, `dc agent install jsp2react` replaces `install.sh`.)*

## How it works (two agents, one contract, three skills)

```
                 ┌────────────────────────── STATUS.md  (control plane) ──────────────────────────┐
                 │                            spec.md    (screen catalog / parity contract)        │
                 │                            MANIFEST.json (artifact ledger)                      │
                 └───────────────▲───────────────────────────────────────────────▲────────────────┘
                                 │ seeds                                          │ reads/updates
   ┌─────────────────────────────┴───────────┐               ┌──────────────────┴──────────────────────┐
   │  jsp2react-analyzer  (Agent 1)           │   handoff     │  jsp2react-builder  (Agent 2, fig2code)   │
   │  login → extract theme → discover every  │ ────────────▶ │  per view: build 1:1 FROM source-model +  │
   │  view (static+AJAX) → parse JSP→source-  │               │  theme → wire REAL data (record/live) →   │
   │  model → capture + record REAL responses │               │  PROVE parity → fix → verify              │
   └───────────────┬──────────────────────────┘               └──────────────┬────────────────────────────┘
                   │ uses                                                     │ uses
        ┌──────────┴───────────┐                          ┌──────────────────┴──────────┬──────────────────┐
        │ legacy-crawl-capture │                          │ parity-verify (proof engine) │ react-replica-kit │
        │ parse+discover+capture│                         │ pixel+DOM+data-presence diff │ theme+app+data+index│
        └──────────────────────┘                          └──────────────────────────────┴───────────────────┘
        reuses pod skills: webapp-snapshot (login/screenshots) · webapp-testing (Playwright/server) · digimem
```

**The loop (per view, status‑driven so it never drifts over a long sweep):**
`READ STATUS.md → READ source-model + theme + evidence → IMPLEMENT 1:1 FROM SOURCE → wire REAL data
(record HAR replay / live proxy) → verify_screen.py (pixel + DOM + data-presence) → FIX from the concrete
delta report → re‑verify → mark verified → regenerate INDEX.html.`

## How each non‑negotiable is met

| Requirement | Where it's enforced |
|---|---|
| **Built from source, not the image** | `extract_jsp.py` → `source-model.json` is the builder's input (loops/forms/labels/AJAX endpoints); the screenshot only verifies. Stops the AI guessing structure off a picture. |
| **1:1 fidelity** | `parity-verify` DOM lane = strict (copy, labels, field/tab order, columns, validation must match exactly); evidence‑tagged spec; "never infer a view you haven't captured or parsed". |
| **Every view found (incl. AJAX)** | `crawl_ajax.py` walks UI states from the start (tabs/menus/drilldowns), reconciled with the static `crawl_screens.py` inventory into `viewgraph.json`; each view carries a from-start click-path. |
| **Right colors/fonts** | `extract_theme.py` harvests the legacy palette/fonts from the CSS source into `theme.css` tokens the app styles from — no per-element guessing. |
| **No new artifacts** | Fresh app, **no component library**; faithful HTML/CSS port; reuse legacy assets; explicit may/may‑not‑change rules in `jsp-to-react-mapping.md`. |
| **Real data, never fakes** | Two modes, per view: **record** replays the REAL responses recorded to HAR (exact parity); **live** proxies the real backend via Vite (real-time). No hand-authored data. Login (F000) is rebuilt so its session authorizes the calls. |
| **No wrong pages accepted** | `capture_screen.py` checks the HTTP status + error signatures and **quarantines** error/half-loaded pages to `_rejected/`; they're never promoted as the view. |
| **Fidelity proven, not claimed** | Deterministic gate (`verify_screen.py`, exit 0/2): 0 critical structural deltas **and** data present **and** (record) pixel ≤ threshold / (live) style match — numeric report + located diff regions + side‑by‑side. The model **fixes from findings**; it does not judge by eye. |
| **Holds up over long multi‑view runs** | One view per iteration, STATUS.md coverage matrix + strict status semantics + recover‑before‑blocker + source-backed debugging + continue‑while‑reachable rules. |

## What's here

```
jsp2react/
├── install.sh           ← one command: places skills+agents + installs deps (manual phase)
├── README.md            ← you are here (technical entry point)
├── SETUP.md             ← detailed stand-up + the Copilot prompts (read this next)
├── docs/
│   └── HOW-IT-WORKS.md  ← plain-English explainer (use this to understand it / show colleagues)
├── agents/              ← jsp2react-analyzer.agent.md · jsp2react-builder.agent.md
├── skills/              ← legacy-crawl-capture · parity-verify · react-replica-kit (each a SKILL.md + scripts)
└── templates/           ← STATUS.md · spec.md · MANIFEST.json · capture-profile.json (copied into a run)
```

New here? Read **[docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md)** first — it explains the whole thing in
plain language.

## Reuse & open source

Reuses the pod's existing skills rather than reinventing them: `webapp-snapshot` (login via
`save_auth_state.py`, screenshots), `webapp-testing` (Playwright + `with_server.py`), `digimem` (team
memory). Pulls three MIT open‑source packages, all installed manually (see SETUP.md): **pixelmatch** +
**pngjs** (pixel diff), **MSW** (fixture rendering), and **Vite/React/TypeScript** (scaffold).

## Limitations & optional upgrades (deliberately not in the running system)

Kept out on purpose to keep the agents simple for GPT‑5.4 — noted here as *human* escape hatches, not
agent steps:

- **AJAX discovery** is done by the built-in `crawl_ajax.py` (Playwright, from-the-start state walk). For an
  even more exhaustive automated state graph you can run **[Crawljax](https://github.com/crawljax/crawljax)**
  (Apache‑2.0, JVM) offline and fold its states into `viewgraph.json` via `crawl_ajax.py --merge` — it's an
  optional booster (a stale, heavy JVM tool), not required.
- **Pixel diffing** uses `pixelmatch`. If the diff step ever bottlenecks at huge scale (1000+ snapshots),
  **[odiff](https://github.com/dmtrKovalenko/odiff)** is ~8× faster and could swap into `pixel_diff.js`.
- **JSP parsing** is pragmatic (regex/heuristic, stdlib). For bespoke taglibs a heavier ANTLR AST + codemod
  pipeline could be added later; deliberately deferred to keep the analyzer dependency-free.

## Out of scope (so omissions aren't mistaken for gaps)

Back‑end/Spring modernization; responsive/mobile breakpoints (legacy is fixed‑viewport); accessibility
remediation; animation modeling; CI wiring. The replica targets the legacy desktop viewport at parity.
