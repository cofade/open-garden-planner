# Pitfalls: process and documentation

One entry per lesson, each under its permanent `PF-<AREA>-<NN>` ID. Each entry gives its rule, the test that pins it, its sources and its status. Index: [§11.4](../README.md#114-known-development-pitfalls).

### PF-PRC-01

- **Rule:** Read a persisted setting with the API that wrote it, since a `QSettings` slash key is a registry subkey, and check the branch's own diff before treating a behaviour report as a bug.
- **Pinned by:** none — The body names only `tests/conftest.py`, the fixture that isolates test settings, which is not a test of this rule.
- **Source:** #366
- **Status:** standing
- **Legacy:** b1faaa9 README L182

- **"The app changed behaviour" is a claim about a *setting* until the setting has been read.** (Issue #366, owner's manual test): "on startup it no longer asks for my recent projects, it lands on the empty canvas." The obvious suspect was this branch, and the obvious suspect was **wrong twice** — first I blamed the test suite for persisting `show_welcome_on_startup = False`, then I "corrected" myself by pointing at the settings getter, which was also wrong because `QSettings` maps a slash key (`startup/show_welcome`) to a registry **subkey**, so a `Get-ItemProperty` on the parent shows nothing and the key looks absent. The value was there, set to `false`, and the test suite was innocent: `tests/conftest.py` rebinds the org to `cofade_test`, so test writes cannot reach `cofade` — proven by running a test that sets the flag and re-reading the real key. Nothing in the PR touched `welcome_dialog.py` or `settings.py` (empty diff), and the dialog's "Show this screen on startup" checkbox persists that value on click. So it was a user preference, undone with one `reg delete`. Two lessons: **read the persisted value with the same API that wrote it** — `reg query <key> /v` on the *subkey*, or the getter itself, not a parent-key dump; and **check the PR's own diff before blaming it or writing a fix.** A settings-shaped report is the one class of bug report where the correct patch is very often no patch.

### PF-PRC-02

- **Rule:** A user-visible claim is delivered only when a test drives the user's own path and asserts what reaches the user, so grep every new result field for its consumers.
- **Pinned by:** none — The named `test_a_successful_merge_does_report_its_backup` does not exist; the renamed `tests/unit/test_ai_client_onboarding_registry.py::TestSurgicalToml::test_a_successful_merge_reports_its_backup_in_the_detail` is not named here.
- **Source:** #366
- **Status:** standing
- **Legacy:** b1faaa9 README L190

- **A claim written from the producer's side is not a delivered feature — and a test that skips the consumer cannot catch it.** (Issue #366, senior-review round 5, five rounds into one branch): round 4 moved the merge's `.bak` to just before the write, put its location into `InstallResult.detail`, and documented the user-facing consequence in three places — the function's docstring, ADR-035 and this log. All three were true about the **producer** and false about the **product**: the Connect dialog's success branch renders `Added to {client}.` and never read `result.detail`; only the *failure* branch formatted it. The field was populated, the field was documented, and the user's experience was exactly what it was before the fix. The test named `test_a_successful_merge_does_report_its_backup` made this invisible by construction — it asserted `backup is not None and backup.exists()` while its name and docstring promised "the caller is told where it is", and it called the private `_merge_into_config`, which cannot see `_report()` or `install_to_client`. Two rules, both cheap: **a test about a user-visible claim has to go through the path the user goes through** (that one now drives `install_to_client` and asserts the string names both paths, so the name is enforceable); and when a field is added to a result object, **grep for its consumers** — `InstallResult` had two fields the success path never read, and nothing in the type system or the suite noticed. The sibling failure in the same round was a fixture that cleared `CLAUDE_CONFIG_DIR` but not `XDG_CONFIG_HOME`, so a test read the developer's real `opencode.jsonc` and passed vacuously against a file the code could not reach — which is the §11.4 scar from round 1, in a new place. **A fixture that redirects config paths must clear every env var the resolver honours, and the fix is to look at the sibling fixture that already got it right.**

### PF-PRC-03

- **Rule:** Before treating a UI that does not update as a bug, grep the ADRs for an accepted decision it may contradict, and render any change to pixels before trusting it.
- **Pinned by:** none — The body names no test; it only describes a pixel-coverage test that would have caught the regression.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L224

**Lesson**: before treating "the UI doesn't update" as a bug, check whether the change contradicts a *formally accepted* decision, not just a module docstring — grep the ADRs, not only the code you're about to touch; reversing one is legitimate with the right authority, but it has to be a conscious act, amended in place, not a silent override. And once a fix like this is written, **render it** before trusting it — a green suite that only asserts against private helpers proved nothing about the one thing a user actually looks at; a single test that paints to a `QImage` and measures pixel coverage would have caught the regression before it ever reached review. See ADR-037's growth addendum, FR-SUN-08, `core/plant_sizing.py`'s docstring (all amended alongside this entry), and the debug-verbose skill's matching case study for the full investigation.

### PF-PRC-04

- **Rule:** Never edit non-ASCII files with PowerShell `Set-Content -Encoding UTF8`, which double-encodes UTF-8 into mojibake; edit them with Python using `encoding="utf-8"` or with the `Edit` tool.
- **Pinned by:** none — The body names only a grep detection command and no test.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L330

- **NEVER use PowerShell `Set-Content -Encoding UTF8` for files containing non-ASCII characters**: PowerShell 5.1's `Get-Content -Raw` auto-detects encoding but mis-guesses UTF-8-without-BOM as Latin-1; the subsequent `Set-Content -Encoding UTF8` then writes those mis-decoded characters back as UTF-8 with a BOM, **double-encoding every umlaut** (`ö` → `Ã¶`, `ß` → `ÃŸ`, `ä` → `Ã¤`, etc.). Symptom: the entire German UI displays as mojibake after a "harmless" find/replace. Trigger in this codebase: doing in-place text replacement of `Anbauerfolge` → `Anbaufolge` in `scripts/fill_translations.py` and `open_garden_planner_de.ts`. Recovery: `git checkout HEAD -- <files>` and redo the edit with Python (the `Edit` tool, or a small script using `open(..., encoding="utf-8")`). For multi-file bulk replacements use Python, `sed -i.bak`, or `perl -i -pe` — anything but PowerShell. Detect a regressed file fast with `grep -c "Ã¶\|Ã¤\|Ã¼\|ÃŸ" <file>` — any non-zero count means double-encoded.

### PF-PRC-05

- **Rule:** A file-and-line citation copied into skill or agent-context files drifts silently as unrelated code grows, so every cited identifier is resolved by a mechanical gate rather than by review.
- **Pinned by:** none — The body names only `scripts/check_skill_citations.py`, and a script is not a pin.
- **Source:** #334, #336, #342, #346, #347
- **Status:** standing
- **Legacy:** b1faaa9 README L434

- **A `file.py:line` citation drifts silently when unrelated features grow the file — measured, not hypothetical** (#336, 2026-09-04): nothing verified that the identifiers cited across the `SKILL.md` files in both `.claude/skills/` and `.agents/skills/` plus `CLAUDE.md`/`AGENTS.md` still resolved. The motivating data point: `deliver-package` (PR #334, written one day earlier with unusually careful sourcing and a senior-reviewer pass) still shipped three citation errors, found only by hand — a package range that mixed in an unrelated epic and a standalone issue, two issues wrongly described as having GitHub sub-issues, and a closed issue cited as an example of "an open issue". Building `scripts/check_skill_citations.py` (§8.10) and running it cold against the existing corpus found one more, live: `ogp-architecture-contract`'s note that the Smart Symbols sidebar panel is hidden "via one line" cited `application.py:1574`; the line is now 2893 — 1319 lines of drift from Google Maps/satellite-import features (#342/#346/#347) landing in between, in a 6700-line file. Two other skill files (`ogp-config-and-flags`, `ogp-research-frontier`) carried the same stale line number for the same fact — a single piece of knowledge, copied three times, rotting once and not being noticed twice. Fix: correct all three, then gate it — the checker resolves *identifiers* (does a heading/ADR/FR/symbol/issue-number still exist), not *claims* (is the surrounding prose still accurate), and tolerates trivial refactor churn by accepting a `file.py:line` citation whose named symbol is still found within a small window of the cited line rather than demanding an exact match. Lesson: a fact copied into N documents needs N independent chances to rot and one shared chance to be caught; a citation gate pays for itself the first time two of the three copies are wrong and nobody had reason to open the third.

### PF-PRC-06

- **Rule:** A regression test for a gate defect has teeth only if it asserts the original defect itself, so reintroduce the bug and watch the test go red before trusting it.
- **Pinned by:** none — The body names `test_real_corpus_citations_all_resolve` only for its separate issue-registry note, and no test for the mutation rule.
- **Source:** #336
- **Status:** standing
- **Legacy:** b1faaa9 README L436

- **The citation gate's own senior review found the gate had almost no teeth on the dimension that motivated it, and the fix needed its own mutation-tested regressions before it actually had any** (#336, 2026-09-05): round 1 of review found `_extract_symbol` took the *leading* identifier of a cited snippet (`self._sidebar_controller.set_panel_visible(...)` checked for `"self"` — present on nearly every line of any class body), a repeated regex capture group that silently dropped every middle number in an `ADR-a/b/c` list, and a `KNOWN_EXCEPTIONS` declared as a `frozenset` but built by calling `frozenset()` on a **dict literal** — which iterates only the keys, discarding every stated exemption reason without a type error anywhere. Fixing the leading-identifier bug and adding a "regression test" for it both landed **green on the unfixed code**, because the one corpus citation exercising that shape had been rewritten (to drop the `self._x.` prefix) in the same commit as the fix — the test asserted the citation *now* passed, not that the *specific defect* was caught. Only reproducing the bug via mutation (temporarily reverting `_extract_symbol` to `text[:leading identifier]` and re-running the suite) showed the "regression test" was vacuous; the fix that made it non-vacuous was a fixture engineered to contain no string literal at all, so the (separately correct) literal-proximity check couldn't accidentally mask which identifier got extracted. Lesson, general: a regression test for "citation X used to slip past check Y" only has teeth if X *itself*, not a fixed-up copy of X, is what's asserted against — and the fastest way to know is to reintroduce the bug and watch the test go red (the same rule §8.10 states for guards in general, applied to the guard that watches every other guard's citations). Separately, the issue-number check depends on a snapshot (`tests/data/issue_registry.json`) refreshable only by an authenticated `gh` CLI on a dev machine — CI cannot regenerate it, so a PR that adds a genuinely new `#NNN` reference to a skill file must run `scripts/refresh_issue_registry.py` locally before pushing, or `test_real_corpus_citations_all_resolve` goes red for a reason the CI log alone won't explain.

### PF-PRC-07

- **Rule:** A drift-tolerance window must sit strictly below the smallest measured real drift it has to catch, so the citation checker's `_SYMBOL_WINDOW_LINES` is 20 lines rather than a generous guess.
- **Pinned by:** none — The body names no test; `tests/unit/test_skill_citations.py::test_seventy_six_line_drift_with_correct_symbol_is_rejected` covers it but is not named here.
- **Source:** #336
- **Status:** pointer → [§8: 8.10.1 Gating our own documentation's shell commands](../../08-crosscutting-concepts/README.md#8101-gating-our-own-documentations-shell-commands)
- **Legacy:** b1faaa9 README L438

Held in [§8: 8.10.1 Gating our own documentation's shell commands](../../08-crosscutting-concepts/README.md#8101-gating-our-own-documentations-shell-commands). The entry keeps the rule and its pin; the account is in the link.

### PF-PRC-08

- **Rule:** The citation checker's window limits drift distance but not symbol selectivity, so a citation of a common identifier such as `execute` in a large file is only weak protection.
- **Pinned by:** none — The body names no test, and it records a residual the checker does not close.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L440

**Named residual, measured, not swept under the fix**: shrinking the window controls for drift *distance*; it does nothing for symbol *selectivity*. `execute` — the very name used in the motivating `core/commands.py` example above — occurs on 76 of that file's 2861 lines, so even the 20-line window still lets a citation to `execute` resolve against 2351 of 2861 possible line numbers (82.2%); at every candidate line, some `execute` is always within reach. A citation naming a common, generic identifier in a large file is real but weak protection: it catches "the file got so much smaller/bigger that nothing named `execute` remains nearby" and nothing subtler. The corpus's actual citations are unaffected today (every one of them sits at distance 0 from its symbol, verified), but the next contributor who cites a common name in a big file should know the check they're relying on is thinner than "the gate passed" implies. Closing this for good needs a selectivity rule (reject a symbol match against more than a couple of candidate lines in the window, or require a `def`/`class` form when one exists) — filed as follow-up work, not done here.

### PF-PRC-09

- **Rule:** Treat an issue's verified repo facts as claims to check against the code, and confirm that a reusable-looking method can see the shape of the question before reusing it.
- **Pinned by:** none — The body names no test for this process rule.
- **Source:** #331
- **Status:** standing
- **Legacy:** b1faaa9 README L471

**An issue's "verified repo facts" are a claim about the code, not the code — and a rule that
sounds reusable can be structurally blind to the case in front of you** (US-D3.2, #331)

Four of #331's own "verified repo facts" were wrong, and three of the four would have produced
a plausible, tested, wrong implementation:

1. It described **three** season segments (`spring`/`summer`/`fall`). `models/succession.py`
   has always had **four** (`early_spring`/`late_spring`/`summer`/`fall`), with boundaries in the
   module docstring. Building to the issue's prose mislabels a third of the growing season. The
   issue's *acceptance criterion* ("labels matching the module's own segment definitions - pinned
   against the documented formulas, not against a re-implementation") was the correct instruction
   and was followed instead. **An acceptance criterion that contradicts the issue's own context
   is usually the accurate one.**
2. It said a plan with no geo-location has "unknown" season segments, implying new code. The
   succession **dialog already had** a calendar-month fallback, as a private table. Copying it
   would have given an agent and the GUI two definitions of "summer" for the same bed. It was
   moved to `models/succession.py` and both callers now use
   `resolve_season_segments(year, location) -> (segments, are_fallback)`.
   **`is the behaviour absent, or just absent from where you looked?`** An issue describing
   something as missing is evidence about the issue, not about the repo.
3. It said to reuse `crop_rotation_service` "rather than re-derive family rules". The cross-year
   cooldown *is* reused verbatim. But the acceptance criterion - never propose a crop that
   conflicts with **an earlier entry in the same bed** - is unmeetable by
   `check_plant_placement`, which compares a candidate only against `records[0]`, the single most
   recent planting record. It cannot see "tomato after the garlic entry three slots ago".
   Succession is several crops in ONE season; that service models one record per season across
   YEARS. And succession entries never enter rotation history at all, because only the Crop
   Rotation panel writes `PlantingRecord`s. **A reusable-looking method can be blind to the shape
   of the question.** Two unrelated mismatches (arity and history-provenance) had to be checked
   separately, and either alone would have produced a call that looked right, passed a casual
   test, and excluded almost nothing.
4. `commands.py:2472` for `SetSuccessionPlanCommand` was ~216 lines stale (it is at 2688).

### PF-PRC-10

- **Rule:** Verify every file-and-line citation and every reuse instruction in an issue against the code before writing any code, treating the issue's context section as a hypothesis.
- **Pinned by:** none — The body names no test for this process rule.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L504

**Lesson: verify every `file:line` and every "reuse X" instruction against the code before writing
a line, and treat an issue's context section as a hypothesis.** The costs here were cheap only
because the check was done first; the third one in particular would have shipped a tool that
excluded almost nothing while reporting a rotation check it had not performed.
