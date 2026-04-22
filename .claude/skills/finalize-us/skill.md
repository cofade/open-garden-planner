---
name: finalize-us
description: End-of-user-story procedure — commit, push, PR, merge, version bump, roadmap update, wiki sync, branch cleanup
user_invocable: true
argument: "US number and PR title, e.g. 'US-11.2 Plant spacing circles'"
---

# Finalize User Story

Run the full post-approval wrap-up for a completed user story. This skill assumes the code is already approved and all tests pass.

## Steps

1. **Commit** all staged/unstaged changes on the feature branch:
   ```
   git add <changed files>
   git commit -m "feat(US-X.X): <description>"
   ```
   Include `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`.

2. **Push** the feature branch:
   ```
   git push -u origin feature/US-X.X-short-description
   ```

3. **Create PR** via GitHub CLI:
   ```
   "C:\Program Files\GitHub CLI\gh.exe" pr create --title "feat(US-X.X): Title" --body "..."
   ```
   Body must include `## Summary` (bullet points), `## Test plan` (checklist), and the Claude Code footer.

4. **Merge** via GitHub CLI:
   ```
   "C:\Program Files\GitHub CLI\gh.exe" pr merge <PR#> --squash --delete-branch --admin
   ```

5. **Wait for CI release** — the CI release workflow (`release.yml`) auto-creates a release + tag on every non-chore push to master. Default is patch bump. For minor/major bumps, add the `minor` or `major` label to the PR **before** merging.

   Poll by today's date — NOT by tag prefix (which matches old releases immediately and exits the loop before CI has run):
   ```bash
   until "C:\Program Files\GitHub CLI\gh.exe" release list --limit 1 --json tagName,createdAt \
     --jq '.[0].createdAt' 2>/dev/null | grep -q "$(date +%Y-%m-%d)"; do
     sleep 15
   done
   "C:\Program Files\GitHub CLI\gh.exe" release list --limit 1
   ```
   Usually ~2–3 minutes. If already confirmed (e.g. checked manually), skip polling.

6. **Version bump** — sync source files to the CI-created release:
   ```
   "C:\Program Files\GitHub CLI\gh.exe" release list --limit 1 --json tagName --jq '.[0].tagName'
   ```
   Update `pyproject.toml` (`version = "X.Y.Z"`) and `src/open_garden_planner/__init__.py` (`__version__ = "X.Y.Z"`) to match.

   **CRITICAL: Never create git tags manually. The CI release workflow is the sole owner of tags.**

7. **Update roadmap** — mark US as complete:
   - `CLAUDE.md`: change `|        |` to `| ✅     |` in the progress table
   - `../open-garden-planner.wiki/Roadmap.md`: change `| |` to `| :white_check_mark: |`

8. **Commit version sync + roadmap**:
   ```
   git add pyproject.toml src/open_garden_planner/__init__.py CLAUDE.md
   git commit -m "chore: sync version to vX.Y.Z after US-X.X PR #NNN"
   ```

9. **Push master** (no tags — CI owns tags):
   ```
   git push origin master
   ```

10. **Push wiki**:
    ```
    cd ../open-garden-planner.wiki
    git add Roadmap.md && git commit -m "Update roadmap: US-X.X complete" && git push
    ```

11. **Close linked issue** (if the PR/branch references a GitHub issue number):
    - Post a closing comment on the issue via `mcp__github__add_issue_comment` summarising root cause and changes shipped.
    - Close it via `mcp__github__issue_write` with `state: closed, state_reason: completed`.
    - Skip this step if there is no linked issue.

12. **Move issue to "Closed" on the project board** (only if a linked issue exists):
    Project: `PVT_kwHOAyyXvs4BU2fi` (number 1), Status field: `PVTSSF_lAHOAyyXvs4BU2fizhFw3mk`, Closed option: `98236657`.
    ```bash
    # 1. Find the project item ID for the issue
    ITEM_ID=$("C:\Program Files\GitHub CLI\gh.exe" api graphql -f query='
    { user(login:"cofade") { projectV2(number:1) { items(first:100) { nodes {
      id content { ... on Issue { number } }
    } } } } }' \
    --jq ".data.user.projectV2.items.nodes[] | select(.content.number == ISSUE_NUMBER) | .id")

    # 2. Set status to Closed
    "C:\Program Files\GitHub CLI\gh.exe" api graphql -f query="
    mutation { updateProjectV2ItemFieldValue(input: {
      projectId: \"PVT_kwHOAyyXvs4BU2fi\"
      itemId: \"$ITEM_ID\"
      fieldId: \"PVTSSF_lAHOAyyXvs4BU2fizhFw3mk\"
      value: { singleSelectOptionId: \"98236657\" }
    }) { projectV2Item { id } } }"
    ```
    Skip if no linked issue, or if the item is not found in the project.

13. **Cleanup** — delete local feature branch if it still exists:
    ```
    git branch -d feature/US-X.X-short-description
    ```

14. Return the PR URL and new version to the user.
