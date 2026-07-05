---
name: ogp-research-frontier
description: >
  The ambition map for Open Garden Planner — five open research/engineering
  frontiers where THIS project could advance the state of the art, each with
  the verified in-repo asset that makes it credible, the first three concrete
  steps, and a falsifiable "you have a result when…" milestone. Load this when:
  picking the next big direction; evaluating whether an idea is genuinely novel
  or already solved elsewhere; scoping Package D2/D3 (agent write tools, domain
  intelligence) or Phase-14+ ambitions (3D sun/shade, Phase 15 platform work);
  someone asks "what should this project do next" or "where is the frontier
  here"; or you are about to resurrect a retired idea and need to check whether
  it was deliberately killed. Everything in here is OPEN or CANDIDATE work —
  nothing in this file is shipped unless explicitly marked as an existing asset.
---

# OGP Research Frontier

Snapshot date: **2026-07-05**, repo at **v1.23.0** (Phases 1–13 Packages A/B/C
complete; Package D read surface D1.1–D1.3 shipped). Every "asset" claim below
was verified by reading the cited file at this date; every "state of the art"
characterization is an **assessment as of the model's knowledge (early 2026)**,
not a surveyed fact — do not cite it externally without your own check.

Hard rules for using this file:

- **Everything here is open or candidate.** Nothing in this skill is a shipped
  feature claim. If a milestone below is met later, update this file and only
  then consider external claims — routed through `ogp-external-positioning`.
  Nothing here may be publicly claimed until its milestone is met.
- Frontier work is still ordinary change work: branch, tests, senior-reviewer,
  draft PR. Load `ogp-change-control` before touching code. Experimental
  method (hypotheses, benchmarks, negative results) belongs to
  `ogp-research-methodology`; proofs and numeric validation tooling to
  `ogp-proof-and-analysis-toolkit`.

## When NOT to use this skill

- You are executing Phase 14 sun/shade work → use **ogp-3d-sunshade-campaign**
  (the execution plan lives there; only the research framing lives here).
- You need methodology discipline (how to run an experiment, what counts as
  evidence) → **ogp-research-methodology**.
- You are writing public/marketing/README text about capabilities →
  **ogp-external-positioning**.
- You are fixing a bug, doing routine feature work, or need architecture
  invariants → **ogp-debugging-playbook**, **ogp-change-control**,
  **ogp-architecture-contract**.
- You want to know how something that already shipped works → the reference
  skills (**ogp-qt-cad-reference**, **ogp-garden-domain-reference**,
  **ogp-config-and-flags**) and `docs/`.

---

## Frontier 1 — Agent-native CAD co-editing (Package D2/D3, epic #237)

Status: **OPEN.** Read surface shipped (D1.1–D1.3); zero write tools exist.

### (a) Why the state of the art falls short

Assessment (as of the model's knowledge, early 2026): agents interact with CAD
and design tools either by **screen-driving** (pixel-level, slow, fragile, no
undo semantics, fights the human for the mouse) or by **file round-trips**
(export → agent edits a file → re-import, losing live state and forcing the
human to stop working). Neither gives an agent and a human a shared live
document with clean transactional semantics. An embedded MCP server inside a
running GUI editor, where every agent operation is one undoable command on the
same stack the human uses, is — to this assessment — not an established
pattern anywhere; it is the specific thing this project is positioned to
demonstrate.

### (b) This project's specific asset (verified in-repo)

- `src/open_garden_planner/agent_api/bridge.py` — `MainThreadBridge(QObject)`
  with `run_on_main(fn, timeout)` marshaling arbitrary callables onto the Qt
  main thread via a queued signal + `concurrent.futures.Future`, plus
  `abort_pending()` for deadlock-free shutdown. ADR-033 explicitly states this
  boundary is **write-ready**: "later edit tools route through it identically."
- A mature command architecture with the two-chokepoint invariant (exactly two
  ways onto the undo stack: `CommandManager.execute()` and
  `register_applied()`, both dirty the document — see CLAUDE.md #209/#211 and
  `docs/08-crosscutting-concepts/` §8.2). One agent op → one `execute()` → one
  undo step falls out of existing machinery; no new transaction system needed.
- `agent_api/providers.py` — the `AgentProviders` dataclass is the documented
  extension seam for write providers (ADR-034 addendum: "the extension seam
  for render (D1.3), exports/save (D1.4) and writes (D2)").
- The design-decision table in `docs/roadmap.md` (Phase 13 Package D, ~line
  2387) already commits the contract: writes are "auto-apply, **fully
  undoable** — one undo step per agent operation."

### The non-negotiable prerequisite — do not route around it

`docs/roadmap.md` (D2 row) and FR-AGENT-03 (`docs/functional-requirements.md`
~line 427) are explicit: the server is loopback-only with **no auth today**,
and **token auth must land before ANY write tool**. Any local process can
reach the port. A write tool without auth is a P0 security regression, full
stop. If you find yourself prototyping a write tool "just locally first" —
stop; ship the auth first. See also §8.11 (security scanning) in
`docs/08-crosscutting-concepts/README.md`.

### (c) First three concrete steps in this repo

1. **Design and ship token auth** (its own PR, before any write code): generate
   a per-session token at server start, expose it to legitimate clients (e.g.
   a `~/.ogp/agent-token` file with owner-only permissions, or the Settings
   UI), reject unauthenticated requests at the ASGI layer in
   `agent_api/server.py`. Write the ADR (auth model, threat model = other
   local processes) and update FR-AGENT-03.
2. **First write tool through the command stack**: `create_bed(x, y, width,
   height, name?)` in `agent_api/` — a Qt-free request validator + a
   main-thread provider that builds the same `AddItemCommand`-family command
   the UI uses and routes it through `CommandManager.execute()`. Return the
   new object's UUID (ADR-034 addressing). Prove one-op-one-undo in a unit
   test before adding a second tool.
3. **Concurrent-edit integration test** (`tests/integration/`): human-side
   scene mutation (simulated via direct command execution) interleaved with
   MCP-client write calls; assert the undo stack is a clean interleaving,
   Ctrl+Z reverts exactly one op regardless of author, and no Qt cross-thread
   violation occurs (the bridge test patterns in
   `tests/unit/test_agent_api_bridge.py` are the template).

### (d) You have a result when…

An external MCP client (real client, not an in-process shim) creates and moves
objects in a running GUI session; every agent operation is exactly one undo
step on the shared stack; a human performs interleaved edits during the run
without corruption; **and** an adversarial test — a separate local process
hitting the port without the token — proves every write is rejected while
reads behave per the documented policy. Until all four hold simultaneously,
this frontier is not "done" in any communicable sense.

---

## Frontier 2 — Physically-grounded sun/shade on calibrated satellite imagery (Phase 14)

Status: **OPEN.** Owner-designated hardest problem. Execution plan:
**ogp-3d-sunshade-campaign** — this section is only the research framing.

### (a) Why the state of the art falls short

Assessment (as of the model's knowledge, early 2026): consumer garden-design
tools render decorative, physically meaningless shadows (fixed angle, no
geolocation, no date/time model). Professional solar tools (PV-yield,
architectural daylighting) are physically grounded but not garden-centric and
not coupled to plant-level consequences ("this bed gets 4.2 h direct sun on
June 21 → wrong crop"). The gap: a tool where the shadow at a timestamp is a
**prediction about the real garden**, checkable against a photograph, feeding
directly into planting decisions.

### (b) This project's specific asset (verified in-repo)

- **cm-calibrated canvas**: the coordinate system is centimetres end-to-end
  (§8.1 in `docs/08-crosscutting-concepts/README.md`); geometry is metric, not
  decorative.
- **Real geolocation**: `src/open_garden_planner/core/project.py` —
  `ProjectData.location: dict | None` persists `latitude`, `longitude`,
  `elevation_m`, `frost_dates` (docstring at `set_location`, ~line 747), saved
  in the `.ogp` file. The satellite picker
  (`ui/dialogs/map_picker_dialog.py`, ADR-019) produces a background with an
  "exact pixel→meter scale" (module docstring) from Web-Mercator math — so
  scene geometry sits on a georeferenced, metrically true substrate.
- **Weather/climate services**: `services/weather_service.py` (frost alerts,
  US-12.1/12.2) already fetches location-driven data — the plumbing for
  climate-aware refinement (cloud cover, seasonal statistics) exists.
- Phase 14 is already the roadmap's declared v2.0 milestone
  (`docs/roadmap.md` ~line 2447): sun path simulation, shade by season,
  object heights.

The missing piece is **object height** (no item carries a height property
today — Phase 14 bullet "Object height properties" is unshipped) and a solar
position + shadow-projection engine. Both are candidate work.

### (c) First three concrete steps in this repo

1. **Qt-free solar-position module** (`core/solar.py`, candidate name):
   lat/lng + UTC timestamp → sun azimuth/elevation, implemented from a
   standard published algorithm, pinned by unit tests against **precomputed
   third-party solar numbers** (e.g. NOAA calculator outputs pasted as test
   constants with their provenance in a comment — the test must not compute
   its expected values with the code under test). *Standard reconciliation with
   the execution plan:* `ogp-3d-sunshade-campaign` pins to a shipped
   `solar_reference.py` oracle that shares the production algorithm, so its
   headline elevation/azimuth rows are not independently sourced; it satisfies
   this bar via **independent physical-identity cross-checks** (axial tilt,
   solstice-noon `α = 90 − |φ−δ|`, almanac EoT extremes, equinox azimuth) plus a
   recommended ≥1 externally-sourced NOAA/Meeus row per location. Treat that
   identity-based regime as meeting this standard; keep the one-standard rule.
2. **Additive height metadata** on shape items
   (`metadata["object_height_cm"]` — the canonical key defined by the Phase-14
   execution plan `ogp-3d-sunshade-campaign`; do NOT mint `height_cm`, which
   would orphan the campaign's files. No FILE_VERSION bump — follow the
   additive-key precedent of C1/C2/C3, and read §8.14/ADR-017 before touching
   bed-adjacent surfaces), with a properties-panel field.
3. **2D shadow-polygon projection prototype**: given item footprint + height +
   sun vector, project the shadow polygon onto the ground plane and paint it
   as a canvas overlay (reuse the overlay patterns of §8.9). Flat-ground
   assumption first; state it.

### (d) You have a result when…

For a documented reference case (a real object of known height at the
project's real lat/lng, photographed at a known timestamp), the predicted
shadow boundary matches the measured/photographed one within a **stated,
pre-registered tolerance** (state it before measuring — e.g. shadow length
within X % — per ogp-research-methodology), and the solar math is pinned by
tests against independent precomputed solar numbers. A shadow that merely
"looks right" is explicitly not a result.

---

## Frontier 3 — Declarative parametric-symbol ecosystem (ADR-032)

Status: engine **shipped**, ecosystem **OPEN**. The UI is deliberately hidden
today.

### (a) Why the state of the art falls short

Assessment (as of the model's knowledge, early 2026): parametric components in
mainstream CAD (dynamic blocks, family editors) are authored inside
proprietary tools and shared through vendor ecosystems; lightweight/open
planners have static clipart at best. There is no open, safe, plain-JSON
parametric-component format a gardener (or an LLM) can author in a text editor
and share as a single file. OGP already has the hard part — a sandboxed
evaluator — but zero ecosystem around it.

### (b) This project's specific asset (verified in-repo)

- `src/open_garden_planner/core/parametric_eval.py` — a strict AST-whitelist
  arithmetic evaluator ("evaluated **without** Python's `eval()` — a dropped
  JSON file is untrusted input", module docstring), with a node-count cap
  (`_MAX_NODES = 250`) against stack-exhaustion, whitelisted funcs
  (`min/max/abs/round/floor/ceil/sqrt`). Qt-free.
- 5 bundled symbols in
  `src/open_garden_planner/resources/data/smart_symbols/` (`raised_bed_rows`,
  `pergola`, `fence_panel`, `greenhouse_gabled`, `compost_bay_3`), versioned
  JSON with `repeat` blocks and expression coordinates; user drop-a-file
  extensibility via `<app-data>/smart_symbols/` (§8.18).
- §8.18 (`docs/08-crosscutting-concepts/README.md` ~line 806) is already a
  near-complete authoring guide, and
  `tests/unit/test_smart_symbol_schema.py` validates every bundled file in CI.
  Note: validation today is a **pytest test, not a formal JSON Schema** — the
  schema artifact is candidate work, not an existing asset.
- The panel is hidden by one line:
  `self._sidebar_controller.set_panel_visible("smart_symbols", False)` at
  `src/open_garden_planner/app/application.py:1574` (line number valid at
  v1.23.0). Persistence, properties editing, and DXF BLOCK/INSERT export all
  ship and are tested (CLAUDE.md US-C4 entry) — unhiding is a UI decision,
  not an engineering lift.

### (c) First three concrete steps in this repo

1. **Unhide the panel** (delete/flip the `application.py:1574` line — check
   `ogp-config-and-flags` for the hidden-feature-toggle conventions), then
   author ~5 more symbols exercising the DSL's edges (`choice` params, nested
   `repeat`, `circle` elements) to stress the format before third parties do.
2. **Formal validation surface**: write an actual JSON Schema for the symbol
   format plus a tiny validation CLI (`python -m
   open_garden_planner.tools.validate_symbol my_symbol.json`, candidate path)
   that reports schema errors, expression parse failures, and a rendered
   primitive count — the authoring feedback loop §8.18 currently lacks.
3. **Sharing-format spec + gallery UX**: an ADR deciding what a shared symbol
   is (single JSON file? file + preview PNG? licensing field for GPLv3
   compatibility?) and a minimal in-app import path beyond drop-a-file.

### (d) You have a result when…

A third party (a person or an AI agent with no repo access) authors a working,
novel symbol guided **only** by §8.18 and the JSON-schema validation errors —
without reading any Python source — and it loads, renders, round-trips
through `.ogp` save/load, and exports to DXF. Log the attempt; a failure that
required reading source code is a documentation bug to fix, not a pass.

---

## Frontier 4 — Constraint-solver depth (ADR-012, §8.12, TD-007/TD-008)

Status: **OPEN** (both items are explicitly logged technical debt).

### (a) Why the state of the art falls short

Assessment (as of the model's knowledge, early 2026): serious geometric
constraint solvers (SolveSpace's core, commercial kernels like D-Cubed) exist
but are heavyweight, C/C++-bound, and overkill to embed in a Python garden
planner; naive relaxation solvers diverge on coupled systems. The interesting
open question at OGP's scale: how far can a small, pure-Python,
numpy-only hybrid solver go on real scenes — and can it become a documented,
reusable pattern for Python CAD-lite apps — without importing a kernel?

### (b) This project's specific asset (verified in-repo)

- ADR-012 (`docs/09-architecture-decisions/README.md` ~line 93): hybrid
  Gauss-Seidel warm-start + damped Newton-Raphson refinement
  (`constraint_solver_newton.py`), closed-form circle-circle fast path, numpy
  `linalg.lstsq`. scipy was **considered and rejected** (~40 MB installer
  cost) — do not reintroduce it casually; that is a settled trade-off you'd
  need a new ADR to reverse.
- TD-008 (`docs/11-risks-and-technical-debt/README.md` line 40): Newton uses a
  **numerical central-difference Jacobian** (`_JACOBIAN_H`); an analytic
  Jacobian per constraint type is the named, deferred improvement ("roughly
  2N × eval savings per iteration"), gated on large-scene need.
- TD-007 (same file, line 39 + the §11.4 entry at line 84): the
  `EDGE_TOP/BOTTOM/LEFT/RIGHT` dynamic anchor classification flips when a
  dragged vertex changes an edge's dominant axis; the named fix is a single
  `AnchorType.EDGE_MIDPOINT` + stable `anchor_index`. A workaround
  (index-only match in `_resolve_anchor_position`, `dimension_lines.py`) is
  in place — its behavior is the regression oracle for the real fix.
- Geometry-kernel side note (relevant if you widen this frontier to
  computational geometry): boolean ops are **QPainterPath-based**
  (`core/shape_boolean.py` — "Boolean shape operations using QPainterPath");
  `pyclipper` (>=1.3.0, pinned in `pyproject.toml`) is used **only** for
  polygon offsetting in `core/tools/offset_tool.py`. Unifying on one robust
  kernel is itself a candidate sub-frontier; do not describe the current
  boolean ops as clipper-based — they are not.

### (c) First three concrete steps in this repo

1. **Define and commit the benchmark scene** (nothing can be "N× faster"
   without it): a checked-in `.ogp` (e.g.
   `tests/data/constraint_benchmark.ogp`, candidate path) with a documented
   constraint census — proposal: ≥30 items, ≥60 constraints spanning every
   constraint type in §8.12 including coupled EDGE_LENGTH chains and TANGENT
   — plus a pytest-benchmark (or timed unit test) recording solve time and
   final residual vector as the baseline. Store the baseline numbers in the
   test, dated.
2. **Analytic Jacobians (TD-008)** behind a flag: derive per-constraint-type
   partials, keep the numerical Jacobian as the cross-check — a test asserts
   analytic ≈ numerical within tolerance on randomized configurations before
   the flag flips to default (proof-of-equivalence workflow:
   ogp-proof-and-analysis-toolkit).
3. **Retire TD-007**: implement `AnchorType.EDGE_MIDPOINT` + `anchor_index`
   with a `.ogp` migration for stored `EDGE_*` anchors, validated by the
   existing workaround's test path (the workaround stays until the migration
   test proves the new anchors survive the vertex-drag axis-flip that
   triggered the bug).

### (d) You have a result when…

The committed benchmark scene solves measurably faster (state the target
multiplier **before** optimizing; TD-008's own estimate suggests ~2× is the
honest ceiling from the Jacobian alone) with **identical final residuals**
(within stated tolerance) under the analytic Jacobian, and TD-007 is deleted
from `docs/11-risks-and-technical-debt/` because the EDGE_* types no longer
exist — with the old workaround's test scenario passing against the new
anchor model. A speedup on an ad-hoc scene, or a fix that keeps the
workaround load-bearing, is not a result.

---

## Frontier 5 — Agent-evaluable garden intelligence (Package D3)

Status: **OPEN.** Engines shipped; zero MCP domain tools exist; no evaluation
set exists.

### (a) Why the state of the art falls short

Assessment (as of the model's knowledge, early 2026): LLMs asked to plan
gardens hallucinate horticulture — companion pairings, spacing, and sowing
windows are produced from priors, unverifiable and often wrong. There is no
widely available setup where an agent's garden plan is grounded in a tool
that computes the domain answer *and* checked by the same deterministic
diagnostics a real application enforces. OGP can be both the toolbelt and the
judge — that closed loop is the frontier, and it doubles as a reusable
evaluation harness for agent horticulture.

### (b) This project's specific asset (verified in-repo)

- The domain engines are **already pure functions decoupled from the GUI**:
  `services/task_generator.py` ("Qt-free" by design per ADR-029 — the module
  imports `QCoreApplication` solely for `translate()`, no widgets/scene; its
  docstring says exactly this) with `build_plan_state(...)` +
  `generate_all(...)`; companion/succession/soil logic follows the same
  pattern (ADR-029, `docs/09-architecture-decisions/README.md` ~line 359).
- The judge already exists and is agent-reachable: D1.2's `get_diagnostics`
  (`agent_api/diagnostics.py`) reports the canvas's own computed warnings —
  antagonist, spacing overlap, capacity overrun, soil mismatch, rotation
  status (ADR-034 addendum). An agent's plan can be scored by the very checks
  the human UI paints as badges.
- The write path (Frontier 1) plus these engines is the full loop: read →
  reason with domain tools → write → self-check via diagnostics.
- Domain semantics reference: **ogp-garden-domain-reference**.

Dependency: D3 write-assisted planning inherits Frontier 1's **token-auth
prerequisite**. Read-only domain tools (e.g. `suggest_companions`) can ship
before auth; anything that mutates the plan cannot.

### (c) First three concrete steps in this repo

1. **First read-only domain tool**: expose e.g.
   `suggest_companions(species_key)` / `check_placement(species_key, bed_id)`
   in `agent_api/` as thin Qt-free wrappers over the existing engines,
   following the D1.2 pattern (Qt-free module + `AgentProviders` callable +
   curated pydantic schema + drift-guard test).
2. **Golden-plan evaluation set**: 3–5 checked-in `.ogp` benchmark plots
   (small/medium/awkward-shaped) each with a documented species palette and
   the known-good diagnostic outcome (zero violations) plus deliberately
   broken variants (known antagonist pair, known spacing overlap) — stored
   under `tests/data/` with expected `get_diagnostics` output pinned in
   integration tests. This is the judge's calibration, independent of any
   agent.
3. **Agent-in-the-loop harness** (script, not CI): drive a real MCP client +
   LLM against a benchmark plot with a fixed task ("plant these 10 species"),
   record tool traces, score the final plan with `get_diagnostics`. Compare
   against a no-tools baseline of the same model to quantify the grounding
   effect — that delta is the publishable observation (methodology:
   ogp-research-methodology; claims: ogp-external-positioning).

### (d) You have a result when…

An agent, using **only** MCP tools (no repo access, no pretrained-knowledge
shortcut you can't rule out — so the pass bar is the diagnostics, not the
prose), produces a plan on a defined benchmark plot that the project's own
`get_diagnostics` scores at **zero** antagonist/spacing/soil violations, and
the run is reproducible from a committed harness script. Bonus result (the
research-grade one): the tool-grounded agent measurably beats its own
no-tools baseline on the same task.

---

## Grounded optional candidates (thinner, still real)

- **Cross-platform packaging** — explicitly on the roadmap: Phase 15
  ("Platform & Community (Future, v2.1+)": plugin system, template sharing,
  "Cross-platform packaging (macOS, Linux)", `docs/roadmap.md` ~line 2459).
  Candidate only; the entire build/verify pipeline (`installer/ogp.spec`,
  NSIS, the CLAUDE.md exe smoke test) is Windows-shaped today. First honest
  step: a Linux PyInstaller CI job that merely *builds and launches* headless
  (`QT_QPA_PLATFORM=offscreen`). Not a result until a non-Windows user runs a
  release artifact.
- **i18n beyond German** — the machinery is language-agnostic but exactly two
  locales exist: `open_garden_planner_de.ts/.qm` and `_en.ts/.qm` in
  `src/open_garden_planner/resources/translations/` (verified 2026-07-05).
  The zero-unfinished gate (`test_german_ts_has_no_unfinished`) is
  German-specific. A third locale is a mechanical candidate; the *frontier*
  angle, if any, is agent-assisted translation with the existing
  `fill_translations.py` pipeline as the review chokepoint — treat as
  low-priority unless a contributor community materializes.

## What we will NOT pursue (settled retirements — do not resurrect)

- **US-B7 Paper Space MVP** — dropped during PR #191 manual-test review
  (CLAUDE.md, Package B note): `pdf_report_service` already covers
  print-to-PDF at chosen paper sizes; a second-space CAD-style print workflow
  added nothing. The `paper_layouts` key from short-lived draft builds is
  silently ignored on load. A "layout/paper space" idea is not new ambition;
  it is a settled retirement. Reopening requires new evidence the PDF path
  fails a real user, plus an ADR.
- **scipy in the solver** — rejected in ADR-012 (~40 MB installer for a
  problem numpy solves at ≤20 variables). Frontier 4 must stay within
  numpy-or-better unless a new ADR overturns this with data.
- **LP-optimal amendment solver** — rejected in ADR-015 (greedy max-coverage
  is provably optimal for the breadth metric at ≤24 substances; users prefer
  "one bag covers most"). Don't re-derive it.
- **Raw `.ogp` JSON as the agent contract** — rejected as the default in
  ADR-034 (brittle, leaks `FILE_VERSION` internals); it survives only as the
  `raw=True` escape hatch. Frontier 1/5 tools must return curated schema.

## Provenance and maintenance

Re-verify the load-bearing asset claims before acting on this file (all
one-liners from repo root; expected hits noted):

- Bridge write-ready: `grep -n "run_on_main\|abort_pending" src/open_garden_planner/agent_api/bridge.py`
- Token-auth prerequisite still open: `grep -n "token auth" docs/roadmap.md docs/functional-requirements.md` (if a token lands, rewrite Frontier 1(c) step 1)
- Location dict: `grep -n "latitude, longitude, elevation_m" src/open_garden_planner/core/project.py`
- Safe evaluator + cap: `grep -n "_MAX_NODES\|without.*eval" src/open_garden_planner/core/parametric_eval.py`
- Symbols bundled / panel hidden: `ls src/open_garden_planner/resources/data/smart_symbols/ && grep -rn 'set_panel_visible("smart_symbols"' src/`
- Solver debt: `grep -n "TD-007\|TD-008" docs/11-risks-and-technical-debt/README.md` (if gone, Frontier 4 milestones may be met — update this file)
- Qt-free engines: `head -25 src/open_garden_planner/services/task_generator.py`
- Boolean vs offset kernels: `head -1 src/open_garden_planner/core/shape_boolean.py && grep -rn pyclipper src/open_garden_planner/core/tools/offset_tool.py pyproject.toml`
- US-B7 stays dead: `grep -n "US-B7" CLAUDE.md`

When any milestone in (d) is met: mark it here, update `docs/roadmap.md`, and
only then involve **ogp-external-positioning** for any outward claim.
