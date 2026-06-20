---
name: finalize-us
description: End-of-user-story procedure — commit, push, PR, merge, version bump, roadmap update, wiki sync, branch cleanup
user_invocable: true
argument: "US number and PR title, e.g. 'US-11.2 Plant spacing circles'"
---

# Finalize User Story

Run the full post-approval wrap-up for a completed user story. This skill assumes the code is already approved and all tests pass. All issues identified and corrected during implementation and manual testing must be documented in the arc42 docs before this step.

## Operating rules

- Do not finalize from `master`; work from the feature branch first.
- Before opening or merging a PR, run an independent PR review in a fresh agent context and address anything actionable.
- Never create git tags manually; GitHub release automation owns tags and versions.
- Wait on CI/releases by a **state transition** — `gh pr checks --watch --fail-fast` for PR checks, and a release-tag change (top `tagName` differs from the one captured before merge) for releases. Never grep `$(date ...)`: local-vs-UTC `createdAt` mismatches and same-day re-runs make date matching unreliable, and a date match cannot detect failure (issue #229).
- Prefer the repo's Windows-safe `gh.exe` path: `"C:\Program Files\GitHub CLI\gh.exe"`.
- Ask for confirmation before any irreversible remote action if the user has not already approved finalization.

## Steps

1. **Verify branch and clean scope**
   ```bash
   git status
   git branch --show-current
   git diff --stat
   ```
   Confirm you are on the intended feature branch and understand exactly what will ship.

2. **Run final local quality checks**
   Use the checks required by `CLAUDE.md` for the touched feature. At minimum, run the relevant tests and lint checks; if UI strings changed, include translation validation.

3. **Run an independent PR review**
   Launch the local `.claude/agents/senior-reviewer.md` agent in a fresh, isolated worktree to review the branch as if it were an external reviewer. The review should look for correctness issues, regressions, missing tests, translation misses, and security concerns. Treat the result as an input to the finalization decision, not as a rubber stamp.

4. **Apply any fixes from review**
   Re-run the affected checks after fixes. If the reviewer found nothing actionable, note that in the PR summary.

5. **Commit** all staged/unstaged changes on the feature branch:
   ```
   git add <changed files>
   git commit -m "feat(US-X.X): <description>"
   ```
   Include `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`.

6. **Push** the feature branch:
   ```
   git push -u origin feature/US-X.X-short-description
   ```

7. **Create PR** via GitHub CLI:
   ```
   "C:\Program Files\GitHub CLI\gh.exe" pr create --title "feat(US-X.X): Title" --body "..."
   ```
   Body must include `## Summary` (bullet points), `## Test plan` (checklist), and the Claude Code footer. Include a short note if an independent PR review was run and whether it produced changes.

8. **Gate on CI, capture the current tag, then merge.**

   First **wait for the PR's checks to pass** — `--fail-fast` exits non-zero on the first failure, so a red CI is surfaced instead of silently waited on. Do not merge if this fails; stop and report the failing check.
   ```bash
   "C:\Program Files\GitHub CLI\gh.exe" pr checks <PR#> --watch --fail-fast
   ```

   Then **capture the latest release tag _before_ merging** (the merge is what triggers `release.yml`), so step 9 can wait on the tag *changing* rather than on a date:
   ```bash
   before_tag=$("C:\Program Files\GitHub CLI\gh.exe" release list --limit 1 --json tagName --jq '.[0].tagName')
   ```

   Then **merge** via GitHub CLI (`--admin` covers branch protection / draft→ready; checks are already green):
   ```bash
   "C:\Program Files\GitHub CLI\gh.exe" pr merge <PR#> --squash --delete-branch --admin
   ```

9. **Wait for the CI release by tag transition** — the CI release workflow (`release.yml`) auto-creates a release + tag on every non-chore push to master. Default is patch bump; for minor/major add the `minor` or `major` label to the PR **before** merging.

   Poll until the top tag differs from `before_tag` (timezone-independent; also correct when two releases land the same day). **Never** match on `$(date ...)` — local-vs-UTC `createdAt` mismatches make date matching unreliable (issue #229).
   ```bash
   new_tag="$before_tag"
   for _ in $(seq 1 40); do          # ~10 min ceiling; the release runs in ~3 min
     new_tag=$("C:\Program Files\GitHub CLI\gh.exe" release list --limit 1 --json tagName --jq '.[0].tagName')
     [ "$new_tag" != "$before_tag" ] && break
     sleep 15
   done
   if [ "$new_tag" = "$before_tag" ]; then
     echo "No new release after merge — check the release workflow before continuing."; exit 1
   fi
   "C:\Program Files\GitHub CLI\gh.exe" release list --limit 1
   ```
   If no new tag appears, **stop and report** — do not run the version bump against the stale tag.

10. **Version bump** — sync source files to the CI-created release:
   ```
   "C:\Program Files\GitHub CLI\gh.exe" release list --limit 1 --json tagName --jq '.[0].tagName'
   ```
   Update `pyproject.toml` and `src/open_garden_planner/__init__.py` to match.

11. **Update roadmap** — mark the user story complete:
   - `CLAUDE.md`: change the Phase progress row to `✅`
   - `../open-garden-planner.wiki/Roadmap.md`: mark the same story complete

12. **Commit version sync + roadmap**:
   ```
   git add pyproject.toml src/open_garden_planner/__init__.py CLAUDE.md
   git commit -m "chore: sync version to vX.Y.Z after US-X.X PR #NNN"
   ```

13. **Push master**:
   ```
   git push origin master
   ```

14. **Push wiki**:
   ```
   cd ../open-garden-planner.wiki
   git add Roadmap.md && git commit -m "Update roadmap: US-X.X complete" && git push
   ```

15. **Cleanup** — delete the local feature branch if it still exists:
   ```
   git branch -d feature/US-X.X-short-description
   ```

16. Return the PR URL and new version to the user.
