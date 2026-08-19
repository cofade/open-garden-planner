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
throw at it. A **package** here is a cluster of open issues that ship together — not a single
issue.

This skill **sequences** work and adds only what is specific to package scale. Every process
rule it needs already lives in `ogp-change-control` (gates, branching, versioning) and
`ogp-docs-and-writing` (the doc duty matrix); this file points at them rather than restating
them, because a second copy of a gate list is how a gate goes missing. Where this file and
those disagree, **they win and this file is the bug**.

## 1. Establish ground truth before choosing anything

Read the canonical source first, then the compact delivery aid:

- `gh issue list --state open` and each candidate's full `gh issue view <n>` — the real source
  for scope, status, dependencies and the decisions an issue is waiting on. **The issue tracker
  is the only work list**; the project-board automation was deleted in #293.
- `docs/roadmap.md` — package order, phasing tables and acceptance criteria only.
- merged PRs and `git log` — delivery history, used to verify work is actually on `master`.

**Packages are identified by convention, not by GitHub structure.** This repo does **not** use
GitHub sub-issues — `#237` and `#284` have none. Membership is carried in the issue *title
suffix* (`US-D2.4: … (Package D2, epic #237)`) and in a `> **Package … map & order**` blockquote
at the head of each body listing every sibling and their order — the exact wording varies
(`Package D map & order` on the D issues, `Package map & order` on F/G), so grep loosely. Read
that blockquote: it is the most current statement of the package's shape that exists. Do not
assume a number range is a package — `#311`–`#321` looks like one but contains `#319`
(Package D3) and `#321` (a standalone touch-input issue).

**GitHub outranks the roadmap.** Packages F and G are nine filed issues (F = `#312`–`#316`,
G = `#311`, `#317`, `#318`, `#320`) with **zero** presence in `docs/roadmap.md` —
`grep -n "Package F\|US-F1\|US-G1" docs/roadmap.md` returns nothing. If the roadmap has drifted,
correct it **in this package's PR**; a stale table is why the next person picks the wrong work.
(Distinguish drift from *disclosed* scope: the D2 US-table blockquote said outright that it was
incomplete — a note admitting a gap is a smaller problem than silence, though still a gap.)

```bash
GH="C:/Program Files/GitHub CLI/gh.exe"   # Windows dev machine; in a Linux/cloud session use
                                          # the GitHub MCP tools instead (ogp-change-control §2.6)
"$GH" issue list --state open --limit 60
git log --oneline -15 origin/master
"$GH" pr list --state all --limit 10 --json number,title,headRefName,state,baseRefName
git branch -a --contains <merge-sha>      # is that merged PR's work really ON master?
```

**Stacked PRs are the local trap.** A PR whose base is another feature branch is invisible in
every "what is on master" view, and GitHub **permanently closes it** when that base branch is
deleted by the parent's merge — closed PRs cannot be retargeted. That cost a rebuilt PR in
Package 3 (#310's PR #324, refiled as #325). The recipe that actually worked: **rebase the child
branch onto `master` and open a fresh PR**. Better still, retarget the child to `master` *before*
merging the parent. If you find stranded work, land it first as its own PR and say so.

## 2. Choose the package

Prefer, in order:

1. The package on the **stated critical path** in `docs/roadmap.md` or the epic body, unless
   step 1 just invalidated it.
2. A package whose blockers are now resolved — recheck, the note may be stale (Package D's own
   "token auth deferred" note at `docs/roadmap.md:2439` is still there, many releases after the
   token auth actually shipped in D2.0).
3. A package whose issues form a real dependency chain, so shipping them together is cheaper
   than shipping them apart.

**An issue that states a recommendation is implementable.** Most decision-carrying issues here
carry an owner-authored *"Recommendation: …"* (or *"Recommended resolution: …"*, sometimes
mid-body rather than at the end) plus *"whatever is decided, the ADR must state
it and a test must pin it"* — that is pre-authorisation, not a blocker. Make the call, record it
in an ADR addendum, and surface it in the PR; never decide it silently in code. **Exclude only an
issue that poses an open question with no recommendation**, or one whose answer is a product call
rather than an architectural one. Treating every decision-carrying issue as excluded would drop
most of a package: #328 and #330 both name a decision *and* recommend an answer.

If a blocker is *inside* the package (issue A blocks issue B), that is an argument **for** taking
both, not for skipping B.

State the choice and the reasoning in one short paragraph before writing any code. If the honest
answer is that the highest-value package is blocked on the owner, say so and pick the next one —
do not invent work to look busy.

## 3. Plan against the issue specs, not against a summary

Read each issue body in full. Issues here carry Verified repo facts (with `file:line` citations),
Contract, Acceptance criteria, Order/dependencies, Docs to update and Gates — usually more
current than the docs, and the citations may still have rotted. **Verify every `file:line` claim
against the code before building on it.** Where the spec is wrong about the code, trust the code,
follow it, and say so in the PR.

Load the skills each issue names in its "before starting" line, plus `ogp-change-control` and
`ogp-architecture-contract` always.

Branch off `master`, one branch and one draft PR per package (`ogp-change-control` §1 for the
naming). If the package is genuinely too large to review in one sitting, slice it (3a/3b/3c) and
heed the stacked-PR rule above.

## 4. Implement in dependency order, gating incrementally

Build the blocker first, then what it unblocks. Run `ruff check src/` after each substantial
piece and the tests for the subsystem you just touched before moving on — a failure found three
files later is three files of rework.

Two disciplines that apply specifically at package scale:

- **One canonical path, never a second one.** The repo's recurring failure mode is a parallel
  implementation that drifts from the original. `create_object` builds items through the loader's
  own `_deserialize_item_core` precisely to avoid a second construction path. If a package needs
  behaviour the GUI already has, **extract the shared path** and have both call it — never copy
  it. A `Callable` injection point with N call sites is N implementations of one behaviour, and
  nothing will tell you when one stops matching the others (see #326 for the worked example).
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

Beyond that, four habits that repeatedly find real defects here:

- **Assert the refusal path, not just the happy path.** Every agent write tool must leave the
  scene *and the undo stack* untouched when it refuses. A tool that half-applies and then errors
  passes a happy-path test perfectly.
- **Assert the undo-step count, not just that undo works.** "Exactly one undo step per agent
  operation" is a contract, and `move_object`'s two-step reparent case is the documented
  exception that proves nobody verifies this by accident.
- **Parametrise over the parameter a defect scales with.** A bug proportional to rotation is
  exactly 0 at rotation 0, so coverage of the default value proves nothing (#213 / PR #217 is
  the recorded case).
  Same for empty collections, single-element lists, and unset optionals.
- **Add a drift guard for anything inlined from elsewhere.** Inlined `ObjectType` name sets, enum
  value sets and tool-name lists each need a unit test asserting they still match the real
  source, or the next enum member silently escapes the package's coverage.

The gate battery is `ogp-change-control` §2.5/§2.8 plus its §4 step-4 checks (pytest / ruff /
bandit), and `ogp-build-and-run` for the mechanics; run **all** of it
after every review-driven fix, not the subset near the fix. On the Windows dev machine that is:

```bash
venv/Scripts/python.exe -m pytest tests/ -v
venv/Scripts/python.exe -m ruff check src/
venv/Scripts/python.exe -m bandit -r src/ --severity-level high
PYTHONUTF8=1 venv/Scripts/python.exe scripts/fill_translations.py
PYTHONUTF8=1 venv/Scripts/python.exe scripts/compile_translations.py
venv/Scripts/python.exe -m pytest tests/unit/test_i18n.py -v
venv/Scripts/python.exe scripts/check_agent_context.py
venv/Scripts/python.exe -m PyInstaller installer/ogp.spec --noconfirm
timeout 8 dist/OpenGardenPlanner/OpenGardenPlanner.exe   # exit 124 = survived = pass
powershell -Command '$p = Start-Process "dist/OpenGardenPlanner/OpenGardenPlanner.exe" -ArgumentList "--selftest" -Wait -PassThru; exit $p.ExitCode'
```

The exe build is the **last three lines of the battery, not an optional extra** — see step 6.
Both exe checks are `ogp-change-control` §2.8's, not this file's; the mechanics and the two
traps in that `Start-Process` invocation are in `ogp-build-and-run`. Do not simplify it: a
plain call returns in milliseconds under PowerShell with no exit code, and a shell-piped run
hands the windowed exe a real stdout so it cannot reproduce the condition #291 is about.

## 6. Verify on the running artifact, not only in pytest

**Always.** `CLAUDE.md` and `ogp-change-control` §2.8 both require a frozen-exe build, the
8-second smoke **and** `--selftest` before every merge; the only sanctioned excuse is a
Linux/cloud session that cannot run them, and then you **say so in the PR** rather than skipping
silently. pytest runs the source tree; users run the frozen exe, and the two have disagreed on
real releases in three different ways: #291 (the embedded server never started in the frozen
*windowed* exe, because uvicorn's log config dereferences `sys.stdout`, which is `None` there),
#277 (a Qt6Core/Qt3D micro mismatch that startup and the smoke both survived because Qt3D is
imported **lazily** — nothing to do with stdout; a `console=True` build reproduces it fine), and
the `ogp.spec` `unittest` exclusion that silently broke DXF export in every built exe. Different
root causes, one shared shape: a subsystem that is dead while the process is alive.

Doubly so when the package touches startup, packaging, resources, or the Agent API. For an
**Agent API** package, add the dogfood run D1.4 established: launch the app, point a live MCP
client at the running server, and drive the new tools end to end. It is the only check that
exercises the real transport, the real marshaling hop and the real client's quirks. (Note what it
is *not*: the `?token=` connect-URL design came from the **owner's manual test** on Windows, not
from a dogfood run — ADR-036's "Addendum (manual-test finding)". Step 8's manual-test
sovereignty is not something automation retires.)

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

The matrix is in `CLAUDE.md` and `ogp-docs-and-writing`; follow it. Four items are easy to forget
at package scale and are checked here because every recent package PR owed all four:

- **`docs/roadmap.md`** — add or complete the package's US rows and mirror them into
  `../open-garden-planner.wiki/Roadmap.md`. This is the table that drifts; fixing it is part of
  the package, not a follow-up.
- **`CLAUDE.md` + `AGENTS.md` "Where to Pick Up After Restart"** — update both, in the same
  commit, then run `scripts/check_agent_context.py`. That gate is meaningless if the content it
  compares is stale in both copies.
- **A `debug-verbose` case study in both skill libraries** whenever the package fixed a
  non-obvious bug (symptom → wrong theories → key evidence → root cause → lesson), per
  `CLAUDE.md`'s debugging section.
- **§11.4** for anything the package learned the hard way, and an **ADR addendum** for every
  decision an issue asked you to make.

Docs are **English-only** — never let a German UI label leak into doc prose.

## 8. Senior-reviewer loop, then hand off to change-control

Run the `senior-reviewer` agent against the branch diff in a fresh worktree — **once per PR, and
again after every round of fixes, until it comes back clean**. The gate itself, its
round-on-round catches, the unmet-gate carve-out and the reviews-are-not-oracles rule all live
in `ogp-change-control` §2.4; read it rather than this paragraph.

Two things that only bite at package scale:

- **Once per PR, not once per package.** A package that ships as two or three PRs needs a review
  per branch — a clean pass on one says nothing about the others.
- **Rounds compound.** Round 2 catches what round 1's *fix* broke, round 3 what rounds 1 and 2
  obscured (#240 / PR #251). Budget for three, and re-run after every round of fixes.
- **This skill never overrides a live instruction from the user.** It only refuses to let an
  unmet gate go unreported.
- **The reviewer's worktree has no `.env` and no real credentials.** Any claim it makes about
  "live-confirmed" behaviour is unverified; confirm it yourself. This is recorded nowhere else.

Then hand off: `ogp-change-control` owns the landing decision, `finalize-us` the post-approval
sequence (CI wait, tag-transition wait, version sync, wiki push). **Open the PR as a draft and
stop there** — never mark ready or merge until the owner confirms manual testing passed (§2.3
carries the list of designs that testing has killed).

## 9. Report

Close with, in this order:

1. what shipped, **per issue**;
2. what the gates say — each layer with its **actual numbers**, and any gate not run, named;
3. what the live / frozen run found, including anything it broke;
4. **only** the manual tests the owner must do — each with what to do, what a pass looks like,
   and what a failure would mean;
5. anything deliberately left out, and why;
6. confirm CI is green (`"$GH" pr checks <n> --watch --fail-fast` — the one gate that runs on a
   different machine than yours, and the only one that can disagree with your local run), and
   that every issue the package closes has `Closes #N` in the PR body, the base is `master`, and
   it is still a draft:
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
