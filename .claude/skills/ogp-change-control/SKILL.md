---
name: ogp-change-control
description: >
  Load BEFORE starting any change to Open Garden Planner — feature, bug fix, refactor,
  doc-in-code, or chore — and whenever you are about to branch, commit, open a PR, mark a
  PR ready, merge, bump a version, create/wait on a release, or you are wondering whether
  an action (tagging, pushing to master, merging without user sign-off, skipping a test or
  translation) is allowed. Explains how changes are classified (US / issue / chore), every
  non-negotiable gate with the historical incident behind it, the CI release machinery
  (release.yml / ci.yml), and a start-to-finish change checklist. If you are unsure whether
  a gate applies to you, it does — read this first.
---

# OGP Change Control

How changes enter this repository, which gates they must pass, and why each gate exists.
This is process, not technique: for *how to run* tests/builds see `ogp-build-and-run`; for
*what evidence counts* see `ogp-validation-and-qa`. Nothing in this skill may be routed
around — every rule below was paid for with a real incident, cited inline.

Facts date-stamped **as of 2026-07-03**: released version **v1.23.0** (matching
`pyproject.toml` and `src/open_garden_planner/__init__.py`), `.ogp` file format
`FILE_VERSION = "1.4"` (`src/open_garden_planner/core/project.py:34`), default branch
`master`, repo owner `cofade`.

## Glossary (read once, used everywhere)

| Term | Meaning here |
|------|--------------|
| **US** | User story, numbered `US-X.X` (e.g. `US-12.7`) or per-package (`US-A1`, `US-C3`, `US-D1.2`). Defined with acceptance criteria in `docs/roadmap.md`. |
| **FR** | Functional requirement (`FR-*`) in `docs/functional-requirements.md`; the durable record of a shipped capability. |
| **ADR** | Architecture Decision Record in `docs/09-architecture-decisions/`. Required for new dependencies, chosen-between approaches, changed patterns, non-obvious constraints. |
| **Draft PR** | GitHub pull request opened with `--draft`. In this repo it means "code review passed, awaiting the user's manual test". It is the mandatory end state of every coding job. |
| **Chore commit** | Commit whose message starts with `chore:` or `chore(...)`. The release workflow deliberately skips these — they are how version-sync and doc-only changes land on master without minting a release. |
| **Squash merge** | The only merge mode used: `pr merge --squash --delete-branch` collapses the branch into one master commit. That single commit message is what `release.yml` inspects for the `chore` skip. |
| **senior-reviewer** | The repo's adversarial review agent (`.claude/agents/senior-reviewer.md`, P0/P1/P2 severity discipline). A clean pass is a hard gate before any PR. |
| **P0 / P1 / P2** | Review severities: P0 blocks merge (correctness, data loss, untranslated user-facing strings); P1 should be fixed before merge; P2 is a nit. |
| **i18n gate** | `tests/unit/test_i18n.py::TestTranslationFiles::test_german_ts_has_no_unfinished` — fails if any registered UI string lacks a German translation. |
| **FILE_VERSION** | The `.ogp` save-file format version (`"1.4"` as of 2026-07-03). Distinct from the app version. New `.ogp` keys are added *additively* without bumping it whenever old versions can safely ignore them. |
| **Manual-test sovereignty** | The user's hands-on test of the built app is the final gate. It has overturned merged designs before (see below); automated green is necessary, never sufficient. |

## 1. Classifying a change

Decide the class first — it determines branch name, commit prefix, and whether a release
will be minted.

| Class | Source of truth | Branch | Commit prefix | Release? |
|-------|-----------------|--------|---------------|----------|
| User story | `docs/roadmap.md` (read the acceptance criteria before coding) | `feature/US-X.X-short-description` | `feat(US-X.X): ...` | Yes (patch by default) |
| Bug fix / follow-up issue | GitHub issue `#NNN` (issues auto-land on project board 1 via `add-to-project.yml`) | `fix/NNN-short-description` or `feature/...` per convention in `git log` | `fix(#NNN): ...` or `feat` if it adds capability | Yes |
| Chore (version sync, roadmap table, doc-only, CI tweak) | — | may go straight to master **only** for the post-release version-sync commit prescribed by the protocol; anything larger gets a branch | `chore: ...` / `chore(scope): ...` | **No** — release.yml skips it |

Everything user-visible that a change adds must eventually be reflected in
`docs/functional-requirements.md`, arc42 docs, and possibly an ADR — see
`ogp-docs-and-writing` for the duty matrix (it mirrors the table in `CLAUDE.md`).

## 2. The non-negotiables

Each rule below has the format: **rule → rationale → incident**. Do not treat any of them
as ceremony; the incident column is why they exist.

### 2.1 Never commit directly to master

Always `git checkout -b feature/US-X.X-short-description` (or `fix/...`) before touching
code. Master is the release trigger: every non-chore push to master mints a tag, a GitHub
release, and a Windows installer (`release.yml`). A direct commit publishes untested code
to end users. The only sanctioned direct-to-master pushes are the `chore:` version-sync /
roadmap commits after a merge (section 2.6), which the release workflow ignores.

### 2.2 Never create git tags manually — CI owns versions

`release.yml` computes the next version from `git describe --tags --abbrev=0` plus the
merged PR's labels. A hand-made tag corrupts that arithmetic for every future release.

**Incident (chore-commit race, documented in `docs/11-risks-and-technical-debt/README.md`
§11.4):** after a feature merge, the follow-up chore commits landed ~37 s later while the
release build for the feature was still running (~2 m 50 s). The chore-triggered workflow
runs read the *old* latest tag, computed a stale version (`v1.8.4` instead of `v1.9.2`),
and failed with "release with the same tag name already exists". Fix: the
`if: "!startsWith(...'chore:') && !startsWith(...'chore(')"` guard on the release job —
which is also why your version-sync commit **must** carry the `chore:` prefix (a scoped
`chore(finalize-us):` once slipped past a narrower guard and wrongly triggered a release,
hence the second `chore(` clause).

**Incident (issue #229, documented in `.claude/skills/finalize-us/skill.md`):** a script
waited for the new release by grepping `gh release list` output for today's `$(date)`.
Local-vs-UTC `createdAt` mismatches and same-day re-runs made the match unreliable, and a
date match cannot detect a *failed* release. Rule: wait on a **state transition** —
capture the top `tagName` before merging, poll until it *changes* (the `finalize-us`
skill has the exact loop). Never match on dates.

### 2.3 Every coding job ends with a DRAFT PR — and stays draft until the user says so

Any task that changes code finishes by pushing the branch and opening a **draft** PR
(`gh pr create --draft` on Windows; `mcp__github__create_pull_request` with `draft: true`
in cloud sessions). Never stop at "branch pushed". Never open a non-draft PR. Never mark
ready or merge without the user explicitly confirming manual testing passed — then, and
only then: `pr ready` followed by `pr merge --squash --delete-branch --admin`.

**Why manual testing is sovereign — merged-or-reviewed work has been overturned by it
repeatedly (all documented in `CLAUDE.md` progress tables):**

- **US-B7 (Paper Space MVP) was dropped entirely** during PR #191 manual-test review — the
  feature duplicated the existing PDF report service. Code was written; the test killed it.
- **Issue #226 (sidebar accordion): the first shipped design failed manual testing** — a
  QSplitter-based layout reordered panels on open — and was reworked into the single
  QVBoxLayout design (ADR-030 addendum).
- **US-D1.3: the `layers` render parameter was subtractive-only** — an agent requesting a
  user-hidden layer silently didn't get it. Found only in manual test, after independent
  review had found "no P0/P1s".
- **PR #221 (#218): the rotated-circle resize was geometrically incoherent** (diameter
  collapsed at 45°, ghost pixels) — caught in manual test after tests were green.
- **US-C3: gallery thumbnails rendered round for rectangular trellises** — manual-test fix.

The lesson generalizes: automated tests pin what someone thought to assert; the user finds
what nobody thought of. See `ogp-failure-archaeology` for the full chronicle and
`ogp-validation-and-qa` for what evidence you must present *alongside* the draft PR
(a manual-testing checklist is step 8 of the workflow — always provide one).

### 2.4 senior-reviewer pass before the PR — and re-run after fixes

Launch the `senior-reviewer` agent against the branch diff (fresh worktree, diff vs
`master`) before opening the draft PR. Address every P0/P1, then **re-run for a clean
re-review** — a review of the fix is not implied by a review of the original. The
`finalize-us` skill repeats this gate pre-PR; running it twice is by design.

**Real catches that justify the gate (all in `CLAUDE.md` progress tables):**

- **#213 / PR #217, P0 in round 2:** the species-assignment resize kept the *visual*
  centre fixed but not `transformOriginPoint`, so a **rotated** plant saved a displaced
  position — drift on reload, jump on next rotation. Round 1 missed it.
- **#210 / PR #214, P1 in round 2:** a pending debounced text commit had to be **flushed
  before any form rebuild**, or the rebuild destroyed the field + timer and the edit
  vanished from undo.
- **#206 / PR #222, P1:** the Layer combo's item list is backed by mutable external state;
  refreshing only the selected index left the dropdown stale after a layer rename.
- **#228 / PR #230, P1 in round 1:** the calendar rewrite dropped the frost row's
  `frost_items:<ids>` highlight key — navigation silently broke.

**And one refutation, which is also part of the discipline (#223):** a review P1 claimed
`can_undo/redo_changed` fired conditionally; reading `commands.py` refuted it. Reviews are
*inputs*, not oracles — verify every finding against the code before acting, in both
directions.

### 2.5 Mandatory i18n and mandatory integration test — no exceptions

- **i18n:** every user-visible string goes through `self.tr()` /
  `QCoreApplication.translate("Context", ...)` / `QT_TR_NOOP` (rules and the
  hardcoded-f-string trap: `docs/08-crosscutting-concepts/README.md` §8.3 and the i18n
  block in `CLAUDE.md`). Then register in `scripts/fill_translations.py`, run it and
  `scripts/compile_translations.py` (both with `PYTHONUTF8=1`), and the i18n gate test
  must pass. Known blind spot (§11.4): the gate only sees strings *already extracted* —
  a plain f-string never reaches it; `TestNoHardcodedEnglish` greps for known offenders
  but the primary defence is the `tr()` rule at the call site.
- **Integration test:** every US ships at least one end-to-end workflow test in
  `tests/integration/test_<feature>.py` — "No merge without it. No exceptions."
  (`docs/08-crosscutting-concepts/README.md` §8.10, which also documents the
  tool-API/MagicMock pattern and fixtures). Bug fixes pin their regression with a test at
  the appropriate layer.

### 2.6 Version sync protocol (after every CI release)

GitHub releases are **the** source of truth for the version. After the merge triggers
`release.yml` and the new tag exists:

1. Read the new tag (Windows dev machine):
   ```bash
   "C:\Program Files\GitHub CLI\gh.exe" release list --limit 1 --json tagName --jq '.[0].tagName'
   ```
   In a cloud/Linux session use the GitHub MCP tools instead
   (`mcp__github__get_latest_release`) — the `gh.exe` path above is Windows-specific and
   there is no sanctioned local `gh` invocation documented for Linux here.
2. Update **both** `pyproject.toml` (`version = "X.Y.Z"`, line ~7) and
   `src/open_garden_planner/__init__.py` (`__version__ = "X.Y.Z"`, line ~8) to match.
3. Also update the `CLAUDE.md` progress table / roadmap status in the same commit.
4. Commit as `chore: sync version to vX.Y.Z after US-X.X PR #NNN` and push to master —
   the `chore:` prefix is load-bearing (section 2.2).

### 2.7 Bump size via PR labels, before merging

CI defaults to a **patch** bump. For a minor or major release, add the `minor` or `major`
**label to the PR before merging** — `release.yml` reads the labels of the most recently
merged PR at run time; a label added after the workflow ran does nothing.

### 2.8 Build & verify the frozen exe before every merge

```bash
venv/Scripts/python.exe -m PyInstaller installer/ogp.spec --noconfirm
timeout 8 dist/OpenGardenPlanner/OpenGardenPlanner.exe   # exit code 124 = success (app survived 8 s)
```
Windows-only (the exe cannot run in a Linux cloud session — say so in the PR rather than
skipping silently). Rationale: PyInstaller hidden-import and data-file breakage is
invisible to pytest; D1.1 specifically had to verify the frozen embedded MCP server.
Details in `ogp-build-and-run`.

## 3. The release pipeline as change-control machinery

### `.github/workflows/ci.yml` — the merge gate (every push, every PR to master)

Three parallel jobs on `ubuntu-latest`, Python 3.11:

| Job | Command | Notes |
|-----|---------|-------|
| Lint | `ruff check src/` | |
| Test | `pytest tests/ -v` with `QT_QPA_PLATFORM: offscreen` | Installs Qt's xcb/EGL system libs first — this is the canonical headless-test recipe for Linux sessions too |
| Security | `bandit -r src/ --severity-level high` | Fails only on HIGH severity |

Gate on green before merging: `gh pr checks <PR#> --watch --fail-fast` (Windows) or the
GitHub MCP check-run tools in cloud sessions.

### `.github/workflows/release.yml` — the version authority (push to master only)

Verified behaviour, as of 2026-07-03:

1. **Trigger:** `push` to `master` only.
2. **Chore skip:** job-level
   `if: "!startsWith(github.event.head_commit.message, 'chore:') && !startsWith(github.event.head_commit.message, 'chore(')"`.
3. **Version arithmetic:** latest tag via `git describe --tags --abbrev=0` (fallback
   `v1.0.0`); reads labels of the most recent merged PR to master via
   `gh pr list --state merged --base master --limit 1`; `major` label → major bump,
   `minor` → minor, otherwise **patch**.
4. **Idempotence guard:** if the computed tag already exists, every subsequent step is
   skipped ("Tag ... already exists, skipping release").
5. **Build:** `windows-latest`, installs NSIS via choco, runs
   `python installer/build_installer.py --version X.Y.Z`, produces
   `OpenGardenPlanner-vX.Y.Z-Setup.exe` + `SHA256SUMS.txt`.
6. **Publish:** `gh release create vX.Y.Z ... --generate-notes` — this creates the tag.
   Nothing else in the process ever creates a tag.

Consequences for you: the *squash-merge commit message* is what step 2 inspects (so a
feature PR title must not start with `chore`); the *PR labels at merge time* are what
step 3 inspects; and after any merge you must wait for the tag **transition** (section
2.2) before running the version sync.

`add-to-project.yml` is unrelated to releases: it auto-adds newly opened issues to
project board 1 (owner `cofade`).

## 4. Change checklist — start to finish

The authoritative 12-step table lives in `CLAUDE.md` (Workflow section); this expands it
with gates and sibling-skill pointers. Windows dev commands are canonical; Linux/CI
equivalents in parentheses.

| # | Step | Gate / detail |
|---|------|---------------|
| 1 | Classify the change (section 1) and read the source of truth — US acceptance criteria in `docs/roadmap.md` or the GitHub issue | Do not code from the title alone |
| 2 | `git checkout -b feature/US-X.X-short-description` | Never on master (2.1) |
| 3 | Implement with type hints; wrap every user-visible string for translation as you go | 2.5; architecture invariants: `ogp-architecture-contract`; Qt/CAD theory: `ogp-qt-cad-reference` |
| 4 | Quality checks: `venv/Scripts/python.exe -m pytest tests/ -v` · `-m ruff check src/` · `-m bandit -r src/ --severity-level high` (Linux: `QT_QPA_PLATFORM=offscreen python -m pytest tests/ -v`, etc.) | Same three checks CI runs; how-to details: `ogp-build-and-run` |
| 5 | Translations: register strings in `scripts/fill_translations.py`; `PYTHONUTF8=1 venv/Scripts/python.exe scripts/fill_translations.py` then `scripts/compile_translations.py`; run the i18n gate test | 2.5 |
| 6 | Write the integration test in `tests/integration/test_<feature>.py` | Mandatory (2.5); patterns in §8.10 |
| 7 | Build & smoke the exe (2.8) | Windows-only; declare if skipped in a cloud session |
| 8 | Update docs: FR entry, arc42 sections, ADR if triggered, glossary, §11.4 lessons | Duty matrix: `ogp-docs-and-writing` |
| 9 | senior-reviewer pass; fix all P0/P1; re-run until clean | 2.4 — verify findings against code before acting |
| 10 | Commit `feat(US-X.X): Description`, push, open **draft** PR with summary + test plan + **manual-testing checklist** | 2.3; evidence standards: `ogp-validation-and-qa` |
| 11 | Wait for CI green (`gh pr checks <PR#> --watch --fail-fast`) | Never merge on red |
| 12 | **STOP.** User performs manual testing. Only on their explicit confirmation: add `minor`/`major` label if warranted (2.7), `pr ready`, capture current tag, `pr merge --squash --delete-branch --admin` | 2.3, 2.7 |
| 13 | Wait for the release **tag transition**, then version-sync `chore:` commit to master and wiki/roadmap update | 2.2, 2.6 — the exact wrap-up procedure, including the polling loop, is the `finalize-us` skill; invoke it rather than re-deriving |
| 14 | Delete local branch; `/clear` context | |

If manual testing fails at step 12: fix on the same branch, re-run steps 4–11 (including
a fresh senior-reviewer pass on the delta), keep the PR draft. If the *design* fails,
be prepared to drop the feature — US-B7 shows that is a legitimate outcome.

Reviewing someone else's PR instead of authoring one? Use the existing `analyze-pr` skill
(fetches metadata, runs every locally runnable layer, emits the manual-test plan).
Debugging mid-implementation? `debug-verbose` (project skill) and `ogp-debugging-playbook`.

## When NOT to use this skill

- Running the app, tests, or builds mechanically → `ogp-build-and-run`.
- Deciding what proof a claim needs / what to put in the test-plan checklist → `ogp-validation-and-qa`.
- The wrap-up sequence itself after user approval → invoke the `finalize-us` skill (do not re-implement its steps from memory).
- Which docs to touch and how to write them → `ogp-docs-and-writing`.
- Why the code is shaped the way it is (invariants, ADR digest) → `ogp-architecture-contract`; past incidents in depth → `ogp-failure-archaeology`.
- Qt/CAD mechanics, domain model, settings, diagnostics → `ogp-qt-cad-reference`, `ogp-garden-domain-reference`, `ogp-config-and-flags`, `ogp-diagnostics-and-tooling`.
- License/positioning questions → `ogp-external-positioning`.

## Provenance and maintenance

All claims verified against the repo on 2026-07-03. Re-verify drift-prone facts with:

```bash
# Release trigger, chore skip, label-based bump, tag creation
grep -n "startsWith\|describe --tags\|major\|minor\|release create" .github/workflows/release.yml
# CI jobs: ruff / offscreen pytest / bandit-high
grep -n "ruff check\|QT_QPA_PLATFORM\|pytest tests\|severity-level" .github/workflows/ci.yml
# Current source-of-truth versions (must match the latest GitHub release tag)
grep -n "^version" pyproject.toml && grep -n "__version__" src/open_garden_planner/__init__.py
# .ogp file format version
grep -n "^FILE_VERSION" src/open_garden_planner/core/project.py
# Workflow table, draft-PR mandate, versioning protocol
grep -n "draft\|Never create git tags\|feature branches" CLAUDE.md
# i18n gate test exists
grep -n "test_german_ts_has_no_unfinished" tests/unit/test_i18n.py
# Integration-test mandate wording
grep -n "No merge without it" docs/08-crosscutting-concepts/README.md
# Chore-race incident text
grep -n "Release workflow race condition" docs/11-risks-and-technical-debt/README.md
# Issue #229 date-matching rule + tag-transition wait loop
grep -n "#229\|before_tag" .claude/skills/finalize-us/skill.md
# senior-reviewer agent definition present
head -5 .claude/agents/senior-reviewer.md
```

If any command's output no longer matches this file, update the file — a wrong runbook is
worse than none.
