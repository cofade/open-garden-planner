

# OGP Failure Archaeology

Repo state when written: v1.23.0, 2026-07-03, default branch `master`, history is
squash-merged PRs. Sources: the pitfall entries in `docs/11-risks-and-technical-debt/pitfalls/` (their index is
§11.4 of the chapter README; the narratives are in `archive/`; the richest), `CLAUDE.md` progress tables, `.claude/skills/debug-verbose/SKILL.md` case
studies, `docs/roadmap.md`, `docs/09-architecture-decisions/README.md`, `git log`.
Every "pinned by" test file was verified to exist on disk on 2026-07-03.

Entry format: **Symptom → wrong theories/dead ends → root cause → evidence → fix →
status → pinned by**. Not every entry needs every field; short incidents are compressed.

---

