---
name: ogp-research-methodology
description: >
  The discipline that turns a hunch into an accepted result in Open Garden Planner.
  Load this when: starting any investigation (bug, performance question, design doubt);
  forming a hypothesis about why something behaves the way it does; deciding whether the
  evidence you have is sufficient to adopt a change; tempted to declare a fix "done" after
  a green test run; planning an experiment or instrumentation pass; a senior-review finding
  contradicts your understanding; or a manual test contradicts your green tests. Encodes
  the project's evidence bar, prediction-before-experiment rule, adversarial review culture,
  manual-test sovereignty, the idea lifecycle from hunch to docs-of-record (or documented
  retirement), and the named anti-patterns this project has already paid for.
---

# OGP Research Methodology

How this project decides that something is *true* — and that a change deserves to exist.
Every rule below is extracted from a named, verifiable episode in this repo's history
(CLAUDE.md progress tables, `docs/11-risks-and-technical-debt/` §11.4, `docs/roadmap.md`,
`.claude/skills/debug-verbose/skill.md`, `.claude/agents/senior-reviewer.md`). Nothing here
is aspirational; it is all case law. (Repo state: v1.23.0, verified 2026-07-05.)

Scope boundary: this skill is about *epistemics* — what counts as evidence and when a result
is accepted. For the concrete proof recipes (headless repro scripts, geometry traces,
pixel-scan assertions) see `ogp-proof-and-analysis-toolkit`. For which problem to pick, see
`ogp-research-frontier`. For the gate *sequence* (branch → tests → review → draft PR → merge),
see `ogp-change-control`. For symptom→cause triage, see `ogp-debugging-playbook`.

---

## 1. The evidence bar: one mechanism must explain ALL observations

Do not accept a root-cause theory that explains only some of the symptoms. The standard in
this project is: **one mechanism accounts for every observation, including the negatives**
(the things that *didn't* happen, and the fixes that *didn't* work).

**Case law — issue #218** (rotated-circle drag-resize; debug-verbose case study 2026-06-17 +
§11.4 "Closed (#218)"): the symptom set was (a) diameter collapses, (b) diameter *refuses to
grow* on a diagonal drag, (c) centre drifts across the canvas, (d) the dragged handle doesn't
track the cursor, (e) a translucent "ghost" disc lingers. A partial theory ("missing
`prepareGeometryChange`") explained only the ghost. The earlier partial fix — the
rotation-gated `_reanchor_after_rotated_resize` band-aid — held one invariant while the layer
beneath produced nonsense. The accepted mechanism explained everything at once: at 45° a
diagonal drag projects entirely onto one local axis, so `min(width, height)` in
`CircleItem._apply_resize` picked the *unchanged* axis (→ collapse AND refusal to grow AND
cursor non-tracking), two disagreeing fixed-corner inferences (scene-space vs rotated-local)
pinned the wrong corner (→ drift), and the missing `prepareGeometryChange()` left stale
pixels (→ ghost). Only when the headless trace showed radius stuck at 50.00 through an
(80,80) drag — a number the theory *predicted* — was the mechanism accepted, and the fix was
to replace the incoherent step, not to patch around it.

Rules:

- List every observation before theorising — including "fix X didn't help" and "it works
  when unrotated". A theory that is silent about any item on the list is incomplete.
- Fix from evidence, not assumptions. This is the debug-verbose core principle verbatim:
  "stop theorising, start observing." Instrument first (`/debug-verbose`), read stdout, then
  explain.
- Keep the wrong theories. Every debug-verbose case study records its "Theories entertained
  (wrong)" list deliberately — so the next investigator doesn't re-walk dead ends, and so the
  accepted mechanism is visibly stronger than the alternatives it beat.
- When your fix works "except in one case", you do not have the mechanism yet. See §7,
  anti-pattern 1.

---

## 2. Hypotheses must predict numbers before you run

Write down the expected observation — with magnitudes — BEFORE running the experiment.
**An experiment that cannot disagree with you is not an experiment.** Three grounded
exemplars of this practice in the repo:

- **#169 (live-drag projection tolerance, §11.4)**: the hypothesis was that a cm-scale `tol`
  in `project_to_feasible()` creates a slack band — the cursor near a feasible point falls
  inside it on most frames, so the moving vertex slips *up to that band per frame*. The
  predicted slip magnitude (bounded by the 0.5 cm tolerance, per frame, accumulating on a
  near-stationary drag) matched the observed "entire polyline rigidly translates" on a
  fully-constrained chain. The fix pinned the number: default `tolerance=1e-4`
  (sub-render-precision) for live projection, cm-scale retained for full-graph solves.
- **D1.3 (render tool coordinate frame, PR #242)**:
  `tests/unit/test_agent_api_render_coordinate_frame.py` scans pixel columns of a rendered
  image for a marker and asserts the *predicted* correction formula holds exactly:
  `pixel_y = image_height_px − (scene_y_cm − region_y_cm) · px_per_cm`. The `y_flip=True`
  inversion relative to D1.2's scene frame was an empirically established fact, then pinned
  by a test whose expected pixel rows were computed before the scan.
- **§8.12.8 (constraint solver)**: every constraint type has a written residual formula
  (scaled to cm) in `docs/08-crosscutting-concepts/` §8.12.8. A solver investigation starts
  from "residual should be X here"; a residual that doesn't match the table is the finding.

Rules:

- Before instrumenting, write: "if my theory is right, the log will show ___ (value/order/
  sign); if it's wrong, it will show ___." The tangent-constraint case study (fixed
  2026-06-07, debug-verbose) is the model: the `[TANGENT]` per-frame log was expected to show
  a one-shot sign error and instead showed `signed_dist` sliding `+320 → 0 → −320` — a
  *trajectory through the centre* — which killed the sign theory and revealed the
  rank-deficient-Jacobian mechanism.
- Reproduce with the *exact* magnitudes from the field. #218 and the tangent case both
  reproduced only after matching the user's drag magnitude and direction from the
  instrumentation log; small/wrong-direction repros passed green and hid the bug.
- A prediction with no number ("it should behave better") is a hope, not a hypothesis.

---

## 3. Assigned adversarial refutation: the senior-reviewer pass

Results in this project survive only after an institutionalized adversary tries to kill
them. The `senior-reviewer` agent (`.claude/agents/senior-reviewer.md`) is that adversary by
design: fresh context every run ("fresh eyes every time" — no credit for fixing what was
asked), reads **diffs and source, not commit messages** ("trust code, not commit messages"),
cites file:line for every claim, and ranks findings P0 (blocks merge) / P1 (fix before
merge) / P2 (nits) with explicit severity discipline. CLAUDE.md workflow step 7 makes this
pass mandatory before any draft PR; `finalize-us` repeats it pre-PR.

Multiple rounds are **normal, not failure**:

- **#213 / PR #217**: three senior-review rounds; the P0 was caught in round 2 — the species
  resize kept the visual centre fixed but not `transformOriginPoint`, so a *rotated* plant
  saved displaced geometry. Round 1 had passed the unrotated case green. (CLAUDE.md progress
  table + §11.4.)
- **PR #236 (US-C4 smart symbols)**: three senior-review rounds, each catching a new
  exception family escaping a too-narrow catch, until the structural fix landed. (§11.4.)
- **#211 (undo/redo dirty-flag)**: the review found "the deeper rot" — ~30 direct
  `_undo_stack.append` sites that the first fix silently un-dirtied. (CLAUDE.md, §11.4.)

**Refutation goes both ways — the reviewer is fallible and the primary source wins.**
Case law — **#223 / PR**: a senior-review P1 claimed the constraints/properties panels would
lose undo/redo coverage when moved off `can_undo/redo_changed`; it was **refuted by reading
`commands.py`** — those signals are emitted unconditionally on every `undo()`/`redo()`, not
only when the boolean flips (CLAUDE.md #223 entry; §11.4 "#206 wiring" follow-up records the
refutation). Rule: when a review finding contradicts your understanding, neither party is
right by rank — the one who reads the actual code at the cited line wins. Answer a finding
with a file:line citation or a fix, never with an argument from intent.

Rules:

- Run the reviewer in a fresh worktree against the branch diff; re-run after fixes for a
  clean re-review. Do not open the draft PR with outstanding P0/P1.
- Treat a round-2+ P0 as evidence the *test matrix* was too narrow (unrotated-only, kit-only,
  bundled-DB-only), not as reviewer noise. Extend the matrix, don't just patch the instance.
- When you refute a finding, record the refutation and the primary source in the PR/docs —
  #223 did, which is why the next person doesn't re-litigate it.

---

## 4. Manual testing is the final falsifier

Green tests plus a clean review have repeatedly lost to manual testing in this project.
**Schedule for the possibility that manual testing rejects the *design*, not just the code.**

- **ADR-030 / #226 (sidebar)**: the first cut — bottom `QSplitter`, reparent-on-pin,
  equal-share — passed its gates and **failed manual testing** (opening a panel reordered the
  list). The redesign (single `QVBoxLayout` in a `QScrollArea`, never reparented,
  content-weighted stretch, animated open/close) is recorded as an ADR-030 addendum. The
  design died, not a line of code.
- **US-B7 (Paper Space MVP)**: dropped entirely at PR #191 manual-test review — the existing
  `pdf_report_service` already covered print-to-PDF at chosen paper sizes, so the Layout tab,
  viewport item, title block, scale bar, and `paper_layouts` schema were all removed before
  merge. A whole feature retired on evidence of redundancy (`docs/roadmap.md` "US-B7 dropped
  during manual-test review"; CLAUDE.md Package B note).
- **D1.3 layers semantics**: `layers` was subtractive-only (could hide, never show) — the
  gap only surfaced in manual test; the semantics were reworked to snapshot-force-restore so
  an agent can request a layer the user has toggled off (CLAUDE.md D1.3 entry).
- Smaller instances: US-C3's gallery thumbnails (trellis fell through to the round fallback
  — manual-test fix), #213's "nothing resizes on screen" (the ring-only refresh was
  technically correct and user-invisible; §11.4 manual-test follow-up), #212's list-scroll
  fight (manual-test round 2).

Rules:

- The draft PR stays a draft until the user confirms manual testing passed (CLAUDE.md
  workflow step 10). Manual test is sovereign over your green suite and the reviewer's pass.
- Always surface a manual-testing checklist with the work (workflow step 8) — write it so a
  failure is *informative* (which claim died?), not just "looks wrong".
- When manual testing kills something, the kill produces artifacts: an ADR addendum
  (ADR-030), a roadmap note + compat guarantee (US-B7), or a §11.4 lesson (#213). See §5.

---

## 5. The idea lifecycle (mapped to this repo's artifacts)

Every accepted change in this project traversed this pipeline; use it as the map for yours.

1. **Hunch** — from any source in §6.
2. **GitHub issue / roadmap US with acceptance criteria** — `docs/roadmap.md` for user
   stories; issues for defects and follow-ups (the project files follow-ups aggressively:
   #206, #209, #210, #225 each born inside another change's review).
3. **Feature branch** — the experiment space; never master (CLAUDE.md workflow step 1).
4. **Instrumented investigation** — `/debug-verbose` at the first sign of any non-obvious
   bug, before theorising. Predictions written first (§2).
5. **Implementation with pinned tests** — every mechanism gets a test that *fails without
   the fix* (e.g. `test_apply_keeps_rotated_plant_centered`,
   `tests/integration/test_rotation_aware_resize.py` with its
   {shape}×{0,45,215°}×{corner,edge} matrix, the D1.3 coordinate-frame test).
6. **Senior-review rounds** — until no outstanding P0/P1 (§3). Multiple rounds expected.
7. **Draft PR** — every coding job ends with one; never a bare pushed branch.
8. **Manual test (sovereign)** — may reject code, design, or the feature itself (§4).
9. **Docs of record** — §11.4 pitfall entry (with "Rule:" / "Lesson:"), ADR or ADR addendum,
   FR-* entry, roadmap completion note, debug-verbose case study. CLAUDE.md: "all lessons
   learned MUST be documented." A result that isn't in the docs of record is not yet
   accepted — it is merely merged.
10. **Adopted** — OR **documented retirement**.

**Retirement is a first-class outcome, and it still produces knowledge.** US-B7 is the
exemplar: dropped WITH rationale recorded in both CLAUDE.md and `docs/roadmap.md`, plus a
compat *guarantee* — `FILE_VERSION` stays 1.4, and the loader silently ignores the
`paper_layouts` key that short-lived draft builds wrote into `.ogp` files. A retired idea
that leaves behind a recorded reason and a compatibility contract has paid for itself.
Never delete an idea silently; retire it on the record.

---

## 6. Where good ideas historically came from

Know the sources so you keep them open (deciding *which* to pursue is
`ogp-research-frontier`'s job):

- **Manual-test findings**: the C3 gallery-thumbnail shape-routing fix; #213's "nothing
  resizes on screen"; #212 round 2's scroll-fight signature guard; the D1.3 layers rework.
- **Review-round escalations**: P0s found in round 2+ (#213's rotated-pivot P0; #236's
  successive exception families; #211's ~30 direct-append sites; #222's Layer-combo P1) —
  each escalation generalized into a rule, not just a patch.
- **Dogfooding the CAD workflows**: Package A (relative/polar input, snap modes) and
  Package B — explicitly titled "closing the CAD precision gap" — exist because real
  CAD-style use exposed precision gaps (CLAUDE.md Phase 13 tables).
- **User-owner priorities**: Package D's shape comes from a recorded planning session —
  `docs/roadmap.md` "Design decisions (from the planning session)" under the Package D
  section.
- **Pitfalls generalized into rules**: §11.4 entries ending in "Rule:" / "Lesson:" (the
  trust-boundary broad-catch rule from #236; the enum-combo UNKNOWN rule from #231; the
  two-chokepoint undo-stack invariant from #209; the shared-id-derivation rule from #227).
  A fixed bug that didn't yield a rule is an unfinished fix.
- **Debug sessions raising sister issues**: the US-12.10d session filed #170 and #171 as
  deferred sister issues discovered mid-investigation (debug-verbose case study). Capture
  what you find even when it's out of scope.

---

## 7. Anti-patterns — observed, named, and paid for

1. **The losing game** — declaring victory after each exception-family patch. PR #236: the
   untrusted-JSON loader caught `(OSError, JSONDecodeError, ValueError)`; three consecutive
   review rounds each surfaced a new escaping family (`ArithmeticError`/`TypeError`, then
   `RecursionError` during `ast.parse`, then `AttributeError` in the structural phase). Each
   "fix" added the family that bit it and re-declared victory. §11.4 names this "the losing
   game" and gives the structural exit: one broad `except Exception` at the ingestion seam
   for untrusted input; narrow catches only for first-party input. Generalized: if your fix
   is "add the case that just failed", stop and find the structural boundary.
2. **Post-correcting an incoherent step instead of fixing the step** — #218: a re-anchor
   layered over `min(w,h)` + two disagreeing fixed-corner inferences "can never be right
   because the layer beneath produces nonsense" (§11.4, debug-verbose lesson (a)). The senior
   review flagged the fragility before it shipped. If a correction pass exists to compensate
   for a step you don't trust, replace the step.
3. **Date-matching CI state instead of watching state transitions** — issue #229: waiting on
   releases by grepping `$(date ...)` breaks on local-vs-UTC `createdAt` mismatches and
   same-day re-runs, and a date match *cannot detect failure*. The rule (codified in
   `.claude/skills/finalize-us/skill.md`): wait on a **state transition** — `gh pr checks
   --watch --fail-fast`, or the top release tag *differing* from the one captured before
   merge. Generalized: poll for "the world changed from X to Y", never for "something
   matching today exists".
4. **Registering translations without checking the call-site path** — §11.4:
   `test_german_ts_has_no_unfinished` only verifies strings *already extracted* into the
   `.ts` file; a plain f-string or a `_SEGMENT_LABELS[key]` dict lookup never reaches
   `pylupdate6`, so registering the German in `scripts/fill_translations.py` alone changes
   nothing in the running app. The epistemic lesson is general: **a green gate only proves
   what the gate actually measures** — know the gate's blind spot before citing it as
   evidence (the mitigation, `TestNoHardcodedEnglish`, was built precisely to cover the
   blind spot).

Honourable mentions from the same corpus: construct-and-test is not serialize-and-test
(US-12.10d — dataclass fields missing from `to_dict`/`from_dict` while 14 integration tests
passed); "passes alone, fails together" almost always means shared global state, and green
CI does not prove the local full suite is clean (`QSettings.setDefaultFormat` leak, §11.4).

---

## 8. Methodology checklist (one page — run it for any investigation)

1. **State the hypothesis** in one sentence naming a mechanism, not a symptom
   ("`min(w,h)` picks the unchanged axis at 45°", not "resize is broken").
2. **Predict the numbers**: write down what the instrumentation/experiment will show if the
   hypothesis is right AND what it will show if it's wrong. Magnitude, sign, order. (§2)
3. **Instrument**: `/debug-verbose` — `[TAG]`-prefixed prints on the execution spine,
   `traceback.format_stack()` at unexpected-call sites; reproduce with the *exact* field
   magnitudes.
4. **Collect**: read stdout against the prediction. A surprise is data — log it into the
   wrong-theories list, revise, repeat.
5. **One-mechanism check**: does the surviving theory explain EVERY observation, including
   the negatives and the failed fixes? If any observation is unexplained, you're not done.
   (§1)
6. **Fix the step, not around it**; pin the mechanism with a test that fails without the
   fix, on a matrix that includes the degenerate cases (rotation angles, ties, UNKNOWN
   values, teardown).
7. **Adversarial pass**: senior-reviewer in a fresh worktree; resolve or *refute-with-source*
   every P0/P1; re-run for a clean pass. Expect rounds. (§3)
8. **Manual test** (sovereign): provide the checklist; be prepared for the design — or the
   feature — to die there. (§4)
9. **Docs of record**: §11.4 lesson (ending in a Rule), ADR/addendum if a decision changed,
   FR/roadmap update, debug-verbose case study for non-obvious bugs.
10. **Adopt or retire on the record**: merged + documented, or dropped WITH rationale and
    any compat guarantee written down (US-B7 pattern). Remove all instrumentation either way.

---

## When NOT to use this skill

- **Trivial, mechanism-free changes** (typo, doc wording, a rename with no runtime surface):
  the lifecycle gates in `ogp-change-control` still apply, but you don't need a hypothesis
  ledger for a typo.
- **You need the concrete experiment recipes** (headless drag drivers, pixel scans, residual
  probes): that's `ogp-proof-and-analysis-toolkit`.
- **You're choosing what to investigate**, not how: `ogp-research-frontier`.
- **You're mid-triage on a known recurring symptom**: `ogp-debugging-playbook` (and its
  precedent index) is faster; come back here when the playbook has no precedent and you're
  forming a fresh theory.
- **You're sequencing release/merge mechanics**: `ogp-change-control`.
- Related references: `ogp-failure-archaeology` (the full incident corpus behind §7),
  `ogp-validation-and-qa` (test-layer policy), `ogp-docs-and-writing` (how to write the
  docs-of-record artifacts), `ogp-qt-cad-reference` / `ogp-garden-domain-reference`
  (domain facts your hypotheses will lean on).

---

## Provenance and maintenance

Volatile facts date-stamped 2026-07-05 (repo at v1.23.0, Phases 1–13 Packages A–D1.3
complete). Re-verify the cited episodes before relying on them:
`grep -n "Closed (#218)\|losing game\|#169" docs/11-risks-and-technical-debt/README.md` ·
`grep -n "US-B7 dropped\|planning session" docs/roadmap.md` ·
`grep -in "refuted by reading\|senior-review rounds\|P0 caught" CLAUDE.md` ·
`grep -rn "issue #229" .claude/skills/finalize-us/skill.md` ·
`sed -n '441,455p' docs/08-crosscutting-concepts/README.md` (§8.12.8 residuals) ·
`ls tests/unit/test_agent_api_render_coordinate_frame.py` ·
`head -20 .claude/agents/senior-reviewer.md` and
`head -12 .claude/skills/debug-verbose/skill.md` (core principle + case-study format).
