

# OGP Debugging Playbook

Fast triage for this repo's *recurring* failure modes. Every row below is grounded in a
documented incident — the project has already paid for these lessons once. Your job:
match the symptom, run the cheapest discriminating experiment, follow the fix pointer.

Ground-truth sources (read the matching entry BEFORE changing code):

| Source | What it holds |
|---|---|
| `docs/11-risks-and-technical-debt/README.md` §11.4 | The pitfall chronicle — one entry per hard-won lesson, with contracts and regression tests |
| `.agents/skills/debug-verbose/SKILL.md` | Instrumentation method + full case studies (symptom → wrong theories → key log line → root cause) |
| `docs/08-crosscutting-concepts/README.md` §8.9 | QGraphicsView overlay/geometry patterns (incl. §8.9.8 rotation invariant) |
| `docs/08-crosscutting-concepts/README.md` §8.19 + `docs/07-deployment-view/README.md` §7.6 | MCP server threading pitfalls + PyInstaller bundling fixes |

Jargon used once, defined once:
- **Y-flip**: the canvas view applies `scale(zoom, -zoom)` so positive scene Y is visually *up* (CAD-style, origin bottom-left). Anything drawn or exported without accounting for this appears mirrored or misplaced. (§11.4 "Canvas Y-axis flip")
- **`ItemIgnoresTransformations`**: Qt flag making an item render at fixed pixel size regardless of zoom. Used by all drag handles, labels, badges. It has three separate failure modes (rows 2, and export rows below).
- **The chronicle**: §11.4. When this playbook says "chronicle: `<keyword>`", grep that keyword in §11.4 for the full entry.

