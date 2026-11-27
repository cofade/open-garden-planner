---
id: ADR-061
title: "The pitfall catalogue — numbered area files, permanent IDs, one index and a verbatim archive"
status: "Accepted (2026-10-20). Owner review of the dedupe table and of the pins flagged for a human look is pending. Supersedes the single-section layout of §11.4 (\"Known Development Pitfalls\") that ADR-047 left in place. The audit family's move is recorded in the ADR-047 addendum above."
legacy_anchor: adr-061-the-pitfall-catalogue--numbered-area-files-permanent-ids-one-index-and-a-verbatim-archive
---

# ADR-061: The pitfall catalogue — numbered area files, permanent IDs, one index and a verbatim archive

**Status**: Accepted (2026-10-20). Owner review of the dedupe table and of the pins flagged for a human look is pending. Supersedes the single-section layout of §11.4 ("Known Development Pitfalls") that ADR-047 left in place. The audit family's move is recorded in the ADR-047 addendum above.

## Context

At b1faaa9 the chapter README was 3,432 lines and 532 KB. Its §11.4 ("Known Development Pitfalls") was 498 KB in two parts: 145 unstructured items in the intro (240 KB) and 21 numbered diaries (258 KB), of which the nine Phase 17 L-step diaries (numbered 12 to 20) held 180 KB. Every feature PR appended to that one file, and the README changed in 27 of the 50 commits visible in the shallow clone. The numbering was broken: diary 6 named two different entries, the headings were out of order, and six engineering lessons sat under §11.5. The citation gate (`scripts/check_skill_citations.py`) resolves `§N.M` against the headings of the skill files and of the chapter READMEs. The `§11.4` heading is kept, so bare references still resolve; the numbered forms are retired.

## Decision

1. **Layout.** The chapter README keeps §11.1 to §11.3 and §11.5 (governance only). Its §11.4 is the index: one row per entry (ID, rule, status, where, legacy) and a redirect table from the 20 legacy numbers, which has 23 rows because diary 6 names two entries and diary 17 names three. Standing rules live in `pitfalls/01…12-*.md`, one file per area (3 KB to 52 KB). Narratives are copied verbatim into `archive/01…13-*.md`: 01 to 11 are the Phase 17 L-steps, 12 holds incidents outside Phase 17, and 13 holds retired work.
2. **IDs.** `PF-<AREA>-<NN>`, with the area codes CAN, LIF, PER, UI, I18, CI, TST, API, DOM, E3D, L3D and PRC. An ID is never reused, and a pointer or retired entry keeps its ID. The numbers in the file names give reading order only.
3. **Entry template.** A `### PF-…` heading, then the fields **Rule** (one sentence, with no pipe and no bold), **Pinned by** (`tests/…py` or `tests/…py::name`, joined by `; `, or `none — <reason>`), **Source** (issues, PRs and ADRs), **Status** (`standing`, `standing; narrative in […]`, `pointer → […]` or `retired; narrative in […]`) and **Legacy** (`b1faaa9 README L…`, with the legacy number of a numbered diary). A standing entry keeps its verbatim b1faaa9 body where it has one, with relative links re-based for `pitfalls/`; a narrative with no entry body lives in the archive.
4. **Canonical home.** A fact already held in substance in an ADR addendum, a §8 section or a skill is not repeated. An entry becomes a pointer only when its home section holds the entry's issue numbers, the test files and functions its body names, and at least half of its distinctive identifiers. Of 44 candidates, 17 passed and are pointers; 27 failed and were restored verbatim. `audits/2026-10/dedupe-2026-10.md` records every entry's origin and decision.
5. **Rules and pins** were decided per entry from each verbatim body, in five passes by area, and then validated mechanically: every pinned file exists and defines the named test, and no placeholder remains. 68 entries carry pins (a Pinned by field that starts with a backticked test path); 112 give the reason they have none.
6. **Frozen snapshot.** `audits/2026-10/audit-2026-10.md` keeps its text (SHA-256 `8f9ea849…c27`, identical to its copy at b1faaa9). Its family moves with it, per the ADR-047 addendum.
7. **Gates.** `tests/unit/test_pitfall_catalogue.py` (16 tests) checks that index rows and entries agree (ID, rule, status, legacy and anchor); that every heading in an area file is an entry heading; that every Status is one of the four forms; that no placeholder remains; that every pin names a real test under `tests/`; that every pointer's home holds its issue numbers and pins; that every archive link resolves; that the redirect table matches the Legacy fields; that every PF citation resolves; that no legacy numbered citation survives outside the archive and the legacy columns; and the size budgets. The budgets are 64 KB per area file and 80 KB for the chapter README (96 KB since the 2026-10-24 addendum below). The area budget is raised from the 48 KB first set, because the UI area holds 22 entries with their full rules and measures 52 KB; the README budget is raised because each index row now carries a full rule (73 KB measured).
8. **Citations.** 117 numbered citations in the files outside the chapter became PF citations. A diary-level citation names every standing rule of its diary, so one citation may name up to three entries. Where a citation relies on a sub-lesson that has no entry of its own, it names the entry and the item of the archived narrative, for example `PF-E3D-07, item 1 of archive/05-l1-3-workspace.md`.

## Consequences

- One place per lesson. A reader scans the index, which carries each entry's rule, status and legacy number, and opens an area file for the body.
- A pointer depends on its home. The gate fails when the home stops naming the issue numbers or pins the entry names; it does not compare prose. Fourteen of the 17 pointers name no test in their body, so for them the issue number is the only anchor, and a long home weakens even that. A reviewer must read the home of each pointer; the gate does not replace that.
- Some standing rules state the headline of a diary. The archived narrative holds the full text, and a sub-lesson without its own entry is cited by item.
- Open points for owner review. Some rules compress several lessons (PF-API-21 covers seven findings; PF-DOM-02, PF-DOM-22, PF-DOM-23 and PF-DOM-24 hold more than one rule each). Some pins are judgements: PF-E3D-06's control test shows that the trap exists, PF-E3D-08's named test covers another item, and PF-PER-13's pin cannot tell a restored layer id from the active-layer fallback. Conftest fixtures count as pins only where the entry names one (PF-TST-07); the other fixture guards are recorded as the fix. PF-E3D-09 has no pin, because its body does not name the removal gate `tests/unit/test_no_qt3d_left.py`. The gate checks that a named file mentions the pinned name, not that the test covers the rule: a review found a pointer whose home mentioned the same function in an unrelated context (PF-API-01), and that entry is now standing with its own text. Method pins are written without their class, and the gate checks that the name is defined in the file.

## Evidence

- Verbatim split: the 181 blocks of §11.4 at b1faaa9 were checked against their destination files before the dedupe. The 27 restored bodies were checked equal to the base text after link re-basing.
- Dedupe: `audits/2026-10/dedupe-2026-10.md` lists all 180 entries with their origin line at b1faaa9, their kind and their decision.
- Gates: `tests/unit/test_pitfall_catalogue.py` (16 tests, passing), with `test_no_qt3d_left`, `test_quick3d_packaging`, `test_dependency_governance` and `test_skill_citations` (89 passing), `scripts/check_skill_citations.py`, `scripts/check_agent_context.py` and `scripts/sync_wiki.py --check` passing.
- Code: no runtime file moved. Of the Python lines changed since b1faaa9, all are comments or docstrings except two fixture path constants, `AUDIT_PLAN` in `tests/integration/test_item_style_in_step.py` and `BENCHMARK_PLAN` in `tests/perf/test_nfr_budgets.py`.

## ADR-061 addendum: the index budget is raised, not met by shortening rules (#588, 2026-10-24)

**Context.** PR #584 brought the §11.4 index to 79,997 of its 80,000-byte budget (measured
newline-normalised, `test_pitfall_catalogue.py::test_size_budgets_hold`) and filed #588: the
next index row in any area would fail the gate. The non-3D hardening package then needed
three new PF rows (PF-CAN-23, PF-CAN-24, PF-CI-13) plus PF-UI-28 and the `04b` area-table
row — 1,665 bytes, taking the index to 81,662. Under that pressure the rules had already
been cut once in PR #584, and a review called that the wrong feedback loop — a byte count
that shapes the wording of a rule makes the rule incomplete.

**Decision.** Of #588's three options (split the index per area, raise the budget with a
stated reason, shorten the index format), this raises the chapter-README budget to 96,000
bytes. The index inherently grows by one row per lesson — a permanent addition, not a leak
— and the budget's job is to force the structural split before the file becomes unwieldy,
not to compress what each lesson says. 96,000 leaves 14,338 bytes, about eight more packages
at the observed 1,665 bytes each, so the next package does not reopen the question. The
area files keep their 64 KB budgets; `04-ui-panels-dialogs.md` (63,440) is the next one to
split. The test's comment says the budget is a maintenance trigger, not a target.

**Consequences.** #588 stays open for the structural decision (a per-area index or a shorter
row format), which this addendum does not make; the raise is the option it lists and buys
the time to take it deliberately. No entry, rule or pin changed to fit.

## ADR-061 addendum: structural split of the pitfall index by area (#588, 2026-10-26)

**Context.** As anticipated in the 2026-10-24 addendum, the central chapter README had
grown to 217 index rows and ~83 KB. Compressing rule wording was rejected as the wrong
feedback loop. The structural decision selected by the owner on 2026-10-24 is executed.

**Decision.**
1. **Central navigation.** The chapter README §11.4 retains its role as the central entry point,
   presenting a concise area navigation table linking to per-area index files and detailed body files,
   plus the legacy numbered redirect table (`11.4.N` -> `PF-*`).
2. **Area indexes.** The 217 full index rows are distributed into 12 dedicated area index files under
   `docs/11-risks-and-technical-debt/pitfalls/index/` (`01-canvas-geometry.md` through `12-process-and-docs.md`).
   Logical areas remain independent of body-file splits (`UI` index covers both `04` and `04b`).
   All 5 columns (`ID`, `Rule`, `Status`, `Where`, `Legacy`) are preserved verbatim with rebased
   relative links (`../01-canvas-geometry.md#pf-can-01`).
3. **Gates & Budgets.** `tests/unit/test_pitfall_catalogue.py` discovers area index files,
   enforcing full coverage in central navigation, exact ID matching, per-area row locality, and link resolution.
   Size budgets are adjusted to reflect the split architecture:
   - Chapter README: `README_MAX_BYTES = 48_000` (measured 26,489 B; ~21 KB headroom)
   - Area indexes: `INDEX_MAX_BYTES = 24_000` (measured 2,141 B – 8,284 B; >=15 KB headroom each)
   - Detailed body files: `PITFALL_MAX_BYTES = 64_000` (unchanged)
4. Closes #588.

## ADR-061 addendum: a second CAN index, forced by the 24 KB budget (#850, 2026-11-19)

**Context.** The 2026-10-26 addendum fixed one index file per logical area and said an
area's body-file splits do not add an index. The CAN area has since filled
`index/01-canvas-geometry.md` to 23,951 bytes against its 24,000-byte budget: the next
canvas lesson (PF-CAN-68, #850) would have pushed it over, and the gate's own message
points at the structural split rather than at compressing a rule.

**Decision.** The CAN area carries **two** index files, split by body file, not by rule:
`index/01-canvas-geometry.md` keeps PF-CAN-01–48 (the body file `01-canvas-geometry.md`)
and `index/01b-canvas-rendering.md` holds PF-CAN-49 onwards (the body file
`01b-canvas-rendering.md`). Both are `CAN` in `AREA_INDEX_MAP`, both are linked from the
§11.4 navigation row, and every row keeps its five columns and its rebased
`../01b-canvas-rendering.md#pf-can-…` link. 19 existing rows were moved byte-identically;
no rule, pin or status changed to fit. This is the remedy for an **index** that reaches
`INDEX_MAX_BYTES`; a **body** file that reaches `PITFALL_MAX_BYTES` is split as the
catalogue already does. The next file in line is a body file, `04-ui-panels-dialogs.md`
(63,544 of 64,000), whose remedy is that body split (`04`/`04b`), not a second index.
