---
id: ADR-051
title: "Repository-owned wiki sources and manual publication"
status: "Accepted (9 October 2026). Publication requires owner approval and protected merge."
refs: ["#417"]
legacy_anchor: adr-051-repository-owned-wiki-sources-and-manual-publication-issue-417
---

# ADR-051: Repository-owned wiki sources and manual publication

**Status**: Accepted (9 October 2026). Publication requires owner approval and protected merge.

**Context**: The separate wiki accumulated stale status, setup, architecture, and reporting information.
Roadmap-only release edits did not maintain the other pages. The community profile also lacked
contribution, conduct, security, and PR-template files. The owner requires no public email address.

**Decision**:
1. **Review wiki sources with repository changes.** Six templates live in `docs/wiki/`.
   The canonical roadmap remains the source of phase and infrastructure status.
   Fixed markers include its overview table, infrastructure table, and complete Phase 17 section.
2. **Validate offline and publish manually.** The standard-library `scripts/sync_wiki.py` validates
   text and local links, renders into an external directory, and compares an existing checkout.
   It performs no network or Git operations. The existing Lint CI job checks sources only.
   Publication follows owner approval and merge. Reconcile direct wiki edits before copying named pages.
3. **Keep policies in GitHub-supported repository files.** CONTRIBUTING.md owns contribution
   instructions. Wiki pages link to policies rather than duplicate them. The PR template records
   evidence and allows explained non-applicable checks.
4. **Separate report destinations.** Private vulnerability reports use GitHub's security form
   and reach repository maintainers. Private abuse reports use GitHub Support's reporting tools.
   No private maintainer inbox or private Discussion category is promised. No contact email is published.
5. **State verified limits.** Security fixes target the latest stable release without a fixed
   response deadline. Accessibility guidance states known pointer/keyboard barriers and unverified
   screen-reader compatibility. Installer sizes are dated measurements, not invented minimum requirements.

**Alternatives considered**:
- Continuing manual edits in the wiki alone leaves sources outside the repository review process.
- Copying the complete roadmap creates an unnecessarily long wiki and duplicates requirements.
- Automatic publication from CI needs write credentials and can overwrite independent wiki edits.
- A public contact email conflicts with the owner's preference. Public Discussions cannot supply a private channel.
- A standard conduct template with an unfilled private contact field would promise a reporting route that does not exist.

**Consequences**: There is no application, dependency, or `.ogp` format change.
The six existing wiki page names remain stable. Only those pages are managed by the rendering tool.
Check modes are read-only. Output validates all sources before writing, rejects source-repository
destinations, and preserves unrelated files. Missing wiki checkouts fail visibly.
Exit 0 means success, exit 1 means published drift, and exit 2 means invalid input or filesystem failure.
Windows console streams use UTF-8 so a Unicode diff can be captured correctly.

**Validation**: `tests/integration/test_wiki_publication.py` drives the real CLI with temporary
repositories. It covers source-table changes, deterministic Unicode output, missing sections,
invalid markers, broken links, read-only comparisons, missing pages, and unsafe output destinations.
Agent context parity and skill citations remain required. Initial live wiki and community-profile
checks occur after approved publication; source checks cannot prove GitHub recognition.
