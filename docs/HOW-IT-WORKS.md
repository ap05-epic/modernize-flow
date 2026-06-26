# How jsp2react works (plain-English explainer)

A guide you can read to understand the system — and use to explain it to others. For setup steps see
[SETUP.md](../SETUP.md); for the technical entry point see [README.md](../README.md).

## The 30-second version

> We have a big old web app (Java/JSP/Struts). We want a modern React version that looks and behaves
> *exactly* the same. jsp2react is a set of instructions + small tools that let GitHub Copilot do this
> automatically: it logs into the old app, visits every screen, takes a precise "fingerprint" of each
> one, rebuilds it in React, and then **mathematically checks** that the React copy matches the original —
> screen by screen — instead of just eyeballing it. If it doesn't match, the tool says exactly what's
> different so the AI can fix it and check again.

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
| **Agent: analyzer** | Logs in, finds every screen, captures each one (screenshot + structure + data), maps its endpoints, and writes the plan. |
| **Agent: builder** | Takes the plan and, **one screen at a time**, rebuilds it in React and proves it matches. |
| **Skill: legacy-crawl-capture** | Finds and "fingerprints" each legacy screen. |
| **Skill: parity-verify** | The proof engine — compares old vs new and reports exactly what differs. |
| **Skill: react-replica-kit** | Sets up the React app and a side-by-side review page. |

It also **reuses tools the pod already has** instead of reinventing them: the existing login tool, the
screenshot tool, the browser/testing tool, and the team memory.

## The loop (how a screen gets built)

```
1. Read STATUS.md            → what's done, what's next (this keeps the AI on track over a long run)
2. Look at the captured      → the screenshot + a "fingerprint" of the legacy screen
   evidence for one screen
3. Build it in React 1:1     → same layout, text, fields, columns — nothing added or removed
4. Feed it the same data     → using saved copies of the real responses (so no live backend needed)
5. PROVE it matches          → run the check; get a pass/fail + a list of differences
6. Fix from the list         → repeat 5–6 until it passes
7. Mark it verified, move on → update STATUS.md, next screen
```

The trick that keeps a long, 220-screen run from going off the rails: **one screen per turn, tracked in a
checklist file (STATUS.md)**. The AI never has to hold the whole app in its head at once.

## How we "prove" a match (the important part)

A screen passes only when a script — not the AI's opinion — says so. The check has two halves:

1. **Structure check.** Compares the *meaning* of both screens: every label, every column, field order,
   tab order, validation message, every control. These must match **exactly**. This catches things a
   picture can't — e.g. "Acct #" vs "Account #" looks almost identical but is wrong.
2. **Picture check.** Compares the two screenshots pixel-by-pixel and highlights the regions that differ,
   then points at *which element* is in that spot — e.g. "this table header is off." Tiny differences from
   fonts/anti-aliasing are ignored; real layout/spacing/color differences are not.

The output is a short report that says, in plain terms, *what* is different and *where* — so the AI makes a
small, targeted fix and re-checks. **The AI fixes from facts; it never decides "good enough" by eye.**

## How it renders with no backend

The React copy must look right on its own, without the old server running. During capture we save the
real data each screen received. The React app is fed those saved copies (via a tool called MSW), so it
shows the **same data** the original screenshot showed — which is also what makes the pixel check fair.
The same endpoint addresses are still wired up, so you *can* point it at the real backend later if you want.

## The three promises it keeps

- **Exact copy (1:1):** enforced by the structure check + "never guess a screen you haven't captured."
- **Nothing new added:** plain HTML/CSS, no UI component library, reuse the old icons/fonts — only the
  framework changes, never the appearance.
- **Proven, not claimed:** a screen is "done" only when the check script passes and leaves a side-by-side
  image for a human to glance at.

## What you actually run

Install once (`bash install.sh`), then tell Copilot to run the **analyzer** with just the **legacy URL and
how to log in**. The analyzer sets up its own tracking file (STATUS.md) and captures everything — you don't
configure anything by hand. Then run the **builder** repeatedly (one screen at a time). The exact prompts
are in [SETUP.md §6b](../SETUP.md). A side-by-side review page lets you and your colleagues compare
originals against the React replicas.
