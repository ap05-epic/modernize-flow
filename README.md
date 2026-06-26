# jsp2react — Legacy JSP/Struts UI → React+TS, with proven 1:1 fidelity

A **skills + agents** system for GitHub Copilot CLI (GPT‑5.4). Given a legacy JSP/Java/Struts web app's
URL, it logs in, reaches and reproduces **every** screen, builds a **React + TypeScript 1:1 replica** of
each, and **proves** each match deterministically — then serves originals next to replicas for review.

It is the live-app analog of **fig2code** (Figma→code): same conventions and status‑driven loop, but the
source of truth is a *running legacy screen + its JSP/Struts source*, not a static design.

## How it works (two agents, one contract, three skills)

```
                 ┌────────────────────────── STATUS.md  (control plane) ──────────────────────────┐
                 │                            spec.md    (screen catalog / parity contract)        │
                 │                            MANIFEST.json (artifact ledger)                      │
                 └───────────────▲───────────────────────────────────────────────▲────────────────┘
                                 │ seeds                                          │ reads/updates
   ┌─────────────────────────────┴───────────┐               ┌──────────────────┴──────────────────────┐
   │  jsp2react-analyzer  (Agent 1)           │   handoff     │  jsp2react-builder  (Agent 2, fig2code)   │
   │  login → crawl every screen → capture    │ ────────────▶ │  per screen: port 1:1 → render from MSW    │
   │  evidence → map endpoints → fixtures      │               │  fixtures → PROVE parity → fix → verify    │
   └───────────────┬──────────────────────────┘               └──────────────┬────────────────────────────┘
                   │ uses                                                     │ uses
        ┌──────────┴───────────┐                          ┌──────────────────┴──────────┬──────────────────┐
        │ legacy-crawl-capture │                          │ parity-verify (proof engine) │ react-replica-kit │
        │ discover + capture   │                          │ deterministic pixel+DOM diff │ scaffold+MSW+review│
        └──────────────────────┘                          └──────────────────────────────┴───────────────────┘
        reuses pod skills: webapp-snapshot (login/screenshots) · webapp-testing (Playwright/server) · digimem
```

**The loop (per screen, status‑driven so it never drifts over a long sweep):**
`READ STATUS.md → MAP states to captured evidence → IMPLEMENT 1:1 → render from MSW fixtures →
verify_screen.py (pixel + DOM diff) → FIX from the concrete delta report → re‑verify → mark verified.`

## How each non‑negotiable is met

| Requirement | Where it's enforced |
|---|---|
| **1:1 fidelity** | `parity-verify` DOM lane = strict (copy, labels, field/tab order, columns, validation must match exactly); evidence‑tagged spec; "never infer a visible state". |
| **No new artifacts** | Fresh app, **no component library**; faithful HTML/CSS port; reuse legacy assets; explicit may/may‑not‑change rules in `jsp-to-react-mapping.md`. |
| **UI only / backend not a render dependency** | React renders from **captured MSW fixtures**; live backend is opt‑in (`VITE_MSW=off`) for data‑wiring QA only. |
| **Fidelity proven, not claimed** | Deterministic gate (`verify_screen.py`, exit 0/2): pixel mismatch ≤ threshold **and** 0 critical structural deltas, with a numeric report + located diff regions + side‑by‑side image. The model **fixes from findings**; it does not judge by eye. |
| **Same (mainframe) endpoints / same data** | Analyzer maps the 3 backend layers (Struts `.do` / Spring REST / WS‑feign→mainframe); replica wires the same paths; fixtures are the captured responses. |
| **Holds up over long multi‑screen runs** | One screen per iteration, STATUS.md coverage matrix + strict status semantics + recover‑before‑blocker + continue‑while‑reachable rules. |

## What's here

```
jsp2react/
├── README.md            ← you are here (technical entry point)
├── SETUP.md             ← how to stand this up on the pod by hand + the Copilot prompts (read this next)
├── docs/
│   └── HOW-IT-WORKS.md  ← plain-English explainer (use this to understand it / show colleagues)
├── agents/              ← the two operating manuals (Copilot agents)
├── skills/              ← legacy-crawl-capture · parity-verify · react-replica-kit
└── templates/           ← STATUS.md · spec.md · MANIFEST.json (copied into a run)
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

- **Screen discovery** is the lightest part: the analyzer uses `struts-config.xml` + a link scan + live
  menu traversal. If a screen is only reachable through complex dynamic JS and the crawler misses it, a
  person can run **[Crawljax](https://github.com/crawljax/crawljax)** (Apache‑2.0, JVM) offline to get a
  state‑flow map, then feed those routes into the screen list. Not wired in — it's a stale (2023), heavy
  tool that would just distract the agent.
- **Pixel diffing** uses `pixelmatch`. If the diff step ever bottlenecks at huge scale (1000+ snapshots),
  **[odiff](https://github.com/dmtrKovalenko/odiff)** is ~8× faster and could swap into `pixel_diff.js`.
  Unnecessary at ~220 screens.

## Out of scope (so omissions aren't mistaken for gaps)

Back‑end/Spring modernization; responsive/mobile breakpoints (legacy is fixed‑viewport); accessibility
remediation; animation modeling; CI wiring. The replica targets the legacy desktop viewport at parity.
