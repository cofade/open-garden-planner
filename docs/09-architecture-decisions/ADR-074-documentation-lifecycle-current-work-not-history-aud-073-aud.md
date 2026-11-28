---
id: ADR-074
title: "Documentation lifecycle — current work, not history (AUD-073, AUD-077)"
status: "Accepted (documentation restructure, 2026-11-07)"
legacy_anchor: adr-074-documentation-lifecycle--current-work-not-history-aud-073-aud-077
---

# ADR-074: Documentation lifecycle — current work, not history (AUD-073, AUD-077)

**Status**: Accepted (documentation restructure, 2026-11-07)

**Context**: `docs/roadmap.md` grew to 4,205 lines and `AGENTS.md` spent roughly a
quarter of its budget on release-by-release narratives. The audit had already recorded
the cause: most roadmap content was shipped history (AUD-073), and the root
instructions repeated shipped narrative already maintained in the roadmap and ADRs
(AUD-077). The writing guide required dense acceptance highlights and a "Docs updated
on completion" table for every delivered US/package, the release ritual appended a new
pickup bullet, and the only enforced limit was a distant byte ceiling on the root file.
Nothing removed or retired the previous release's detail, so every release added and
nothing subtracted.

**Decision**:

1. **Root files are a rulebook and a current handoff.** `AGENTS.md` and `CLAUDE.md`
   contain always-on commands, gates, invariants, the current release and the next
   work. They do not contain release narratives, per-issue implementation stories, or
   facts already owned by an ADR, FR, §8 section or issue.
2. **The roadmap is current work plus a compact completed index.** While a US is open,
   it carries its description and acceptance criteria. On completion, the detail is
   deleted and replaced by one row (ID, one-line scope, version/PR, ADR/FR link). A
   completed section is a status table, not a narrative.
3. **Durable facts have one home.** Decisions live in ADRs, capability in
   `docs/functional-requirements/README.md`, lessons in the pitfall catalogue and skills, and
   delivery evidence in the GitHub release and issue. Git history is the archive; no
   repository history files are created.
4. **Release close includes a documentation prune.** `finalize-us` replaces the handoff,
   deletes the released package's detail from the roadmap, keeps the one-line row, and
   updates the wiki's current status. This is a release step, not a later cleanup.
5. **The senior reviewer checks documentation waste.** Root/roadmap additions that
   repeat shipped history, restate an ADR/FR, or explain what the code does are findings
   (P1 when they hide the next action, P2 otherwise). No new size gate is added; the
   existing 28/32 KiB root budget remains the only hard backstop.

**Alternatives considered**:

- *Create a roadmap archive and move the history there.* Rejected: the code, tests,
  ADRs, FRs, GitHub releases and issues already hold the evidence; an archive preserves
  the same content type and repeats the pressure-valve cycle.
- *Add a hard roadmap size test.* Rejected as the primary control: a size gate does not
  change the content model and can be satisfied by compressing rather than retiring.
  The reviewer check and release-close step are the content controls.
- *Collapse completed sections in `<details>` blocks.* Rejected: the file is still
  loaded and searched in full, and the history still competes with current work.

**Consequences**: `docs/roadmap.md` drops from 4,205 lines to about 380; the root handoff
drops from 72 lines to about 30; the two pickup archive files and the spent
`docs/implementation-plan-457.md` are deleted; the wiki Home, Roadmap and Architecture
pages lose their release changelogs; the roadmap's Overview, Dev Infrastructure and Phase
17 headings remain because `scripts/sync_wiki.py` includes them. The stale 2026-03
"Outlook: Additional 2D Features" list was retired: shipped candidates are in the
delivery index, and the issue tracker remains the work list. This supersedes ADR-068's
alternative "Deleting historical skills/pickups … rejected" for the two pickup files
only; historical skills remain. `ogp-docs-and-writing`, `deliver-package`, `finalize-us`,
`ogp-change-control`, the senior-reviewer definitions and the PR template carry the rule.
The existing `scripts/check_agent_context.py` budget and parity check remain unchanged.

Cross-refs: AUD-073, AUD-077, AUD-078 in
`docs/11-risks-and-technical-debt/audits/2026-10/audit-2026-10-reconciliation.md`;
ADR-051 (wiki publication), ADR-068 (agent context), `AGENTS.md` "Where to Pick Up After
Restart", `docs/wiki/README.md`.
