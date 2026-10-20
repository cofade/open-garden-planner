# Pitfalls: process and documentation

Standing rules for this area, one entry each. The heading is the rule. Pins and sources are listed under each entry. Index: [§11.4](../README.md#114-known-development-pitfalls).

### PF-PRC-01


- **Rule:** "The app changed behaviour" is a claim about a *setting* until the setting has been read.
- **Pinned by:** `tests/conftest.py`
- **Source:** #366
- **Status:** pointer → [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16)
- **Legacy:** README L182

Held in [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16). The entry keeps the rule and its pin; the account is in the link.

### PF-PRC-02


- **Rule:** A claim written from the producer's side is not a delivered feature — and a test that skips the consumer cannot catch it.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** pointer → [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16)
- **Legacy:** README L190

Held in [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16). The entry keeps the rule and its pin; the account is in the link.

### PF-PRC-03

- **Rule:** Lesson: before treating "the UI doesn't update" as a bug, check whether the change contradicts a *formally accepted* dec
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L224

**Lesson**: before treating "the UI doesn't update" as a bug, check whether the change contradicts a *formally accepted* decision, not just a module docstring — grep the ADRs, not only the code you're about to touch; reversing one is legitimate with the right authority, but it has to be a conscious act, amended in place, not a silent override. And once a fix like this is written, **render it** before trusting it — a green suite that only asserts against private helpers proved nothing about the one thing a user actually looks at; a single test that paints to a `QImage` and measures pixel coverage would have caught the regression before it ever reached review. See ADR-037's growth addendum, FR-SUN-08, `core/plant_sizing.py`'s docstring (all amended alongside this entry), and the debug-verbose skill's matching case study for the full investigation.

### PF-PRC-04

- **Rule:** NEVER use PowerShell `Set-Content -Encoding UTF8` for files containing non-ASCII characters
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L330

- **NEVER use PowerShell `Set-Content -Encoding UTF8` for files containing non-ASCII characters**: PowerShell 5.1's `Get-Content -Raw` auto-detects encoding but mis-guesses UTF-8-without-BOM as Latin-1; the subsequent `Set-Content -Encoding UTF8` then writes those mis-decoded characters back as UTF-8 with a BOM, **double-encoding every umlaut** (`ö` → `Ã¶`, `ß` → `ÃŸ`, `ä` → `Ã¤`, etc.). Symptom: the entire German UI displays as mojibake after a "harmless" find/replace. Trigger in this codebase: doing in-place text replacement of `Anbauerfolge` → `Anbaufolge` in `scripts/fill_translations.py` and `open_garden_planner_de.ts`. Recovery: `git checkout HEAD -- <files>` and redo the edit with Python (the `Edit` tool, or a small script using `open(..., encoding="utf-8")`). For multi-file bulk replacements use Python, `sed -i.bak`, or `perl -i -pe` — anything but PowerShell. Detect a regressed file fast with `grep -c "Ã¶\|Ã¤\|Ã¼\|ÃŸ" <file>` — any non-zero count means double-encoded.

### PF-PRC-05

- **Rule:** A `file.py:line` citation drifts silently when unrelated features grow the file — measured, not hypothetical
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #334, #336, #342, #346, #347
- **Status:** standing
- **Legacy:** README L434

- **A `file.py:line` citation drifts silently when unrelated features grow the file — measured, not hypothetical** (#336, 2026-09-04): nothing verified that the identifiers cited across the `SKILL.md` files in both `.claude/skills/` and `.agents/skills/` plus `CLAUDE.md`/`AGENTS.md` still resolved. The motivating data point: `deliver-package` (PR #334, written one day earlier with unusually careful sourcing and a senior-reviewer pass) still shipped three citation errors, found only by hand — a package range that mixed in an unrelated epic and a standalone issue, two issues wrongly described as having GitHub sub-issues, and a closed issue cited as an example of "an open issue". Building `scripts/check_skill_citations.py` (§8.10) and running it cold against the existing corpus found one more, live: `ogp-architecture-contract`'s note that the Smart Symbols sidebar panel is hidden "via one line" cited `application.py:1574`; the line is now 2893 — 1319 lines of drift from Google Maps/satellite-import features (#342/#346/#347) landing in between, in a 6700-line file. Two other skill files (`ogp-config-and-flags`, `ogp-research-frontier`) carried the same stale line number for the same fact — a single piece of knowledge, copied three times, rotting once and not being noticed twice. Fix: correct all three, then gate it — the checker resolves *identifiers* (does a heading/ADR/FR/symbol/issue-number still exist), not *claims* (is the surrounding prose still accurate), and tolerates trivial refactor churn by accepting a `file.py:line` citation whose named symbol is still found within a small window of the cited line rather than demanding an exact match. Lesson: a fact copied into N documents needs N independent chances to rot and one shared chance to be caught; a citation gate pays for itself the first time two of the three copies are wrong and nobody had reason to open the third.

### PF-PRC-06

- **Rule:** The citation gate's own senior review found the gate had almost no teeth on the dimension that motivated it, and the fix needed its own mutation-tested regressions before it actually had any
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #336
- **Status:** standing
- **Legacy:** README L436

- **The citation gate's own senior review found the gate had almost no teeth on the dimension that motivated it, and the fix needed its own mutation-tested regressions before it actually had any** (#336, 2026-09-05): round 1 of review found `_extract_symbol` took the *leading* identifier of a cited snippet (`self._sidebar_controller.set_panel_visible(...)` checked for `"self"` — present on nearly every line of any class body), a repeated regex capture group that silently dropped every middle number in an `ADR-a/b/c` list, and a `KNOWN_EXCEPTIONS` declared as a `frozenset` but built by calling `frozenset()` on a **dict literal** — which iterates only the keys, discarding every stated exemption reason without a type error anywhere. Fixing the leading-identifier bug and adding a "regression test" for it both landed **green on the unfixed code**, because the one corpus citation exercising that shape had been rewritten (to drop the `self._x.` prefix) in the same commit as the fix — the test asserted the citation *now* passed, not that the *specific defect* was caught. Only reproducing the bug via mutation (temporarily reverting `_extract_symbol` to `text[:leading identifier]` and re-running the suite) showed the "regression test" was vacuous; the fix that made it non-vacuous was a fixture engineered to contain no string literal at all, so the (separately correct) literal-proximity check couldn't accidentally mask which identifier got extracted. Lesson, general: a regression test for "citation X used to slip past check Y" only has teeth if X *itself*, not a fixed-up copy of X, is what's asserted against — and the fastest way to know is to reintroduce the bug and watch the test go red (the same rule §8.10 states for guards in general, applied to the guard that watches every other guard's citations). Separately, the issue-number check depends on a snapshot (`tests/data/issue_registry.json`) refreshable only by an authenticated `gh` CLI on a dev machine — CI cannot regenerate it, so a PR that adds a genuinely new `#NNN` reference to a skill file must run `scripts/refresh_issue_registry.py` locally before pushing, or `test_real_corpus_citations_all_resolve` goes red for a reason the CI log alone won't explain.

### PF-PRC-07


- **Rule:** A drift-tolerance window that is merely "generous" is a false safety claim, not a weaker one
- **Pinned by:** none — pending Phase 3 review
- **Source:** #336
- **Status:** pointer → [§8: 8.10.1 Gating our own documentation's shell commands](../../08-crosscutting-concepts/README.md#8101-gating-our-own-documentations-shell-commands)
- **Legacy:** README L438

Held in [§8: 8.10.1 Gating our own documentation's shell commands](../../08-crosscutting-concepts/README.md#8101-gating-our-own-documentations-shell-commands). The entry keeps the rule and its pin; the account is in the link.

### PF-PRC-08

- **Rule:** Named residual, measured, not swept under the fix
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L440

**Named residual, measured, not swept under the fix**: shrinking the window controls for drift *distance*; it does nothing for symbol *selectivity*. `execute` — the very name used in the motivating `core/commands.py` example above — occurs on 76 of that file's 2861 lines, so even the 20-line window still lets a citation to `execute` resolve against 2351 of 2861 possible line numbers (82.2%); at every candidate line, some `execute` is always within reach. A citation naming a common, generic identifier in a large file is real but weak protection: it catches "the file got so much smaller/bigger that nothing named `execute` remains nearby" and nothing subtler. The corpus's actual citations are unaffected today (every one of them sits at distance 0 from its symbol, verified), but the next contributor who cites a common name in a big file should know the check they're relying on is thinner than "the gate passed" implies. Closing this for good needs a selectivity rule (reject a symbol match against more than a couple of candidate lines in the window, or require a `def`/`class` form when one exists) — filed as follow-up work, not done here.

### PF-PRC-09


- **Rule:** **An issue's "verified repo facts" are a claim about the code, not the code — and a rule that
- **Pinned by:** none — pending Phase 3 review
- **Source:** #331
- **Status:** pointer → [ADR: ADR-034 addendum: succession domain schema, determinism, and a SHARED season-segment fallback (US-D3.2, #](../../09-architecture-decisions/README.md#adr-034-addendum-succession-domain-schema-determinism-and-a-shared-season-segment-fallback-us-d32-331)
- **Legacy:** README L471

Held in [ADR: ADR-034 addendum: succession domain schema, determinism, and a SHARED season-segment fallback (US-D3.2, #](../../09-architecture-decisions/README.md#adr-034-addendum-succession-domain-schema-determinism-and-a-shared-season-segment-fallback-us-d32-331). The entry keeps the rule and its pin; the account is in the link.

### PF-PRC-10


- **Rule:** Lesson: verify every file:line and every "reuse X" instruction against the code before writing it
- **Pinned by:** none — pending Phase 3 review
- **Source:** none recorded
- **Status:** pointer → [PF-PRC-09](12-process-and-docs.md#pf-prc-09)
- **Legacy:** README L504

Duplicate of [PF-PRC-09](12-process-and-docs.md#pf-prc-09): the same lesson, with the same pins.
