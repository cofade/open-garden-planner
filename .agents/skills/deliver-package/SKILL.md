---
name: deliver-package
description: >
  Pick the next package of open issues and deliver it end to end — establish ground truth
  from GitHub, choose the package, plan against the issue bodies, implement in dependency
  order, run the full gate battery, verify on the frozen exe / live app, senior-review to
  clean, open a draft PR, and report only the manual tests the owner must still do. Use
  when asked to "take the next package", "pick the next issues and implement them",
  "deliver package N", or to work autonomously through a cluster of related issues rather
  than a single user story.
---

# Deliver a package

One pass from "what's next?" to a draft PR that has already survived everything an agent can
throw at it. A **package** here is a cluster of open issues that ship together — the rows of a
`docs/roadmap.md` phase/US table, or the sub-issues of a GitHub epic (`#237` Package D, `#284`
Visual Refresh 3, `#311`–`#321` Packages F/G) — not a single issue.

This skill **sequences** work. Every rule it applies belongs to `ogp-change-control` and
`CLAUDE.md`; where they disagree with this file, **they win and this file is the bug**. Landing
decisions (merge, version sync, wiki) belong to `ogp-change-control` and the `finalize-us`
skill, which this skill hands off to rather than restating.

## 1. Establish ground truth before choosing anything

Read the canonical source first, then the compact delivery aid:

- `gh issue list --state open` and each candidate's full `gh issue view <n>` — the real source
  for scope, status, dependencies and the decisions an issue is waiting on. **The issue tracker
  is the only work list**; the project-board automation was deleted in #293.
- `docs/roadmap.md` — package order, phasing tables and acceptance criteria only.
- merged PRs and `git log` — delivery history, used to verify work is actually on `master`.

**GitHub outranks the roadmap.** The roadmap's US tables lag the tracker routinely — Package D's
table had no rows for D2.2–D2.6 or D3.1–D3.4 for as long as those nine issues existed. If the
roadmap has drifted, correct it **in this package's PR**; a stale table is why the next person
picks the wrong work.

```bash
GH="C:/Program Files/GitHub CLI/gh.exe"
"$GH" issue list --state open --limit 60
git log --oneline -15 origin/master
"$GH" pr list --state all --limit 10 --json number,title,headRefName,state,baseRefName
# For any recently merged PR, confirm its work is actually ON master:
git branch -a --contains <merge-sha>
```

**Stacked PRs are the local trap.** A PR whose base is another feature branch is invisible in
every "what is on master" view, and GitHub **permanently closes it** when that base branch is
deleted by the parent's merge — closed PRs cannot be retargeted. This cost a rebuilt PR in
Package 3 (#310's PR #324, refiled as #325). If you stack, **retarget the child to `master`
before merging the parent**, or merge the parent without `--delete-branch`. If you find stranded
work, land it first as its own PR and say so; never build on a base `master` does not have.

## 2. Choose the package

Prefer, in order:

1. The package on the **stated critical path** in `docs/roadmap.md` or the epic body, unless
   step 1 just invalidated it.
2. A package whose blockers are now resolved — recheck, the note may be stale (Package D's own
   "token auth deferred" note outlived the token auth actually shipping in D2.0).
3. A package whose issues form a real dependency chain, so shipping them together is cheaper
   than shipping them apart.

**Exclude issues whose body carries an unresolved owner decision** — those need a decision, not
code. Several Package D issues name theirs explicitly (may an agent unlock a locked layer, #328;
the constrained-object policy, #330). If such an issue also states a recommendation and the
decision is *architectural* rather than *product*, you may make it — but you must record it in an
ADR addendum and surface it in the PR, never decide it silently in code.

If a blocker is *inside* the package (issue A blocks issue B), that is an argument **for** taking
both, not for skipping B.

State the choice and the reasoning in one short paragraph before writing any code. If the honest
answer is that the highest-value package is blocked on the owner, say so and pick the next one —
do not invent work to look busy.

## 3. Plan against the issue specs, not against a summary

Read each issue body in full (`gh issue view <n>`). Issues in this repo carry Verified repo facts
(with `file:line` citations), Contract, Acceptance criteria, Order/dependencies, Docs to update
and Gates sections that are usually more current than the docs — and the citations may still have
rotted. **Verify every `file:line` claim against the code before building on it.** Where the spec
is wrong about the code, trust the code and note the divergence in the PR.

Load the skills each issue names in its "before starting" line, plus `ogp-change-control` and
`ogp-architecture-contract` always.

Branch off `master`: `feature/US-X.X-short-description` for a US-shaped package,
`fix/NNN-short-description` for a bug cluster. **One branch, one draft PR per package** unless
the package is genuinely too large to review in one sitting — then slice it (3a/3b/3c) and heed
the stacked-PR rule in step 1.

## 4. Implement in dependency order, gating incrementally

Build the blocker first, then what it unblocks. Run `ruff check src/` after each substantial
piece rather than at the end, and run the tests for the subsystem you just touched before moving
on — a failure found three files later is three files of rework.

Two OGP-specific disciplines that apply at package scale:

- **One canonical path, never a second one.** The repo's recurring failure mode is a parallel
  implementation that drifts from the original. D2.1 nearly built a second bed-linking path
  before a probe disproved the need, and `create_object` builds items through the loader's own
  `_deserialize_item_core` precisely to avoid a second construction path. If a package needs
  behaviour the GUI already has, **extract the shared path** and have both call it — never copy
  it.
- **Wrap every user-visible string as you write it** (`self.tr()` / `QCoreApplication.translate`
  / `QT_TR_NOOP`), not in a cleanup pass. The i18n gate only sees strings already registered; a
  hardcoded f-string sails straight past it (§11.4).

Route to `ogp-qt-cad-reference` for canvas/geometry, `ogp-garden-domain-reference` for domain
logic, `ogp-architecture-contract` for serialization / undo / layers / beds / `agent_api` seams,
and **§8.14 + ADR-017 before touching anything bed-related**.

## 5. Test every layer the change touches

Per §8.10, **every user story ships at least one end-to-end integration test in
`tests/integration/test_<feature>.py` — no merge without it, no exceptions**, and every bug fix
pins its regression with a test **observed failing first**.

Beyond that, three habits that repeatedly find real defects here:

- **Assert the refusal path, not just the happy path.** Every agent write tool must leave the
  scene *and the undo stack* untouched when it refuses. A tool that half-applies and then errors
  passes a happy-path test perfectly.
- **Assert the undo-step count, not just that undo works.** "Exactly one undo step per agent
  operation" is a contract, and `move_object`'s two-step reparent case is the documented
  exception that proves nobody verifies this by accident.
- **Add a drift guard for anything inlined from elsewhere.** Inlined `ObjectType` name sets, enum
  value sets and tool-name lists each need a unit test asserting they still match the real
  source, or the next enum member silently escapes the package's coverage.

Run the full battery — not the subset near your change — after every review-driven fix:

```bash
venv/Scripts/python.exe -m pytest tests/ -v
venv/Scripts/python.exe -m ruff check src/
venv/Scripts/python.exe -m bandit -r src/ --severity-level high
PYTHONUTF8=1 venv/Scripts/python.exe scripts/fill_translations.py
PYTHONUTF8=1 venv/Scripts/python.exe scripts/compile_translations.py
venv/Scripts/python.exe -m pytest tests/unit/test_i18n.py -v
venv/Scripts/python.exe scripts/check_agent_context.py
```

## 6. Verify on the running artifact, not only in pytest

Not optional when the package touches startup, packaging, resources, or the Agent API. pytest
runs the source tree; users run the frozen exe, and the two have disagreed on real releases —
#291 (the embedded server never started in the frozen *windowed* exe, because uvicorn's log
config touches `sys.stdout`, which is `None` there) and the `ogp.spec` `unittest` exclusion that
silently broke DXF export in every built exe.

```bash
venv/Scripts/python.exe -m PyInstaller installer/ogp.spec --noconfirm
timeout 8 dist/OpenGardenPlanner/OpenGardenPlanner.exe   # exit code 124 = success
```

For an **Agent API** package, add the dogfood run that D1.4 established: launch the app, point a
live MCP client at the running server, and drive the new tools end to end. It is the only check
that exercises the real transport, the real marshaling hop and the real client's quirks — the
`?token=` connect-URL parameter exists because Claude Code drops configured headers on tool-call
POSTs, which no in-process test could ever have shown.

**Read what the run says, do not just read the exit code.** A failure is three different things
and they want opposite responses:

| The run shows | It probably means | Do |
|---|---|---|
| exe exits immediately (not 124) | a packaging / hidden-import break | fix `installer/ogp.spec`; never settle for "it works from source" |
| a tool errors only over the live client | transport or marshaling, not logic | fix the seam; a passing in-process test does not refute it |
| a tool returns plausible but wrong data | a genuine logic defect the fixtures missed | that is a finding — add the fixture, never adjust the assertion |

Record what a live run *surprised* you with in `docs/11-risks-and-technical-debt/` §11.4. A run
that only confirmed what you already believed was not worth the electricity.

## 7. Documentation duty — before it counts as done

Per the duty matrix in `CLAUDE.md` and `ogp-docs-and-writing`. At package scale this always
includes:

- an **ADR** (or an addendum to the governing one) per non-trivial decision — and *always* for a
  decision an issue explicitly asked you to make;
- the **arc42** chapters touched: `05-building-block-view/` (new modules), `06-runtime-view/`
  (changed flows), `08-crosscutting-concepts/` (§8.19 Agent API, §8.10 test policy, §8.11
  security, §8.3 i18n);
- **`docs/functional-requirements.md`** — an `FR-*` entry per new user-facing capability;
- **`docs/12-glossary.md`** for every new domain term;
- **`docs/roadmap.md`** — add or complete the package's US rows (this is the table that drifts;
  fixing it is part of the package, not a follow-up), and mirror it into
  `../open-garden-planner.wiki/Roadmap.md`;
- **§11.4** for anything the package learned the hard way.

Docs are **English-only** — never let a German UI label leak into doc prose.

## 8. Senior-reviewer loop, then hand off to change-control

Run the `senior-reviewer` agent against the branch diff in a fresh worktree. Fix every P0 and P1,
re-run, repeat until clean — **a review of the original is not a review of the fix**. Round 2 has
caught P0s that round 1 missed (#213 / PR #217's rotated-plant `transformOriginPoint` drift).

Two counterweights, both earned:

- **Reviews are inputs, not oracles.** Verify each finding against the code in both directions
  before acting; a #223 P1 claiming conditional `can_undo`/`can_redo` signals was refuted simply
  by reading `commands.py`.
- **The reviewer's worktree has no real credentials or `.env`.** Any claim it makes about
  "live-confirmed" behaviour is unverified — confirm it yourself.

Then hand off: `ogp-change-control` owns the landing decision and the evidence hierarchy;
`finalize-us` owns the post-approval sequence (CI wait, tag-transition wait, version sync, wiki).
**Open the PR as a draft and stop there.** Never mark ready, never merge, until the owner
confirms manual testing passed — manual testing has killed reviewed, merged and green work
repeatedly (US-B7 dropped entirely; #226's accordion reworked; D1.3's subtractive `layers` bug).

## 9. Report

Close with, in this order:

1. what shipped, **per issue**;
2. what the gates say — each layer with its **actual numbers**, and any gate not run, named;
3. what the live / frozen run found, including anything it broke;
4. **only** the manual tests the owner must do — each with what to do, what a pass looks like,
   and what a failure would mean;
5. anything deliberately left out, and why;
6. confirm every issue the package closes has `Closes #N` in the PR body and that the PR's base
   is `master` and it is still a draft:
   ```bash
   "$GH" pr view <n> --json closingIssuesReferences,baseRefName,isDraft
   ```
   A package is by construction a multi-issue PR — the highest-density case for one issue
   silently missing its keyword and staying open forever.

A short honest list beats a long padded one. If something is blocked on the owner, name it and
stop there — **stopping at a draft PR with an honest checklist is a successful outcome.**

## When NOT to use this skill

- A single user story or a one-issue fix → the `CLAUDE.md` workflow table + `ogp-change-control`.
- The post-approval wrap-up itself (merge, version sync, wiki) → `finalize-us`.
- Reviewing someone else's PR → `analyze-pr`.
- Deciding what proof a claim needs → `ogp-validation-and-qa`.
- Mechanical "how do I run this" questions → `ogp-build-and-run`.
