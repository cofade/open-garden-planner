---
id: ADR-047
title: "Audit snapshots plus a living debt register (2026-10 repository audit)"
status: "Accepted (2026-10-04). Introduced by the first whole-repository audit (`docs/11-risks-and-technical-debt/audits/2026-10/audit-2026-10.md`); changes how technical debt is recorded, not what the code does."
legacy_anchor: adr-047-audit-snapshots-plus-a-living-debt-register-2026-10-repository-audit
---

# ADR-047: Audit snapshots plus a living debt register (2026-10 repository audit)

**Status**: Accepted (2026-10-04). Introduced by the first whole-repository audit
(`docs/11-risks-and-technical-debt/audits/2026-10/audit-2026-10.md`); changes how technical debt is
recorded, not what the code does.

**Context.** The project records lessons at the incident level with unusual discipline:
§11.4 holds 139 pitfall entries, the failure archaeology 25 sagas, the ADR file 46
decisions with 41 addenda. The *registers* above that level had stopped working. The
debt register §11.3 received its last row on 2026-04-17 while 61 later commits touched
the file; it has a priority column but no status and no link to an issue. §11.1/§11.2
carry rows resolved months ago (Qt3D vs a dedicated engine is "open" although ADR-038
settled it; the SQLite plant cache is still open and nothing says so). §10.6 promises
"mypy type check" and a "coverage report" on every push; CI runs neither, and the first
measurement found 2 104 strict-mode errors in 134 of 248 files and 80.2 % non-UI line
coverage (66.4 % branch) against the written 80 % target. A register that nobody can
read for status is institutional memory only on paper (§11.4 says so itself: it "is
only institutional memory if it is read").

The audit also produced numbers that are worthless as prose and valuable as a time
series: complexity rank distribution (59 of 4 042 functions at rank D or worse), module-level
layering violations (6), lint debt outside `src/` (235 findings), formatter drift (427
files), mutation scores for twelve core modules, the slowest tests, the share of
version-sync commits (122 of 407). A number meant as a trend needs a re-runnable procedure
checked into the repository (external-positioning rule), or the next audit starts from
zero and cannot say whether anything improved; a number that is only a dated measurement
(benchmark timings, mutation scores) has to say so.

**Decision.**

1. **§11.3 is the single living register.** Columns: `ID | Area | Description |
   Severity/Effort | Status | Issue | Source`. Every Top-N finding of an audit snapshot
   gets a row (`TD-009` onward); P0/P1 rows carry their GitHub issue, P2/P3 rows point to
   the audit epic's checklist, and the long tail stays in the snapshot's appendix. `Status`
   is one of `open` (with a measurement or partial-fix note where useful), `fixed (#PR)`,
   `accepted (ADR-0xx)`, `closed (reason)` or `superseded (by …)`, and is updated when
   the issue closes. Historical rows TD-001…TD-008 keep their ids, receive a status, and
   carry an issue only where one exists. Rows are never deleted; a resolved row says so.
2. **Audit reports are dated snapshots** beside the register
   (`docs/11-risks-and-technical-debt/audit-YYYY-MM.md`), written in the house style
   (symptom, measurement, recommendation; numbers over adjectives), with a Top-N ledger
   that cites the register ids and the issues. The snapshot is not edited after merge;
   corrections go to the register and the next snapshot.
3. **One re-runnable baseline.** `scripts/audit_metrics.py` emits the metrics JSON the
   snapshot quotes (`docs/11-risks-and-technical-debt/audit-YYYY-MM-metrics.json`). A
   later run against the same commit reproduces the static numbers exactly (LOC,
   complexity, mypy at the recorded tool version, ruff, layering, git) and coverage to
   about 0.1 percentage point overall (up to 0.3 per package); a run against a newer commit is the trend. A tool that is
   missing or whose output cannot be parsed yields `available: false` with a reason, never
   a zero; a section disabled by flag is `null`. Every other number in a snapshot
   (benchmarks, mutation scores, PoCs) is labelled point-in-time with its harness named.
4. **Deliberate decisions are listed, not ranked.** A finding that contradicts an ADR or
   a documented rule is recorded in the snapshot's "challenged decisions" section with the
   ADR cited and the measurement that motivates the challenge; it enters the register
   only when the owner reopens the decision.

**Rationale.** The alternative, filing issues only, loses the cross-section view (which
dimension is red, what the trend is) and repeats the drift that emptied §11.3. The
alternative of a separate `docs/audit/` tree adds a 13th top-level folder beside the 12
arc42 chapters and detaches the snapshot from the chapter that owns risks and debt.
Ratchets in CI (mypy count must not grow, no new rank-F functions, a coverage floor) are
*proposed* in the snapshot and tracked as issues; adopting them is a separate decision
because each changes what a contributor must do to merge.

**Consequences.** Positive: status is readable in one table; the next audit diffs a JSON
file instead of re-measuring from zero; owners of open debt are the issues, not a
sentence in prose. Negative: three places can drift when an issue closes (the register
row, the issue and the epic checklist); the row carries the issue number so a grep finds
it, and the register rows and the epic checklist are rendered from the same audit ledger
(the snapshot's §9.1).
`scripts/audit_metrics.py` depends on optional tools and on a full git history for churn
(a shallow checkout reports `available: false` there by design). The first audit added
no CI gate beyond the script's own unit test, created no label and changed no code
outside `scripts/audit_metrics.py`; the Windows-only checks (frozen exe, frame pacing at a
real window) were handed to the owner's local run (see the snapshot's handover section).

**Addendum (2026-10-05, PR #413): rows from another decision's evidence.** A row found
outside an audit, in another ADR's evidence (TD-035 to TD-037, ADR-048), links the work
package that carries it instead of the audit checklist, because no audit epic owns it; a
P0/P1 row links its own issue, as decision 1 requires of every P0/P1 row (TD-037: #414).

## ADR-047 addendum: the audit family moves to `audits/2026-10/` (ADR-061)

The eight dated 2026-10 artifacts moved from `docs/11-risks-and-technical-debt/` into
`docs/11-risks-and-technical-debt/audits/2026-10/`, and the reference-plan fixture moved to
`tests/fixtures/plans/`. The snapshot's text is unchanged, and it contains no relative links, so
the move needed no edit to it. Its statement that it was "not edited after merge" is corrected:
commit `07241b9` (#426, 2026-10-10) rewrote its AUD-063 entry and table row (the issue resolved via
ADR-052). That edit is recorded here and in ADR-061. The decision above keeps its original convention for future
snapshots (beside the register); this addendum supersedes it: future snapshots go to
`audits/YYYY-MM/audit-YYYY-MM.md`, with their metrics JSON beside them.

`audit-2026-10-metrics.json` still records the snapshot-date values (2,104 mypy errors in
134 files). TD-020 in §11.3 records the later baseline (1,966 errors).
