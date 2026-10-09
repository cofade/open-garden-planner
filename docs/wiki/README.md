# Wiki maintenance and publication

The six `.md` source pages in this directory own the GitHub wiki content.
This README is a maintenance guide. It is not a published wiki page.
The canonical roadmap remains `docs/roadmap.md`. Issues remain the current work list.
See ADR-051 in the architecture decision register.

## Source ownership

| Published page | Authoritative information |
|---|---|
| Home | Canonical roadmap and latest GitHub release. |
| Roadmap | Canonical overview, infrastructure table, and Phase 17 section. Other sections are short summaries with links. |
| Installation | README, release artifacts, installer settings, and deployment documentation. |
| Contributing | Root CONTRIBUTING.md. |
| Architecture | arc42 building blocks, runtime documentation, and ADRs. |
| _Sidebar | Existing page names and repository policy files. |

All source text is UTF-8. Use literal punctuation and check marks.
Do not use PowerShell `Set-Content -Encoding UTF8` or insert literal Unicode escape sequences into prose.

Roadmap.md contains exactly three fixed inclusion markers:

```text
<!-- ogp:include roadmap-overview -->
<!-- ogp:include roadmap-infrastructure -->
<!-- ogp:include roadmap-phase-17 -->
```

The first two include the corresponding canonical tables without rewriting them.
The third includes the complete canonical Phase 17 section.
Unknown, missing, duplicate, or malformed markers fail validation.

## Check and prepare a review

Run the offline check from the main repository:

```text
.venv/Scripts/python.exe scripts/sync_wiki.py --check
```

The check reads all six templates and the canonical roadmap.
It checks strict UTF-8, known text corruption, inclusion markers, wiki page links,
and links to files on this repository's master branch using local paths.
It also checks heading fragments for linked Markdown files.
External services and release links require manual review. No network request occurs.
CI runs this check in the existing Lint job. It never needs a wiki checkout or write credential.

Render pages into a review directory outside the source repository:

```powershell
$wikiPreview = Join-Path $env:TEMP 'ogp-wiki-review'
.venv/Scripts/python.exe scripts/sync_wiki.py --output $wikiPreview
```

The tool writes only the six named pages. It preserves other files in the output directory.
It does not copy this guide, commit, push, delete pages, or access GitHub.
The output directory must be outside the main repository.
Do not point it at the live wiki checkout during PR preparation.

Inspect all rendered pages and the sidebar. Check headings, tables, code fences, navigation,
capability claims, reporting routes, and the generated roadmap sections.
Open the main repository's draft PR with the review checklist and any unmet gates.

## Publish after owner approval and protected merge

1. Use the approved, merged main repository sources. Confirm the main checkout contains the merged commit.
2. Check `git status` in the existing sibling wiki checkout. Preserve unrelated edits and reconcile pending changes before publication.
3. Fetch the wiki remote. Compare the local and remote heads. Fast-forward the clean checkout if necessary.
4. Read wiki changes since the previous publication. Reconcile direct edits to managed pages into the repository sources through review.
5. Render again from the approved main checkout into the preview directory.
6. Compare the preview with the existing wiki. Review every proposed change before copying files.
7. Copy only the six managed pages. Do not remove unrelated wiki pages or edit the wiki's Git settings.
8. Inspect the wiki diff, then commit with its configured identity. Record the source commit SHA in the commit message.
9. Push normally. If the remote advances, reconcile it. Never force-push to resolve a publication conflict.
10. Check the published pages and run the comparison below. Record both repository commit SHAs in the handoff.

Compare a checkout without changing it:

```text
.venv/Scripts/python.exe scripts/sync_wiki.py --check-published --wiki-dir ../open-garden-planner.wiki
```

Exit 0 means all six pages agree. Exit 1 means pages are missing or differ.
Exit 2 means input, validation, or filesystem failure.
Line endings are normalized when reading. Text and Unicode content must otherwise agree.
An unavailable wiki checkout is an error, not a successful or skipped comparison.
Report publication pending if the checkout is unavailable. Do not silently clone or claim publication.

For the initial #417 publication, the audited wiki head was
`6279a789e8d266b3391e3fb9e7f29fe966625050` on 9 October 2026.
Read and reconcile any newer wiki commits before replacing the managed pages.
Reference #417 from the source PR. Close it only after the published wiki satisfies its acceptance criteria.

## Maintenance checklist

- A release or package completion can affect Home, Roadmap, and README claims.
- A setup, installer, dependency, or verification change can affect Installation and CONTRIBUTING.md.
- A module or renderer change can affect Architecture.
- A review-policy change can affect CONTRIBUTING.md, the PR template, and agent skills.
- A reporting or accessibility change can affect community files, Home, Contributing, and the sidebar.
- Update sources in the same reviewed PR as the related change where possible.
- Run the offline check before delivery. Publish after approval and merge.
- Keep the community profile, reporting controls, and template detection checks separate from source validation.

## Initial audit findings

Issue #417's Phase 13 and check-mark defects were already corrected by the audit.
Phase 16 had content. Phase 17 still lacked a detail section, and the overview differed.
Home's release status was stale. Installation omitted attestations and used an outdated build recipe.
Contributing duplicated old commands. Architecture omitted major shipped subsystems.
The old Roadmap also contained a literal Unicode escape and misplaced completion notes.
All existing wiki page links and repository document targets resolved.

The GitHub community profile reported 57% before this change.
Contribution, conduct, security, and PR-template files were absent. Accessibility guidance was also absent.
Private vulnerability reporting was disabled. The implementation enabled it and read back `enabled: true`.
Community profile recognition and the final published wiki remain post-merge checks.
