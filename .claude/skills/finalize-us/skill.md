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
   Launch the local `.claude/agents/pr-reviewer.md` agent in a fresh, isolated worktree to review the branch as if it were an external reviewer. The review should look for correctness issues, regressions, missing tests, translation misses, and security concerns. Treat the result as an input to the finalization decision, not as a rubber stamp.

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

8. **Merge** via GitHub CLI:
   ```
   "C:\Program Files\GitHub CLI\gh.exe" pr merge <PR#> --squash --delete-branch --admin
   ```

9. **Wait for CI release** — the CI release workflow (`release.yml`) auto-creates a release + tag on every non-chore push to master. Default is patch bump. For minor/major bumps, add the `minor` or `major` label to the PR before merging.

   Poll by today's date — not by tag prefix:
   ```bash
   until "C:\Program Files\GitHub CLI\gh.exe" release list --limit 1 --json tagName,createdAt \
     --jq '.[0].createdAt' 2>/dev/null | grep -q "$(date +%Y-%m-%d)"; do
     sleep 15
   done
   "C:\Program Files\GitHub CLI\gh.exe" release list --limit 1
   ```

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
