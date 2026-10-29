---
name: ogp-docs-and-writing
description: >
  Load when finishing ANY feature or fix in Open Garden Planner and you owe documentation
  updates (you always do — this project practices continuous documentation); when writing
  an ADR, an FR-* entry, a pitfall entry (`pitfalls/`, ADR-061), or a debug-verbose case study; when
  updating docs/roadmap.md, docs/functional-requirements.md, or AGENTS.md progress tables;
  when syncing the GitHub wiki; or whenever you are unsure WHERE a piece of knowledge
  should live in the docs. Contains the verified docs-of-record map, the mandatory
  change-type → doc-target tables, the house style derived from real entries, and
  copy-pasteable templates for every document type. The docs are this project's
  institutional memory — every change must leave them better than found.
---

# OGP Docs & Writing

## Current translation gate (#496)

`scripts/check_translations.py` is the required source/catalog/binary gate for every
locale in `SUPPORTED_LANGUAGES`. New wrapped UI keys require all target translations;
new locales require all current keys. Run `update_translations.py`, complete targets
(the fill helper is German-only), compile, then check. No coverage allowances or manual
locale test lists. The compiler rejects incomplete/blank targets and unsupported plural
input; vanished records cannot satisfy coverage. See section 8.3 and docs/TRANSLATING.md.
The older German-only check mentioned in historical examples below is supplementary.
Truly unwrapped UI prose and linguistic quality still require review.


How knowledge is recorded in this repository: which document owns which kind of fact,
what each entry type looks like (derived from real exemplars, not invented), and the
templates to copy. This skill is about *where knowledge lives and how it is written*.
For *what evidence counts as validation* see `ogp-validation-and-qa`; for *process
sequencing* (branch → review → draft PR → merge) see `ogp-change-control`.

Facts date-stamped **as of 2026-09-05**: app version v1.27.7, arc42 chapters 01–12 each
a single `README.md`, ADR register runs ADR-001 … ADR-043 (all in one file), FR register
runs through FR-31 / FR-AGENT-16, §8 crosscutting sections run §8.1 … §8.25.

## When NOT to use this skill

- You need to know *how to run* tests, builds, or translation tooling → `ogp-build-and-run`.
- You are deciding whether a change may merge, or what gates apply → `ogp-change-control`.
- You are writing *test content* or deciding what the integration-test policy requires →
  `ogp-validation-and-qa` (the policy text itself lives in §8.10, but its application is
  that skill's business).
- You are debugging → `ogp-debugging-playbook` / the `debug-verbose` skill. Come back
  here only when the fix is in and you owe the case study + pitfall entry.
- Pure prose polish of an existing doc with no code change attached — just edit it; no
  skill needed.

## 1. The docs of record — verified map

All paths verified to exist **2026-07-04**. Every arc42 chapter is a directory holding a
single `README.md` — there are no per-ADR or per-chapter sub-files.

| Document | Path | Owns |
|----------|------|------|
| Introduction & goals | `docs/01-introduction-and-goals/README.md` | Vision, stakeholders, quality goals |
| Constraints | `docs/02-constraints/README.md` | Technical/organizational constraints |
| Context & scope | `docs/03-context-and-scope/README.md` | External systems, APIs |
| Solution strategy | `docs/04-solution-strategy/README.md` | Top-level technical strategy |
| Building block view | `docs/05-building-block-view/README.md` | Module structure, project tree, black-box descriptions of every component |
| Runtime view | `docs/06-runtime-view/README.md` | Sequence diagrams, runtime behavior |
| Deployment view | `docs/07-deployment-view/README.md` | CI/CD, installer, release process |
| Crosscutting concepts | `docs/08-crosscutting-concepts/README.md` | §8.1–§8.25: coordinate system, commands, **i18n (§8.3)**, **QGraphicsView patterns (§8.9)**, **integration-test policy (§8.10)**, **SAST (§8.11)**, **bed-only features (§8.14)**, sidebar accordion (§8.17), smart symbols (§8.18), agent API (§8.19), icon/sprite/texture pipelines (§8.21–§8.24), stacking order (§8.25) |
| ADR register | `docs/09-architecture-decisions/README.md` | **All** ADRs (ADR-001…043) in this ONE file — append new ADRs here, never create a separate file |
| Quality requirements | `docs/10-quality-requirements/README.md` | Quality scenarios |
| Risks & technical debt | `docs/11-risks-and-technical-debt/README.md` | §11.1 open questions, §11.2 risks, §11.3 TD-* debt register (living: Status + Issue columns, ADR-047; dated audit snapshots under `audits/YYYY-MM/`), **§11.4 navigation table to the pitfall area indexes** (`pitfalls/index/NN-*.md`, ADR-061) |
| Glossary | `docs/12-glossary/README.md` | §12.1 terms, §12.2 keyboard shortcuts, §12.3 references |
| Roadmap | `docs/roadmap.md` | User stories, acceptance criteria, per-US completion notes, "Docs updated on completion" tables |
| FR register | `docs/functional-requirements.md` | Numbered FR-* requirements, the specification of user-visible capability |
| Translation guide | `docs/TRANSLATING.md` | How to add a new language (`.ts`/`.qm` pipeline) |
| AGENTS.md | `AGENTS.md` (repo root) | Quick reference commands, workflow, phase progress tables. **A maintained doc** — its own "Maintaining this file" note requires updating the progress table when US status changes and keeping commands current |
| Debug case-study log | `.agents/skills/debug-verbose/SKILL.md` | Growing list of `## Case study:` entries — one per non-trivial bug fixed |
| GitHub wiki | `docs/wiki/README.md` | Six repository-owned source pages. Canonical roadmap inclusions render through `scripts/sync_wiki.py`. Validate offline before delivery. Publish to the separate sibling wiki checkout after owner approval and protected merge. If absent, report publication pending. Do not silently clone or edit the published pages as a second tracker (ADR-051). |
| This skill library | `.agents/skills/<name>/SKILL.md` | Operational knowledge for agents — see §7 below |

## 2. The mandatory-update tables (from AGENTS.md — binding)

These are reproduced faithfully from AGENTS.md. They are not suggestions; the workflow's
pre-merge check ("arc42 docs updated, ADRs created if needed, glossary updated, wiki
synced") assumes they were followed.

**After implementing a feature:**

| Change Type | Update Target |
|-------------|---------------|
| New component/module | `docs/05-building-block-view/` — add black box description |
| New UI pattern | `docs/08-crosscutting-concepts/` section 8.9 |
| Changed runtime behavior | `docs/06-runtime-view/` — update sequence diagrams |
| New user-facing capability | `docs/functional-requirements.md` — add FR-* entry |
| Architecture decision | `docs/09-architecture-decisions/` — create ADR |
| New domain term | `docs/12-glossary/` — add definition |

**After solving issues, all lessons learned MUST be documented:**

| Issue Category | Document In | Capture |
|----------------|-------------|---------|
| PyQt6 quirks | `docs/11-risks-and-technical-debt/pitfalls/` (area file; index row in pitfalls/index/) | Rule → Pinned by → Fix |
| Performance issues | `docs/08-crosscutting-concepts/` | Optimization technique |
| Testing patterns | `docs/08-crosscutting-concepts/` §8.10 | How to test this pattern |
| Security fixes | `docs/08-crosscutting-concepts/` §8.11 | Vulnerability + mitigation |

**ADR triggers** — create an ADR when: introducing a new dependency; choosing between
approaches; changing established patterns; addressing non-obvious constraints.

**Pre-merge doc checklist** (verify before any merge): arc42 docs updated, ADRs created
if needed, glossary updated (terms **and** any new keyboard shortcut in §12.2), wiki
sources validated and publication prepared (or flagged pending — see §1), roadmap status + "Docs updated on completion"
table written, AGENTS.md progress table current, new keyboard shortcuts in glossary.

Additional targets observed in practice (beyond the AGENTS.md tables):
- Every non-trivial bug fix → **Case study** in `.agents/skills/debug-verbose/SKILL.md`
  (the skill's own "How this skill grows" section mandates it).
- New/changed UI strings → source inventory and every registered target catalog (see §6).
- Known-but-deferred debt → a `TD-*` row in §11.3 (with Status and Issue, ADR-047), or a filed follow-up issue referenced
  from the roadmap note (house pattern: "Follow-up #NNN filed: …").

## 3. House style, from real exemplars

### 3.1 Pitfall entry anatomy (ADR-061)

Standing rules live in `docs/11-risks-and-technical-debt/pitfalls/NN-<area>.md`, one entry
per lesson, each with a permanent ID `PF-<AREA>-<NN>`. Take the next free number for the
area; IDs are never reused. The corresponding area index in `docs/11-risks-and-technical-debt/pitfalls/index/NN-<area>.md` gets one row per entry (and §11.4 in the chapter README links to each area index).
Read a few entries of the area before writing one, and match their shape.

An entry is a heading and five fields; the body follows:

- **Rule:** one sentence, imperative or invariant, so a skimmer gets the contract without
  the story.
- **Pinned by:** the test or tests that fail when the rule breaks, each as
  `tests/<path>.py::<name>`, separated by `; `, or `none — <reason>`. Only files under
  `tests/` pin: a script or a source file cannot. The gate checks that each file and
  function exists; a reviewer checks that the test enforces the rule.
- **Source:** the issues, PRs and ADRs the lesson came from.
- **Status:** `standing`; `pointer → [home](link)` when an ADR addendum, a §8 section or a
  skill already holds the mechanism; `standing; narrative in [archive/…](link)` when the
  story has been archived; or `retired; narrative in [archive/13-retired.md](../archive/13-retired.md#…)`.
- **Legacy:** `b1faaa9 README L2526 (legacy 11.4.17)` for an entry moved from a numbered diary,
  `b1faaa9 README L183` for a bullet, or `none (new entry)` for an entry written after the restructure.

The body names symptom, root cause and fix in that order, with files and functions in
backticks, then the contract future callers rely on. Keep it short: the story belongs in
an archive narrative.

Rules that follow from the layout:

1. If a fact is already held in substance elsewhere, do not repeat it. Merge any missing
   sentence into that home first, then make the entry a pointer.
2. A fixed bug keeps its rule and its entry; its story moves to the archive and is never
   deleted. Retired work keeps its ID.
3. A process rule belongs to CLAUDE.md and AGENTS.md when it applies to every session, or to
   the skill that owns the process. The PRC area keeps only the lessons that have no such home.
4. `tests/unit/test_pitfall_catalogue.py` holds the index to the entries (IDs, rule, status,
   legacy number and anchor), each pointer's home (its issue numbers and pins), the pins, the
   archive links, the redirect table and the size budgets, and bans legacy numbered citations
   outside the archive. Run it after any change to the catalogue.

### 3.2 ADR format (`docs/09-architecture-decisions/README.md`)

All ADRs live in the one README, headed `## ADR-NNN: Title`. Two observed generations:

- **Early ADRs (001–011)**: four terse bold-labelled lines — `**Status**`,
  `**Context**`, `**Decision**`, `**Rationale**`, `**Consequences**` — one sentence or
  two each (see ADR-001 PyQt6, ADR-002 Y-Up).
- **Modern ADRs (020+)**: same labels but expanded — `**Status**: Accepted (issue #NNN)`;
  a Context paragraph naming the forces; a **numbered, bold-led Decision list** (each
  point one committed mechanism with file paths); an explicit `**Alternatives
  considered**` bullet list, each with the reason for rejection (including first cuts
  that *shipped and failed manual testing* — see ADR-028's rejected post-correction);
  `**Consequences**` naming added files, format impact ("No `.ogp` format change"), and
  the pinning tests; and **`**Addendum (PR #NNN)**` paragraphs** appended when later
  work refines the decision rather than replacing it (ADR-029 has two).

Write new ADRs in the modern form. Number = max existing + 1 (grep `^## ADR-` first —
the file is NOT in strictly ascending order; ADR-013 sits after ADR-015). Re-grep just
before opening the PR too: a parallel branch can take your number while yours is in
review (the sim clock's ADR-052 became ADR-053 when #426 merged first, and every
reference had to move — `git grep -l "ADR-052"` on the branch, not on master). Reference
the ADR from AGENTS.md progress notes, the roadmap completion note, and any related
§8 section or pitfall entry.

### 3.3 Roadmap style (`docs/roadmap.md`)

- Completed phases get `~~strikethrough~~` in the top phase table; US status tables use
  `✅` rows: `| ✅ | C1 | One-line description — see FR-23 / ADR-029 |`.
- Each delivered US/package gets an `### … acceptance highlights` bullet list: dense,
  evidence-linked — names the mechanism (`services/harvest_aggregation`), the undo
  story, the persistence story ("additive `.ogp` key, no `FILE_VERSION` bump"), review
  rounds and **manual-test fixes** ("First cut used a bottom `QSplitter` … reworked
  after manual testing"), and cross-refs (FR-*, ADR-*, §8.x).
- Each completed section ends with a `### Docs updated on completion` two-column table
  (`| Document | Section |`) listing exactly which docs were touched — **write this
  table as you update the docs**; it is the receipt.
- Deferred scope gets its own `### Out of scope (deferred)` list; follow-up gaps found
  in manual testing get a follow-up table ("Package B follow-ups" pattern).

### 3.4 FR entry format (`docs/functional-requirements.md`)

Top-level sections `## FR-N: Title` — recent ones carry provenance in the heading:
`## FR-23: Harvest Tracking / Yield Log (Phase 13, Package C, US-C1, issue #188)`.
Under each, bulleted requirement IDs: `- **FR-<AREA>-NN**: requirement text` (e.g.
`FR-LAYER-09`, `FR-AGENT-09`). Requirement text is testable and specific — clamp
ranges, key bindings, behavior on the error path ("unknown names match nothing, not an
error"), and back-compat guarantees are stated inline. Issue numbers appear in the
requirement when it originated from one (`(issue #201)`). Never renumber existing IDs;
append.

## 4. Templates (copy-paste, derived from the real formats above)

### Pitfall entry (`docs/11-risks-and-technical-debt/pitfalls/`)

```markdown
### PF-<AREA>-<NN>

- **Rule:** <one-line imperative rule, e.g. "Sidebar list panels must store item ids, not live `QGraphicsItem` refs">
- **Pinned by:** `tests/<path>.py::<test_name>` (or `none — <reason>`)
- **Source:** #NNN, PR #NNN, ADR-0NN
- **Status:** standing
- **Legacy:** none (new entry)

Symptom as observed: <what the user saw, quoted where possible>. Root cause: <what the code
actually did, with `file.py` and `function()` names>. Fix: <what changed, where, and the
contract any future caller must follow>.
```

### ADR (modern form, append to `docs/09-architecture-decisions/README.md`)

```markdown
## ADR-0NN: <Title> (US-X.X / issue #NNN)

**Status**: Accepted (issue #NNN)

**Context**: <The forces. What existed, what broke or was missing, why now. Name the
files/subsystems involved.>

**Decision**:
1. **<Mechanism one.>** <What, where (`path/to/file.py`), and the invariant it creates.>
2. **<Mechanism two.>** <…>

**Alternatives considered**:
- *<Alternative>.* <Why rejected — including any first cut that shipped and failed
  manual testing.>

**Consequences**: <Files added/changed, `.ogp` format impact ("no FILE_VERSION bump" /
bump + migration), dependencies, user-visible strings. Tests: `tests/...` (what they
pin). Cross-refs: FR-*, §8.x, PF-*.>
```

(Refinements later: append `**Addendum (PR #NNN)**: …` — do not rewrite the Decision.)

### FR entry (append to `docs/functional-requirements.md`)

```markdown
## FR-NN: <Capability Title> (Phase X, Package Y, US-X.X, issue #NNN)

- **FR-<AREA>-01**: <Testable requirement: exact behavior, bindings, ranges, error-path
  behavior, back-compat guarantee.>
- **FR-<AREA>-02**: <…>
```

### Roadmap completion (status row + section, in `docs/roadmap.md`)

```markdown
| Status | US    | Description                                                      |
| ------ | ----- | ---------------------------------------------------------------- |
| ✅     | X.X   | <One-line summary> — see FR-NN / ADR-0NN                          |

### US-X.X acceptance highlights
- **<Headline capability>** — <mechanism, file names, undo story, persistence story
  (additive key vs FILE_VERSION bump), review rounds, manual-test fixes>.

### Out of scope (deferred)
- <Deferred item + tracking issue if filed>

### Docs updated on completion
| Document | Section |
|----------|---------|
| `docs/09-architecture-decisions/` | ADR-0NN |
| `docs/functional-requirements.md` | FR-NN (FR-<AREA>-01…NN) |
| `docs/05-building-block-view/` | <new modules> |
| `docs/12-glossary/` | <new terms / shortcuts> |
```

### Debug-verbose case study (add a mirrored reference and update its case index)

```markdown
## Case study: <short symptom title> (fixed YYYY-MM-DD)

**Symptom**: <one line, as the user saw it>.

**Theories entertained (wrong)**:
- <wrong theory 1>
- <wrong theory 2>

**What instrumentation revealed** (<the reproduction step>):

```
[TAG] <the key log lines, annotated with ← markers>
```

**Root cause**: <one sentence>.

**Fix** (<scope, e.g. "one line in file.py">): <what changed>.

**Lesson**: <what to do differently next time>.
```

## 5. Where does this knowledge live? (decision aid)

| The thing you learned/built | Record it in |
|-----------------------------|--------------|
| "We chose X over Y because Z" | ADR (docs/09) |
| "The app can now do X" (user-visible) | FR-* + roadmap highlights (+ glossary if new term/shortcut) |
| "Qt/PyQt6 bit me; here's the contract" | pitfall entry in `pitfalls/` (+ debug-verbose case study if instrumented) |
| "This is how you build/test this kind of widget" | §8.9 (UI pattern) / §8.10 (test pattern) |
| "New module exists; here's its responsibility" | docs/05 black box |
| "The startup/save/render sequence changed" | docs/06 sequence diagrams |
| "Known debt, deliberately deferred" | §11.3 TD-* row or filed issue, referenced from roadmap note |
| "Operational knowledge an agent needs" | the relevant `.agents/skills/*/SKILL.md` |
| "US finished / phase status changed" | roadmap table + AGENTS.md progress table (both) |

One fact, one home; everywhere else links to it. The roadmap note *cites* ADR/FR/§8; it
does not restate them.

## 6. Writing rules

- **Docs are English.** Only the *application UI* is translated. But every user-visible
  string your change adds to the APP must go through `tr()` / `QT_TR_NOOP` /
  `QCoreApplication.translate()` and be covered in every registered target catalog —
  full rules in AGENTS.md "Translation (i18n)" and §8.3; new-language how-to in
  `docs/TRANSLATING.md`. The required gate is `scripts/check_translations.py`; it
  cannot see hardcoded f-strings that bypass `tr()` entirely.
- **UTF-8 discipline — never PowerShell `Set-Content -Encoding UTF8`** on any file with
  non-ASCII (umlauts, "—", "→" — which these docs use heavily). PowerShell 5.1
  double-encodes (`ö` → `Ã¶`); the §11.4 mojibake incident corrupted
  `fill_translations.py` + the German `.ts` this way. Use the `Edit` tool, Python
  `open(..., encoding="utf-8")`, `sed -i.bak`, or `perl -i -pe`. Detect regressions:
  `grep -c "Ã¶\|Ã¤\|Ã¼\|ÃŸ" <file>` — any hit means double-encoded.
- **Keep AGENTS.md current**: when a US ships, update its progress-table row (status +
  the dense completion note style you see there); when a command changes, fix Quick
  Reference. AGENTS.md's own "Maintaining this file" note makes this mandatory.
- **Wiki sync duty**: edit repository sources in `docs/wiki/`, then run `scripts/sync_wiki.py --check`.
  Render a preview outside the repository. Follow `docs/wiki/README.md` after owner approval and
  protected merge. Read and reconcile direct wiki edits before publishing. An absent sibling
  checkout leaves publication pending. CI never accesses or publishes the live wiki (ADR-051).
- **Cite evidence**: issue/PR numbers, test paths, and file paths in every entry. The
  house style is falsifiable prose — a claim without a `tests/...` or `file.py`
  reference is below the bar set by existing entries.
- **Date-stamp volatile facts** in skills and process docs ("as of 2026-07-04: …"), so
  staleness is detectable.

## 7. This skill library is itself a doc of record

- Skills live at `.agents/skills/<name>/SKILL.md` with YAML frontmatter (`name`,
  trigger-rich `description`) — same shape as `ogp-change-control` and this file.
- Each ends with a **Provenance and maintenance** section: one-line commands that
  re-verify the skill's load-bearing claims. House rule (quoted from
  `ogp-change-control`): *"If any command's output no longer matches this file, update
  the file — a wrong runbook is worse than none."*
- **When a code change invalidates a skill claim, updating the skill is part of the
  change** — same spirit as the AGENTS.md mandatory-update tables. Grep the library
  before merging anything that renames a file, command, or invariant a skill cites:
  `grep -rl "<old name>" .agents/skills/`.
- The pre-existing skills follow the same growth contract: `debug-verbose` grows a case
  study per bug; `finalize-us` and `analyze-pr` encode process that must track reality.
- Siblings in this 16-skill library: `ogp-change-control` (process gates),
  `ogp-debugging-playbook`, `ogp-failure-archaeology`, `ogp-architecture-contract`,
  `ogp-qt-cad-reference`, `ogp-garden-domain-reference`, `ogp-config-and-flags`,
  `ogp-build-and-run`, `ogp-diagnostics-and-tooling`, `ogp-validation-and-qa`,
  `ogp-external-positioning`, `ogp-3d-sunshade-campaign`, `ogp-proof-and-analysis-toolkit`,
  `ogp-research-frontier`, `ogp-research-methodology`.

## Provenance and maintenance

Derived 2026-07-04 from: AGENTS.md (mandatory-update tables reproduced verbatim);
`docs/11-risks-and-technical-debt/README.md` §11.4 (entries #212, #213/#218/#219, #231,
US-C4 read as anatomy exemplars); `docs/09-architecture-decisions/README.md` (ADR-001,
ADR-028, ADR-029 + addenda); `docs/functional-requirements.md` (FR-1, FR-23 heading,
FR-AGENT-09); `docs/roadmap.md` (Package B follow-ups + US-C1/C2 sections);
`.agents/skills/debug-verbose/SKILL.md` (case-study format + growth contract);
`.agents/skills/ogp-change-control/SKILL.md` (skill house style). Wiki sibling repo
verified ABSENT in this checkout.

Re-verify:

```bash
# All arc42 chapters + key docs still exist
ls docs/{01..12}*/README.md docs/roadmap.md docs/functional-requirements.md docs/TRANSLATING.md
# ADRs still single-file; current max ADR number
grep -c "^## ADR-" docs/09-architecture-decisions/README.md && grep "^## ADR-" docs/09-architecture-decisions/README.md | sort -V | tail -1
# §11.4 still the pitfalls section; §8 section map unchanged
grep -n "^## 11.4" docs/11-risks-and-technical-debt/README.md; grep -c "^### PF-" docs/11-risks-and-technical-debt/pitfalls/*.md; grep -c "^## 8\." docs/08-crosscutting-concepts/README.md
# AGENTS.md mandatory tables unchanged
grep -n "Update Target\|Document In" AGENTS.md
# Debug-verbose case-study count (grows over time)
grep -c "^## Case study" .agents/skills/debug-verbose/SKILL.md
# Wiki sibling present in THIS checkout?
ls ../open-garden-planner.wiki/Roadmap.md 2>/dev/null || echo "wiki absent — flag sync as pending"
```

If any command's output no longer matches this file, update the file — a wrong runbook
is worse than none.
