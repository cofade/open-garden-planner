---
name: analyze-pr
description: Analyze a GitHub PR for the open-garden-planner repo — fetch metadata + linked issues, check out the branch, run every test layer the agent can run locally (pytest unit/integration/ui, ruff, bandit, i18n gate, PyInstaller exe smoke), then produce a copy-paste-ready manual-test plan for whatever's left. Invoke with a PR number ("analyze-pr 191"), with no argument (auto-pick if exactly one open PR), or on the current branch ("analyze-pr current").
user_invocable: true
---

# analyze-pr

Single purpose: take an open-garden-planner PR, validate everything an agent can validate, and hand the user a short list of _only_ the things they still have to do by hand. Stay terse — the user runs this often.

---

## Phase 1 — Resolve the target PR

Argument handling:

- `analyze-pr <N>` → use PR #N.
- `analyze-pr current` → resolve from the current branch: `gh pr view --json number,title,headRefName,baseRefName,body,url,state,mergeable,mergeStateStatus,statusCheckRollup,author,labels`. If no PR exists for the branch, stop and say so.
- `analyze-pr` (no arg) → `gh pr list --state open --json number,title,headRefName --limit 20`. If exactly **one** is open, use it. If more than one, list them and use `AskUserQuestion` to ask which.

Once the PR number is known, fetch the full payload once and reuse it:

```powershell
& "C:\Program Files\GitHub CLI\gh.exe" pr view <N> --json number,title,body,headRefName,baseRefName,state,mergeable,mergeStateStatus,additions,deletions,changedFiles,statusCheckRollup,labels,author,url,closingIssuesReferences
```

Extract issue refs two ways and union them:

1. `closingIssuesReferences[].number` from the payload above (these are the explicit GitHub-tracked links).
2. Regex over title + body — match `(?i)(closes?|closed|fix(es|ed)?|resolves?)\s+#(\d+)` (the same regex GitHub uses for auto-linking).

For each unique issue number, fetch it:

```powershell
& "C:\Program Files\GitHub CLI\gh.exe" issue view <M> --json title,body,state,labels,url
```

If the PR closes no GitHub issues but references roadmap items (e.g. "US-X.X" or "Package B"), find the corresponding section in `docs/roadmap.md` so the acceptance criteria feed into Phase 4.

---

## Phase 2 — Get onto the branch (only if safe)

```powershell
git status --porcelain
```

If non-empty, **stop and ask the user** before switching — they may have in-progress work. Do not stash, do not discard.

Otherwise:

```powershell
& "C:\Program Files\GitHub CLI\gh.exe" pr checkout <N>
git log --oneline (git merge-base HEAD master)..HEAD
git diff --stat (git merge-base HEAD master)..HEAD
```

The diff stat tells you which areas were touched. Use it for the "Risk surface" line in the final report, and to spot risky territory (file format, exporters, installer, persistence, translations, security-adjacent).

> Base branch is `master`, not `main`.

---

## Phase 3 — Run every test layer the agent can run

Commands come from `CLAUDE.md` Quick Reference. Run the four fast layers in parallel as **background** tasks (`run_in_background: true`), then the PyInstaller smoke test once they finish:

```powershell
venv/Scripts/python.exe -m pytest tests/unit/ tests/integration/ tests/ui/ -q
venv/Scripts/python.exe -m ruff check src/
venv/Scripts/python.exe -m bandit -r src/ --severity-level high
venv/Scripts/python.exe -m pytest tests/unit/test_i18n.py -v
```

```powershell
venv/Scripts/python.exe -m PyInstaller installer/ogp.spec --noconfirm
timeout 8 dist/OpenGardenPlanner/OpenGardenPlanner.exe   # exit 124 = success
```

| Layer | Command | Coverage | Skip if… |
|---|---|---|---|
| pytest (unit + integration + ui) | `pytest tests/unit/ tests/integration/ tests/ui/ -q` | All Python correctness incl. Qt UI tests via pytest-qt | Never. Always run — this is the project's only test surface. |
| Ruff | `ruff check src/` | Lint, style, common bugs | Never. ~1 s. |
| Bandit | `bandit -r src/ --severity-level high` | High-severity SAST | Never. ~10 s. CLAUDE.md § 8.11. |
| Translation gate | `pytest tests/unit/test_i18n.py -v` | `test_german_ts_has_no_unfinished` catches missed `.qm` compiles; `test_no_hardcoded_english_in_src` catches `tr()`-less English strings | Never. Redundant with the full pytest run but explicit — call it out separately in the report if UI strings were added. |
| PyInstaller exe smoke | `pyinstaller installer/ogp.spec --noconfirm` then `timeout 8 dist/OpenGardenPlanner/OpenGardenPlanner.exe` (exit 124 = clean launch) | Verifies the bundled `.exe` launches without import errors. **Mandatory before every merge** per CLAUDE.md Quick Reference. | If the diff is docs-only AND touches nothing under `src/`, `installer/`, `pyproject.toml`, `requirements*.txt`. |
| Senior-reviewer agent | `subagent_type: senior-reviewer` against the branch diff | P0/P1/P2 findings on architecture, regressions, missed tests | This skill does **not** launch it (it's heavier; the user runs it explicitly via `finalize-us`). Flag in the report if the PR body shows no evidence of a senior-review pass for a feature-sized change. |

Also pull the GitHub CI rollup from the PR view — `statusCheckRollup[].conclusion` (Lint / Test / Security). If CI is green and the local layers above are green, the PR's automated story is complete.

> **Time budget**: full pytest can take a few minutes (≈2700 tests on this project). Launch all four fast layers `run_in_background: true` and continue with the rest of the analysis; do not poll — the harness re-invokes when each finishes.

For each layer, report:

- the command that ran
- the **last 10–20 lines** of output (so failures stay visible)
- a one-word verdict: ✅ / ❌ / ⚠️

If anything fails, **surface it at the top of the final report** and stop — do not propose fixes speculatively.

---

## Phase 4 — Hand the user the manual-only list

Open the PR description and find every checkbox under "Test plan", "Manual", or "Reviewer to verify manually". Anything **unchecked** is a candidate for manual work; cross-reference against what the automated layers above just covered. What remains is the manual list.

OGP is a desktop PyQt6 app — most manual steps are **UI interactions in the running app**, not CLI. Format each item as `keyboard / menu path → expected visual result`. Where appropriate, prefix with the launch command:

```powershell
venv/Scripts/python.exe -m open_garden_planner
```

Build the list from three sources:

### 4a. Unchecked items from the PR body's "Test plan"

Carry the wording over verbatim — the author already chose words that make sense to them.

### 4b. Per-US / per-feature acceptance walkthroughs

For each user story / feature listed in the PR body, derive a tight walkthrough from the **acceptance criteria** in `docs/roadmap.md` (or `docs/functional-requirements.md` for FR-* entries). Include:

- the **shortcut / menu path** to trigger the feature
- the **golden path** (do X → see Y)
- at least one **edge case** (empty input, degenerate geometry, undo, save/reload roundtrip)

### 4c. Risk-surface tests the diff implies but the PR body forgot

Look at the diff and add manual items for anything the author may have missed:

| If the diff touches… | Add a manual check for… |
|---|---|
| `FILE_VERSION` / `.ogp` schema | Open an older-format file → save → reopen on **the previously-released `.exe`** (forward/back compat). v1.4 binary opening a v1.3 file must just-work; old binary opening a newer file must show a clear error, not silently drop data. |
| Exporter (PNG / SVG / PDF / DXF) | Export a real project, open the file in an external viewer (no internal-only test). |
| Installer / `installer/ogp.spec` | Launch the built `.exe` (not the dev `python -m …`), open a project, perform one drawing op. |
| Translations (`.ts` / `.qm` / `scripts/fill_translations.py`) | Switch language in Settings → confirm new strings show in German with no English fallback. Hardcoded f-strings bypass `tr()` and only show up here. |
| Persistence (`.ogp` JSON schema) | Save → close app → reopen → verify everything round-trips (item types, properties, paper layouts, snap toggles). |
| Drag/drop, snap providers, tools | Try the tool with each relevant snap mode toggled on/off, combined with the keyboard shortcuts. Status-bar coordinate input (`@dx,dy`, `@dist<angle`) where applicable. |
| Paper Space / print / Layout | Open Layout tab (Ctrl+4) → resize viewport → change scale → save → reopen → verify scale bar updates. Also drag rapidly on the Garden Plan tab and confirm the viewport debounces (no flicker storm). |
| Plant / soil data | Drop the plant onto a bed → confirm auto-populated species data + soil compatibility warning fires. Reparent to a different bed → warning refreshes. |
| Google Maps satellite picker | API key in `.env` (`OGP_GOOGLE_MAPS_KEY`). Drag a rectangle → confirm scale is analytical, not visual; reopen project → background persists. |

### 4d. Final manual checklist — output format

A single numbered list, grouped by US / feature, every item phrased as **"do X → expect Y"**. Example:

```
US-B1 Bezier pen tool
  1. Press `B` → cursor changes to Bezier pen → click 4 anchors → smooth curve through them
  2. Drag handle on anchor 2 → curve updates live
  3. Save → close app → reopen → curve identical, handle still editable
  4. Undo (Ctrl+Z) until empty → no orphan items in scene
```

Keep each item one line where possible. Never write "verify it works" — the test must be falsifiable.

---

## Phase 5 — Output a tight report

Structure (markdown, keep it under one screen):

1. **PR summary** — title, branch, additions/deletions, mergeable status, CI rollup (X/Y green), labels.
2. **Connected tickets** — `#N — title (state)`, one line each. If none, say so explicitly and list any roadmap items the PR closes.
3. **Scope** — one-sentence "what this PR does", plus the diff stat by area (`src/core/snap/`, `ui/paper_space/`, `tests/`, `docs/`).
4. **Local validation** — table: layer → result → tail of output. Mark CI-only layers as "CI green (not re-run locally)" where applicable.
5. **Manual tests remaining** — numbered list from Phase 4 (groupings + falsifiable steps).
6. **CLAUDE.md gate reminders** — only mention if the PR description does not already show evidence:
   - Senior-reviewer pass (`subagent_type: senior-reviewer` against the branch in a fresh worktree)
   - arc42 doc updates per `CLAUDE.md` "Contributing to Documentation" table
   - ADR for new dependencies / pattern choices
   - Wiki sync for completed user stories (`../open-garden-planner.wiki/Roadmap.md`)
7. **Verdict** — one sentence: "ready for manual QA" / "blocked on automated failure: …" / "needs senior-review pass before merge".

Do **not** narrate intermediate steps in the final output. The user wants results.

---

## Phase 6 — Stay on the branch, do not push, do not amend

This skill is read-only on git state past `gh pr checkout`. Do not commit, push, rebase, version-bump, or update docs unless the user asks. If automated tests fail, report the failure verbatim and stop — don't try to fix it speculatively. Do not auto-launch the senior-reviewer or `finalize-us` skills; those are separate workflows the user starts when they're ready.

---

## PowerShell reminders that bite the user

- No `&&` chaining → `;` or `if ($?) { ... }`.
- No `2>&1` on native exes — stderr is already captured; wrapping it in PowerShell makes `$?` lie.
- No angle-bracket placeholders (`<N>`) in copy-paste blocks — PowerShell parses `<` as a redirection operator. Define `$N = 191` first, then use `$N`.
- The `gh` CLI: prefer the explicit path `"C:\Program Files\GitHub CLI\gh.exe"` (matches `finalize-us` and the rest of the project's tooling).
- File encoding: never `Set-Content -Encoding UTF8` for files with umlauts (double-encodes UTF-8 → mojibake). Use the `Edit` tool or `open(..., encoding='utf-8')` in Python.
