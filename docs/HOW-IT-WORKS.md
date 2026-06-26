# How jsp2react works (plain-English explainer)

A guide you can read to understand the system — and use to explain it to others. For setup steps see
[SETUP.md](../SETUP.md); for the technical entry point see [README.md](../README.md).

## The 30-second version

> We have a big old web app (Java/JSP/Struts). We want a modern React version that looks and behaves
> *exactly* the same. jsp2react is a set of instructions + small tools that let GitHub Copilot do this
> automatically: it logs in, **reads the old screen's actual source code** (the JSP/AJAX) and **extracts the
> real color/font theme**, finds **every view — including the ones that load by AJAX** (the tabs and menus
> behind one link), rebuilds each in React **from that source**, feeds it the **real backend data**, and then
> **mathematically checks** that the React copy matches the original — view by view — instead of eyeballing
> it. If it doesn't match, the tool says exactly what's different so the AI makes a small fix and re-checks.

## The problem

The legacy app (BAA) is ~220 screens of JSP/Struts with old JavaScript (Dojo, jQuery). Rebuilding the UI
in React by hand is slow, and "does the new screen really match the old one?" is usually a judgment call.
We need it to be **automatic** and the match to be **provable**, not a matter of opinion.

## The idea in one line

Copy the proven structure of *fig2code* (an agent that turns Figma designs into code), but point it at a
**live running legacy screen + its source code** instead of a static design — and replace "the AI looks at
two pictures and decides" with a **deterministic check** that produces a punch-list of differences.

## The cast (who does what)

Two "agents" (instruction manuals the AI follows) and three "skills" (small toolkits the agents run):

| Piece | Role |
|---|---|
| **Agent: analyzer** | Logs in, extracts the theme, finds every view (incl. AJAX views, reached from the start), **parses each JSP into a "source model,"** captures each one (screenshot + structure + the real responses), and writes the plan. |
| **Agent: builder** | Takes the plan and, **one view at a time**, rebuilds it in React **from the source model + theme**, feeds it real data, and proves it matches. |
| **Skill: legacy-crawl-capture** | Parses the JSP source, finds every view (static + AJAX), and "fingerprints" each one. |
| **Skill: parity-verify** | The proof engine — compares old vs new (structure, style, and that the real data rendered) and reports exactly what differs. |
| **Skill: react-replica-kit** | Extracts the theme, sets up the React app (real-data wiring + login), and builds a navigable review index. |

It also **reuses tools the pod already has** instead of reinventing them: the existing login tool, the
screenshot tool, the browser/testing tool, and the team memory.

## The loop (how a screen gets built)

```
1. Read STATUS.md            → what's done, what's next (this keeps the AI on track over a long run)
2. Read the SOURCE MODEL     → the parsed JSP (loops, form fields, labels, which click loads which data)
   + theme + evidence          + the real color/font theme; the screenshot is only the check, not the input
3. Build it in React 1:1     → from the source: same layout, text, fields, columns; colors from the theme
4. Feed it the REAL data     → record (replay the real recorded responses) OR live (proxy the real backend)
5. PROVE it matches          → run the check; pass/fail + a list of exactly what differs (incl. "data missing")
6. Fix from the list         → repeat 5–6 until it passes
7. Mark it verified, move on → update STATUS.md, regenerate the index, next view
```

The trick that keeps a long, 220-screen run from going off the rails: **one screen per turn, tracked in a
checklist file (STATUS.md)**. The AI never has to hold the whole app in its head at once.

## How we "prove" a match (the important part)

A view passes only when a script — not the AI's opinion — says so. The check has three parts:

1. **Structure check.** Compares the *meaning* of both views: every label, every column, field order,
   tab order, validation message, every control. These must match **exactly**. This catches things a
   picture can't — e.g. "Acct #" vs "Account #" looks almost identical but is wrong.
2. **Data check.** Confirms the React side actually rendered the **real data** — not an empty table or a
   half-loaded view. ("Looks like the page but the rows are missing" fails here.)
3. **Picture check.** Compares the two screenshots pixel-by-pixel and points at *which element* is off.
   When both sides show the *same recorded data* (**record mode**) this is exact. When the React side is
   pulling *live* data that may have changed since capture (**live mode**), the picture is advisory and the
   structure/style/data checks carry the gate. Font anti-aliasing is ignored; real layout/spacing/color is not.

The output is a short report that says, in plain terms, *what* is different and *where* — so the AI makes a
small, targeted fix and re-checks. **The AI fixes from facts; it never decides "good enough" by eye.**

## How it gets real data (never fakes)

The copy must show **real backend data**, never hand-made dummy data. Two ways, picked per view:

- **record** — during capture we save the screen's *actual* responses to a file (a HAR). The React app
  replays those exact real bytes, so it shows the same real data the original did — and the picture check is
  exact because both sides are identical. No live backend needed to render.
- **live** — the React app talks to the *real* backend through a dev proxy, reusing the login session, and
  shows real-time data. Most "live," but since live data can change, the match is judged on structure/style.

Either way the endpoint addresses are identical to the old app, so switching modes needs no code change.
The login screen is rebuilt for real, so its session is what authorizes the data calls.

## The three promises it keeps

- **Exact copy (1:1):** built from the JSP **source** (not guessed from a picture) and enforced by the
  structure check + "never guess a view you haven't captured or parsed."
- **Nothing new added:** plain HTML/CSS, no UI component library, colors/fonts from the **extracted legacy
  theme**, reuse the old icons/fonts — only the framework changes, never the appearance.
- **Real data, never fakes:** every view shows real backend data (recorded-and-replayed, or live).
- **No wrong pages slip through:** error/half-loaded pages are detected and quarantined, never accepted as
  the real view.
- **Proven, not claimed:** a view is "done" only when the check script passes and leaves a side-by-side
  image; a generated **INDEX page** lists every view with its status for a human to glance at.

## What you actually run

Install once (`bash install.sh`), then tell Copilot to run the **analyzer** with just the **legacy URL and
how to log in**. The analyzer sets up its own tracking file (STATUS.md), extracts the theme, discovers every
view (including AJAX views), parses the source, and captures everything — you don't configure anything by
hand. Then run the **builder** repeatedly (one view at a time). The exact prompts are in
[SETUP.md §6b](../SETUP.md). A generated `INDEX.html` plus a side-by-side review page let you and your
colleagues compare originals against the React replicas, view by view.
