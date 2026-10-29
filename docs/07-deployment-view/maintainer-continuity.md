# Maintainer ownership and recovery (audit A13)

As checked on 28 October 2026, `cofade` is the repository owner and the only
maintainer whose ownership is declared here. `.github/CODEOWNERS` routes review
to that account; it neither grants permissions nor appoints another maintainer.
The single-maintainer risk remains. No continuity arrangement has been verified.

Security-policy ownership follows the same account. A read-only GitHub API check
of `repos/cofade/open-garden-planner/private-vulnerability-reporting` returned
`enabled: true`. Recheck it after an ownership change; `SECURITY.md` owns the
reporting route. Dependency update review belongs to A2 and its deployment runbook.

## Identity evidence

The commit API links both `cb4a71db8649cc4e48f85f0bef671bb0ac58dd16` and
`003c4bc4c1fba470a8159ce9078a2d3086bd66e4` to `cofade`. They establish the
two addresses reconciled by `.mailmap`; names sharing those addresses are mapped
to the public GitHub no-reply identity. Commit
`d5726dbf8b9d604265b69e8f4be6c49ee822c015` has no linked GitHub author.
Its similarly named professional identity is deliberately left separate.
Other contributors and automation identities are unchanged. Reproduce attribution
with `git shortlog -sne master` and inspect an individual commit with
`gh api repos/cofade/open-garden-planner/commits/<sha>`.

## Owner-only continuity actions

The owner must choose whether to nominate a backup maintainer, agree the role
with that person, and grant the minimum repository permissions explicitly.
No candidate or consent is inferred from contribution counts. Document the
arrangement after both people agree; an unfilled role stays an acknowledged risk.

The owner should retain recovery codes and credential recovery material in
their own secure storage, outside the repository, and verify account recovery
and release-environment access. Never put credentials or recovery codes into
an issue, commit, PR, agent context or this document. Agents cannot verify the
existence of that private material. These actions are not claimed complete.

## Recovery procedure for an authorized maintainer

1. Recover account/repository access through GitHub's account-recovery process.
   Confirm current collaborators and permissions; do not bypass protection.
2. Read the deployment view, ADR-044/050/051 and `finalize-us`. Inspect the latest
   successful Release run and release tag; releases remain the version authority.
3. Prepare the locked build environment from `CONTRIBUTING.md`. Run all gates,
   both frozen checks and read-only protection validation. An unverified build
   is not a recovered release.
4. Restore/recreate missing environment credentials only with owner authorization.
   Check private vulnerability reporting and the policy owner without sending a
   test report or exposing a real report.
5. Ship through a reviewed draft PR, owner manual acceptance and protected merge.
   CI owns tags and release publication. Never manufacture a manual fallback tag.
   Publish wiki sources only after approval and merge.

Revisit the residual risk when the owner nominates a backup, access changes,
or recovery is exercised. This document provides a runnable handover; it does
not assert that a second maintainer or private recovery arrangement exists.
