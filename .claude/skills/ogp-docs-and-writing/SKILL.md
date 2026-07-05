---
name: ogp-docs-and-writing
description: >
  Load when finishing ANY feature or fix in Open Garden Planner and you owe documentation
  updates (you always do — this project practices continuous documentation); when writing
  an ADR, an FR-* entry, a §11.4 pitfall entry, or a debug-verbose case study; when
  updating docs/roadmap.md, docs/functional-requirements.md, or CLAUDE.md progress tables;
  when syncing the GitHub wiki; or whenever you are unsure WHERE a piece of knowledge
  should live in the docs. Contains the verified docs-of-record map, the mandatory
  change-type → doc-target tables, the house style derived from real entries, and
  copy-pasteable templates for every document type. The docs are this project's
  institutional memory — every change must leave them better than found.
---

# OGP Docs & Writing

How knowledge is recorded in this repository: which document owns which kind of fact,
what each entry type looks like (derived from real exemplars, not invented), and the
templates to copy. This skill is about *where knowledge lives and how it is written*.
For *what evidence counts as validation* see `ogp-validation-and-qa`; for *process
sequencing* (branch → review → draft PR → merge) see `ogp-change-control`.

Facts date-stamped **as of 2026-07-04**: app version v1.23.0, arc42 chapters 01–12 each
a single `README.md`, ADR register runs ADR-001 … ADR-034 (all in one file), FR register
runs through FR-26 / FR-AGENT-09, §8 crosscutting sections run §8.1 … §8.19.

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
| Crosscutting concepts | `docs/08-crosscutting-concepts/README.md` | §8.1–§8.19: coordinate system, commands, **i18n (§8.3)**, **QGraphicsView patterns (§8.9)**, **integration-test policy (§8.10)**, **SAST (§8.11)**, **bed-only features (§8.14)**, sidebar accordion (§8.17), smart symbols (§8.18), agent API (§8.19) |
| ADR register | `docs/09-architecture-decisions/README.md` | **All** ADRs (ADR-001…034) in this ONE file — append new ADRs here, never create a separate file |
| Quality requirements | `docs/10-quality-requirements/README.md` | Quality scenarios |
| Risks & technical debt | `docs/11-risks-and-technical-debt/README.md` | §11.1 open questions, §11.2 risks, §11.3 TD-* debt register, **§11.4 Known Development Pitfalls** (the hard-won-lessons log) |
| Glossary | `docs/12-glossary/README.md` | §12.1 terms, §12.2 keyboard shortcuts, §12.3 references. NOTE: CLAUDE.md's table says `docs/12-glossary.md` — the real path is the directory form |
| Roadmap | `docs/roadmap.md` | User stories, acceptance criteria, per-US completion notes, "Docs updated on completion" tables |
| FR register | `docs/functional-requirements.md` | Numbered FR-* requirements (~289 FR references), the specification of user-visible capability |
| Translation guide | `docs/TRANSLATING.md` | How to add a new language (`.ts`/`.qm` pipeline) |
| CLAUDE.md | `CLAUDE.md` (repo root) | Quick reference commands, workflow, phase progress tables. **A maintained doc** — its own "Maintaining this file" note requires updating the progress table when US status changes and keeping commands current |
| Debug case-study log | `.claude/skills/debug-verbose/skill.md` | Growing list of `## Case study:` entries — one per non-trivial bug fixed |
| GitHub wiki | `../open-garden-planner.wiki/Roadmap.md` | Public mirror of the roadmap. **NOT present in cloud/CI checkouts** (verified absent here — `ls ..` shows only the main repo). Handling: if the sibling directory is absent, note "wiki sync pending" in your handoff/PR body so it is done from a full local checkout; do not silently skip the duty, and do not try to clone it without being asked |
| This skill library | `.claude/skills/<name>/SKILL.md` | Operational knowledge for agents — see §7 below |

## 2. The mandatory-update tables (from CLAUDE.md — binding)

These are reproduced faithfully from CLAUDE.md. They are not suggestions; the workflow's
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
| PyQt6 quirks | `docs/11-risks-and-technical-debt/` §11.4 | Symptoms → Root cause → Fix |
| Performance issues | `docs/08-crosscutting-concepts/` | Optimization technique |
| Testing patterns | `docs/08-crosscutting-concepts/` §8.10 | How to test this pattern |
| Security fixes | `docs/08-crosscutting-concepts/` §8.11 | Vulnerability + mitigation |

**ADR triggers** — create an ADR when: introducing a new dependency; choosing between
approaches; changing established patterns; addressing non-obvious constraints.

**Pre-merge doc checklist** (verify before any merge): arc42 docs updated, ADRs created
if needed, glossary updated (terms **and** any new keyboard shortcut in §12.2), wiki
synced (or flagged pending — see §1), roadmap status + "Docs updated on completion"
table written, CLAUDE.md progress table current, new keyboard shortcuts in glossary.

Additional targets observed in practice (beyond the CLAUDE.md tables):
- Every non-trivial bug fix → **Case study** in `.claude/skills/debug-verbose/skill.md`
  (the skill's own "How this skill grows" section mandates it).
- New/changed UI strings → registration in `scripts/fill_translations.py` (see §6).
- Known-but-deferred debt → a `TD-*` row in §11.3, or a filed follow-up issue referenced
  from the roadmap note (house pattern: "Follow-up #NNN filed: …").

## 3. House style, from real exemplars

### 3.1 §11.4 pitfall entry anatomy

Observed across ~30 real entries (e.g. the #212 sidebar-list entry, the #231 enum-combo
entry, the US-C4 trust-boundary entry). Structure of a strong entry:

1. **Bold one-line rule first** — the generalized imperative, so a skimmer gets the
   contract without reading the story. E.g. *"Sidebar list panels must store item ids,
   not live QGraphicsItem refs, and defer the selection"* (issue #212); *"At a trust
   boundary that ingests untrusted files, catch `Exception` at the ingestion seam — do
   NOT enumerate exception families"* (PR #236).
2. Issue/PR number in parentheses right after the bold rule.
3. Symptom as the user saw it (often quoted: *"handle shows but won't move"*, *"list
   jumps back to the top"*).
4. Root cause, with file/function names in backticks.
5. Fix, naming the exact code location and contract for future callers.
6. **"Pinned by `tests/...`"** — the regression test that enforces the lesson.
7. A closing generalized **Lesson/Rule** sentence.

Entries are single bullets (`- **Rule**: …`), long is fine. Follow-ups nest as indented
bold-led paragraphs under the parent bullet (see the #213 entry's *"Manual-test
follow-up"* / *"Second trap"* / *"Closed (#219)"* sub-paragraphs). When a pitfall is
later fixed structurally, do NOT delete it — retitle it **"Closed (#NNN): …"** and
describe what retired it (see the #228 dual-store entry). The section header's standing
instruction: *"Hard-won lessons from implementation. Read these before modifying the
related subsystems."*

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
the file is NOT in strictly ascending order; ADR-013 sits after ADR-015). Reference the
ADR from CLAUDE.md progress notes, the roadmap completion note, and any related §8/§11.4
entry.

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

### §11.4 pitfall entry

```markdown
- **<Generalized one-line rule in imperative form>** (issue #NNN / PR #NNN): <symptom
  as observed — quote the user-visible behavior>. <Root cause: what the code actually
  did, with `file.py` / `function()` names>. Fix: <what changed, where, and the
  contract any future caller must follow>. Pinned by `tests/<path>::<test_name>`.
  <Lesson: the generalized takeaway in one or two sentences.>
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
pin). Cross-refs: FR-*, §8.x, §11.4.>
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

### Debug-verbose case study (append to `.claude/skills/debug-verbose/skill.md`)

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
| "Qt/PyQt6 bit me; here's the contract" | §11.4 pitfall (+ debug-verbose case study if instrumented) |
| "This is how you build/test this kind of widget" | §8.9 (UI pattern) / §8.10 (test pattern) |
| "New module exists; here's its responsibility" | docs/05 black box |
| "The startup/save/render sequence changed" | docs/06 sequence diagrams |
| "Known debt, deliberately deferred" | §11.3 TD-* row or filed issue, referenced from roadmap note |
| "Operational knowledge an agent needs" | the relevant `.claude/skills/*/SKILL.md` |
| "US finished / phase status changed" | roadmap table + CLAUDE.md progress table (both) |

One fact, one home; everywhere else links to it. The roadmap note *cites* ADR/FR/§8; it
does not restate them.

## 6. Writing rules

- **Docs are English.** Only the *application UI* is translated. But every user-visible
  string your change adds to the APP must go through `tr()` / `QT_TR_NOOP` /
  `QCoreApplication.translate()` and be registered in `scripts/fill_translations.py` —
  full rules in CLAUDE.md "Translation (i18n)" and §8.3; new-language how-to in
  `docs/TRANSLATING.md`. Remember the §11.4 lesson: `test_german_ts_has_no_unfinished`
  cannot see hardcoded f-strings that bypass `tr()` entirely.
- **UTF-8 discipline — never PowerShell `Set-Content -Encoding UTF8`** on any file with
  non-ASCII (umlauts, "—", "→" — which these docs use heavily). PowerShell 5.1
  double-encodes (`ö` → `Ã¶`); the §11.4 mojibake incident corrupted
  `fill_translations.py` + the German `.ts` this way. Use the `Edit` tool, Python
  `open(..., encoding="utf-8")`, `sed -i.bak`, or `perl -i -pe`. Detect regressions:
  `grep -c "Ã¶\|Ã¤\|Ã¼\|ÃŸ" <file>` — any hit means double-encoded.
- **Keep CLAUDE.md current**: when a US ships, update its progress-table row (status +
  the dense completion note style you see there); when a command changes, fix Quick
  Reference. CLAUDE.md's own "Maintaining this file" note makes this mandatory.
- **Wiki sync duty**: `../open-garden-planner.wiki/Roadmap.md` mirrors the roadmap.
  Absent in this checkout (verified) — flag "wiki sync pending" in the PR body instead
  of skipping silently.
- **Cite evidence**: issue/PR numbers, test paths, and file paths in every entry. The
  house style is falsifiable prose — a claim without a `tests/...` or `file.py`
  reference is below the bar set by existing entries.
- **Date-stamp volatile facts** in skills and process docs ("as of 2026-07-04: …"), so
  staleness is detectable.

## 7. This skill library is itself a doc of record

- Skills live at `.claude/skills/<name>/SKILL.md` with YAML frontmatter (`name`,
  trigger-rich `description`) — same shape as `ogp-change-control` and this file.
- Each ends with a **Provenance and maintenance** section: one-line commands that
  re-verify the skill's load-bearing claims. House rule (quoted from
  `ogp-change-control`): *"If any command's output no longer matches this file, update
  the file — a wrong runbook is worse than none."*
- **When a code change invalidates a skill claim, updating the skill is part of the
  change** — same spirit as the CLAUDE.md mandatory-update tables. Grep the library
  before merging anything that renames a file, command, or invariant a skill cites:
  `grep -rl "<old name>" .claude/skills/`.
- The pre-existing skills follow the same growth contract: `debug-verbose` grows a case
  study per bug; `finalize-us` and `analyze-pr` encode process that must track reality.
- Siblings in this 16-skill library: `ogp-change-control` (process gates),
  `ogp-debugging-playbook`, `ogp-failure-archaeology`, `ogp-architecture-contract`,
  `ogp-qt-cad-reference`, `ogp-garden-domain-reference`, `ogp-config-and-flags`,
  `ogp-build-and-run`, `ogp-diagnostics-and-tooling`, `ogp-validation-and-qa`,
  `ogp-external-positioning`, `ogp-3d-sunshade-campaign`, `ogp-proof-and-analysis-toolkit`,
  `ogp-research-frontier`, `ogp-research-methodology`.

## Provenance and maintenance

Derived 2026-07-04 from: CLAUDE.md (mandatory-update tables reproduced verbatim);
`docs/11-risks-and-technical-debt/README.md` §11.4 (entries #212, #213/#218/#219, #231,
US-C4 read as anatomy exemplars); `docs/09-architecture-decisions/README.md` (ADR-001,
ADR-028, ADR-029 + addenda); `docs/functional-requirements.md` (FR-1, FR-23 heading,
FR-AGENT-09); `docs/roadmap.md` (Package B follow-ups + US-C1/C2 sections);
`.claude/skills/debug-verbose/skill.md` (case-study format + growth contract);
`.claude/skills/ogp-change-control/SKILL.md` (skill house style). Wiki sibling repo
verified ABSENT in this checkout.

Re-verify:

```bash
# All arc42 chapters + key docs still exist
ls docs/{01..12}*/README.md docs/roadmap.md docs/functional-requirements.md docs/TRANSLATING.md
# ADRs still single-file; current max ADR number
grep -c "^## ADR-" docs/09-architecture-decisions/README.md && grep "^## ADR-" docs/09-architecture-decisions/README.md | sort -V | tail -1
# §11.4 still the pitfalls section; §8 section map unchanged
grep -n "^## 11.4" docs/11-risks-and-technical-debt/README.md; grep -c "^## 8\." docs/08-crosscutting-concepts/README.md
# CLAUDE.md mandatory tables unchanged
grep -n "Update Target\|Document In" CLAUDE.md
# Debug-verbose case-study count (grows over time)
grep -c "^## Case study" .claude/skills/debug-verbose/skill.md
# Wiki sibling present in THIS checkout?
ls ../open-garden-planner.wiki/Roadmap.md 2>/dev/null || echo "wiki absent — flag sync as pending"
```

If any command's output no longer matches this file, update the file — a wrong runbook
is worse than none.
