---
name: finalize-us
description: End-of-user-story procedure - commit, push, reviewed PR, protected merge, release, automatic version-sync PR, wiki sync, branch cleanup
user_invocable: true
argument: "US number and PR title, e.g. 'US-11.2 Plant spacing circles'"
---

# Finalize User Story

Complete the entire owner-approved delivery in one invocation. Preserve the manual-test
approval requirement for the feature. That approval also covers its mechanical version-sync
PR and wiki push; do not ask for a second confirmation for either. Never create a tag.

## 1. Establish the state

Read `git status`, the current branch, the intended PR, its head SHA and its base. Preserve
unrelated edits. Work on the feature branch. If a PR already exists, reuse it. If it is already
merged, resume at the release/version-sync stage using its merge SHA; do not open another PR.
For an already completed version sync, verify source versions and the lock, then finish only
outstanding wiki/cleanup work. A squash title beginning `chore:` or `chore(` creates no release:
wait for its CI, merge normally, and finish without a release wait or a version-sync PR.

Use the Windows-safe GitHub CLI path `C:/Program Files/GitHub CLI/gh.exe` on this machine.
Commands below use `gh` for readability. The issue tracker is the work list.

## 2. Review and create/reuse the feature draft

Run the full checks required by `AGENTS.md`, including both frozen-exe checks. If strings
changed, update and compile translations first. Run senior-reviewer in a fresh worktree
against the branch diff; address P0/P1 findings and repeat review after fixes. For visible 3D
changes, ogp-3d-reviewer comes first. Record all findings in the project documentation.

Commit with the existing configured identity, push the feature branch, and create a DRAFT
PR if none exists (`gh pr create --draft`). Use an actual body file; include summary, test
plan, owner checklist, review results and issue-closing references. Keep the base `master`.
Never mark the feature ready until the owner's manual-test approval is established.

## 3. Gate the current head and merge without a bypass

Fetch master. If the branch is behind, rebase it onto current master, resolve conflicts,
rerun affected checks and the review after fixes, then push with the appropriate lease.
Wait for CI using `gh pr checks N --watch --fail-fast`. Capture the head with
`gh pr view N --json headRefOid --jq .headRefOid`, then verify actual results:

```text
python scripts/check_pr_checks.py --pr N --head VERIFIED_HEAD
```

This verifies check presence as well as success: no checks is never green. It also refuses a
changed head and any failed non-required CI job. If the head changes, repeat verification.
Apply minor/major labels before merge when warranted. Capture the current latest tag with
`gh release list --limit 1 --json tagName --jq '.[0].tagName'` before merging.

On the #399 rollout, after the new checks pass and the owner approves finalization, read the
current protection, compare unrelated fields with the committed payload, and preserve them
if they have changed. Apply the reviewed payload with `gh api --method PUT
repos/cofade/open-garden-planner/branches/master/protection --input quality/master-protection.json`.
Read it back with `python scripts/check_branch_protection.py`. Do not merge while this gate is
unmet. Validate normal refusal/acceptance on a temporary protected validation base, never by
trying to merge a deliberately broken commit into master. Clean up the validation PR/branch.

```text
gh pr ready N
gh pr merge N --squash --delete-branch --match-head-commit VERIFIED_HEAD
```

Never bypass protection. A failing check, conflict or changed head is an actionable finding,
not permission to override it. Zero required approving reviews preserves the solo-maintainer
workflow. Review requirements can be added separately when contributors join.

## 4. Wait for the correct release

Read the feature PR's merge SHA. Poll Release workflow runs for that SHA and the latest
release tag, using bounded waits of at most 30 seconds between progress updates. Stop on
workflow failure; report the failing job. Wait for the latest tag to change from the captured
value, resolve that tag's commit and require it to equal the feature merge SHA. Wait for the
matching Release run to finish successfully (including provenance). Never match dates or
accept an unrelated concurrent release. If the expected release does not appear within
30 minutes, report the workflow state instead of syncing to a stale version. Resume this
stage on a later invocation if necessary.

## 5. Prepare and deliver the automatic version-sync PR

Fetch master and use `chore/sync-vX.Y.Z-pr-N`. Reuse that branch/PR if present. Inspect existing
changes before touching them. Run the preparation helper in dry-run mode first:

```text
python scripts/prepare_version_sync.py --tag vX.Y.Z --source-pr N
python scripts/prepare_version_sync.py --tag vX.Y.Z --source-pr N --apply
```

The helper updates both version declarations, refreshes uv.lock offline and regenerates
pylock.toml. It refuses changed third-party package records and restores source files if
applying fails. If it reports already_synced, verify the lock and skip the duplicate commit.
Update both root instruction files and the canonical roadmap if completion status changed;
prepare the wiki mirror as well. Keep all added text English and context pairs synchronized.

Run lock/export consistency, context parity, skill citations, relevant version/gate tests and
lint. Run an independent senior review of this chore branch in a fresh worktree. Address
P0/P1 and repeat review after fixes. Commit using the helper's exact `chore:` description.
Push, create a draft chore PR with base master, or reuse the existing one. Its body references
the feature PR and release; do not duplicate the feature's issue-closing references.

Wait for all CI, verify current-head check results, mark the chore ready and merge using the
same commands from section 3 and its verified head. These steps are already authorized by
the original finalize-us instruction: do not request another manual-test approval. Its
chore squash message must skip Release. Verify that no additional release was created and
that master has both synchronized versions and a current lock.

## 6. Wiki and cleanup

Push the prepared `../open-garden-planner.wiki/Roadmap.md` change using its repository's
configured identity. Preserve unrelated wiki edits. If the sibling is unavailable, report
wiki sync pending rather than silently claiming success. Return to current master and delete
only the local feature/chore branches that were successfully merged. Report the feature PR,
version-sync PR, published version, CI/release results and any remaining work.
