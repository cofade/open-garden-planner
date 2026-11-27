---
id: ADR-044
title: "Build Provenance Attestation for Release Artifacts"
status: "Accepted (2026-09-15)"
refs: ["#356"]
legacy_anchor: adr-044-build-provenance-attestation-for-release-artifacts-issue-356
---

# ADR-044: Build Provenance Attestation for Release Artifacts

**Status**: Accepted (2026-09-15)

**Context**: A user's Windows Defender quarantined the installed `OpenGardenPlanner.exe` as `Trojan:Script/Wacatac.C!ml` (issue #356). This matches a well-documented false-positive pattern for PyInstaller-built executables (confirmed against multiple upstream PyInstaller issues and community reports) — Defender's ML heuristics are prone to misfire on unsigned, UPX-compressed, low-download-reputation binaries, and `installer/ogp.spec` builds exactly that profile (`upx=True`, no Authenticode signature). This isn't new: issue #89 hit the milder SmartScreen "unrecognized publisher" warning on the same installer and was closed `not_planned` — as of this decision on 2026-09-15, the project had no budget for a paid Authenticode code-signing certificate, so users were pointed at Microsoft's false-positive submission forms instead (§11.1, §11.2). The only existing compensating control, `SHA256SUMS.txt`, proves download integrity (the file wasn't corrupted or tampered with in transit) but says nothing about whether the binary actually traces back to this project's public source — it can't answer "prove this wasn't built from a compromised or modified copy," which is the standard of proof a security-conscious reporter reasonably wants before trusting a "just a false positive" explanation.

**Decision**: Ship GitHub Artifact Attestations (build provenance) on every release, via `actions/attest-build-provenance@v4` in `release.yml`, run after the GitHub Release is created (attestation is keyed to each artifact's digest, not to the release, so this ordering costs nothing and keeps a Sigstore/attestations-API hiccup from ever blocking a release — see "Rejected placement" below). This is a free, GitHub-native, Sigstore-backed mechanism: it cryptographically binds each artifact's digest to the exact commit SHA and public workflow run that produced it. It covers three subjects, not just the installer: the NSIS installer, `SHA256SUMS.txt`, and the raw app exe the installer packages (`dist/OpenGardenPlanner/OpenGardenPlanner.exe` — the exact file Defender quarantined in #356; attesting only the installer would not let that reporter verify the file they actually have). Anyone can independently verify with `gh attestation verify OpenGardenPlanner-<version>-Setup.exe -R cofade/open-garden-planner --signer-workflow cofade/open-garden-planner/.github/workflows/release.yml` — no account, no paid tooling, no trust in the maintainer's word required. This directly answers the "prove it, don't just assert it" bar: the artifact's provenance is checkable against the project's own public Actions run history and source commit, which is itself open for inspection. Upstream documents `attest-build-provenance` as "simply a wrapper on top of `actions/attest`" and recommends new integrations call `actions/attest` directly — noted here so a future maintainer bumping past v4 (or hitting the wrapper's eventual retirement) knows that migration path exists; not adopted now since the wrapper is simpler for this workflow's single-purpose use.

**Rejected alternatives**:

| Option | Why not |
|--------|---------|
| Paid Authenticode code-signing certificate | At the 2026-09-15 decision, a recurring certificate fee was outside the project's budget (issue #89), and signing was outside #356's source-provenance scope. This historical rejection does not rule out no-cost options, and it is not the only fix: [#375](https://github.com/cofade/open-garden-planner/issues/375) was decided on 2026-11-06 (ADR-073) — Authenticode for the GitHub installer stays deferred with named triggers, and the Microsoft Store (Microsoft-signed MSIX) is adopted as a second channel. No signed release has established that a signature alone suppresses these detections. |
| Do nothing beyond re-explaining the false-positive pattern | Repeats the #89 response, which already reads to a security-conscious user as "trust us." Doesn't meet the bar of independently checkable proof the reporter asked for. |
| Self-hosted GPG signing of release assets | Requires the maintainer to generate, protect, and publish a personal key, and requires each user to independently establish trust in *that* key out-of-band — strictly weaker than GitHub's attestation, which roots trust in the platform hosting the public source and the workflow run logs directly, with no separate key-distribution problem. |

**Consequences**: `release.yml` gains a job-scoped `id-token: write` + `attestations: write` permissions block and two new steps: `Attest build provenance` (`actions/attest-build-provenance@v4`, run *after* `Create GitHub Release` so a Sigstore/attestations-API failure never costs a release itself — see the rejected "before release creation" placement below) covering the installer, `SHA256SUMS.txt`, and the raw app exe (`dist/OpenGardenPlanner/OpenGardenPlanner.exe` — the exact file Defender quarantined in #356, not just the installer wrapping it); and `Write release notes preamble`, which writes the checksum + `gh attestation verify` commands (installer and raw exe, with `--signer-workflow`) to a file that `Create GitHub Release` prepends to its auto-generated notes via `--notes-file`, so the trust signal is visible on the release page itself, not only in the README. `README.md` and `docs/07-deployment-view` §7.3 document the verification command alongside the existing checksum instructions, plus plain-language guidance on why SmartScreen/Defender may still warn (this ADR does not resolve that — only source provenance is proven, not code-signing reputation). §11.1/§11.2 updated to reflect the mechanism as a partial mitigation. No `FILE_VERSION` change. Test suite: `tests/unit/test_gate_commands.py::test_the_release_workflow_still_attests_build_provenance` pins six things review rounds actually caught regressing: the step's presence, a non-stale (or SHA-pinned-with-version-comment) action major (node24 arrived at v3.0.0 upstream, not v4 — v2 is exactly as broken as v1 and the guard's floor accounts for that), that it runs *after* `Create GitHub Release` rather than before, that the job grants `id-token`/`attestations` permissions, that `subject-path` covers the installer, `SHA256SUMS.txt`, and the raw app exe — bounded to the attest step's own block, not a fixed character window, so an unrelated later step mentioning the exe path can't make it pass vacuously — and that `--notes-file` still wires the preamble into the release. Mutation-tested against all four regressions the review found (v1, dropped raw-exe path, reordered before release creation, dropped permissions) — each independently fails the guard. Same discipline `test_the_release_workflow_still_runs_selftest` already applies to the neighboring frozen-exe selftest gate (#291's lesson: a release-critical step with no pin can silently degrade for releases at a time). The attestation's actual *output* (a verifiable Sigstore record) is still only exercisable by a real GitHub Actions run against `master`, per `ogp-validation-and-qa`'s evidence discipline — the pytest guard proves the step is wired correctly, not that Sigstore issuance succeeds. Manual fallback releases (docs/07 §7.3) cannot produce an attestation — GitHub's OIDC token is only available inside Actions — so a manually-built release ships checksum-only, same as before. Cross-refs: §11.1, §11.2, `ogp-external-positioning` §5, issue #356, issue #89.

**Rejected placement**: running `Attest build provenance` *before* `Create GitHub Release` (the original draft). Rejected in review: it put a never-yet-executed step, pinned to a since-discovered-stale action major, directly in the critical path ahead of the release — any Sigstore/Fulcio hiccup or transient attestations-API error would have failed the whole release, not just the provenance record. Attestation is keyed to the artifact's digest, not to the release, so ordering after release creation is free and strictly safer.

**Addendum (#358, 2026-09-22)**: Norton 360 flagged the v1.27.9 installer as `FileRepMalware[Misc]` — a second AV vendor hitting the same unsigned, zero-reputation PyInstaller profile this ADR already scoped (the only source changes between the clean-scanning v1.27.8 and v1.27.9 were the attestation workflow and the version bump, so the detection tracks a fresh hash, not new application behavior). This confirms the ADR's stated boundary: provenance attestation answers "was this built from the public source?" but deliberately does not answer "does the vendor's reputation engine trust it?" — releases remain unsigned (§11.1/§11.2). **Correction (#376, 2026-10-11):** the earlier claim that a paid certificate was the only fix is withdrawn. Signing options, including no-cost proposals raised after this decision, are being evaluated in [#375](https://github.com/cofade/open-garden-planner/issues/375); none has been adopted, and effectiveness against Defender ML and Norton FileRep remains unproven for this project. Operational path: false-positive submissions per vendor (Microsoft forms for #356, Norton portal `submissions.norton.com/reportfalsepositive` for #358). Both submission portals are CAPTCHA-protected (Norton: math challenge + reCAPTCHA; Symantec SymSubmit: reCAPTCHA v3), so these are human submissions — the maintainer cannot automate them, and neither can a script-kitted "auto-file our FPs" step be added to `release.yml` without bypassing anti-bot measures, which is out of scope. The reporter was additionally advised they can file from inside their own Norton quarantine UI, where their alert's Alert ID is available.

## ADR-044 addendum: the #375 decision — proposal rejected, Authenticode deferred, the Store adopted as a second channel (6 November 2026)

The evaluation #375 asked for is recorded in **ADR-073**, with every option in the issue's
table scored against its ten criteria and the evidence behind each score. In one paragraph:
the third-party cloud-signing proposal from #358 is rejected (publisher identity, shared
trust anchor, supply chain of the action); Azure Artifact Signing is not available to an
individual outside the USA/Canada; SignPath Foundation signs in its own name and stays
deferred; a Certum Open Source certificate (€49–69/year, the developer's own name,
non-exportable key) is the concrete shape of trigger 3; and the Microsoft Store is adopted as
a **second** distribution channel because a Store-distributed MSIX is signed by Microsoft and
never passes the browser download path where an unsigned, several-releases-a-day file can
never accumulate reputation. The rejected-alternatives row above now reads: "not the only
fix — see ADR-073"; §11.1 and §11.2 say "unfunded and evaluated; deferred, Store channel in
preparation". The GitHub installer stays unsigned and attested exactly as this ADR describes.

## ADR-044 addendum: the SBOM and third-party notices join the attested subjects (A2 #454, 13 October 2026)

**Status**: Accepted (2026-10-13).

**Decision.** Every release now publishes two inventory artifacts and attests them:

- `ogp-sbom.cdx.json` — a CycloneDX 1.5 SBOM listing every third-party Python
  distribution bundled into the build (name, version, `pkg:pypi/…` purl, license), and
- `THIRD_PARTY_NOTICES.md` — the same inventory as a human-readable notices file, also
  installed next to the GPLv3 `LICENSE` so the obligation survives installation.

Both are generated by `scripts/generate_distribution_inventory.py` **from the frozen
bundle's own `.dist-info` metadata** (the spec bundles the required runtime closure via
`installer/runtime_closure.py` and actual collected owners via `installer/frozen_inventory.py`),
never from a developer's environment or a historical
count. The generator fails closed: a bundled distribution with no discoverable license
fails the build rather than printing "UNKNOWN", and `--check` verifies the SBOM against the
bundle and each version against `pylock.toml`. Licenses are emitted as an SPDX `id` where
the metadata names one, an SPDX `expression` where it names a compound (`Apache-2.0 OR
BSD-3-Clause`), and a `name` only when the metadata is prose. The one mapping is
documented in `LICENSE_OVERRIDES`: the three Qt runtime wheels declare the prose "LGPL v3",
whose SPDX identifier is `LGPL-3.0-only`. Both files are added to the
`actions/attest-build-provenance` `subject-path` list, so provenance covers the inventory
the release publishes.

**What this does and does not prove.** A checksum proves *integrity*, an attestation proves
*source provenance*, and an SBOM declares *composition*; none of the three Authenticode-
signs the binary, and none suppresses SmartScreen/Defender/Norton detections (#356, #358,
[#375](https://github.com/cofade/open-garden-planner/issues/375)). The SBOM must not be
presented as a security guarantee; it is a machine-readable statement of what is inside.

**Consequences.** The frozen bundle grows by the bundled metadata — a dated measurement
(Windows, 2026-10-13) of 2.0 MiB of `*.dist-info` in a 610 MiB bundle (0.32 %), with the
LZMA installer at 169.4 MB — not a fixed property; re-measure on a release build. The
installer now also installs `LICENSE` itself, so "notices next to LICENSE" is true on disk
rather than only in the wizard. A new runtime dependency automatically appears in both
artifacts through the shared resolver, and `tests/unit/test_distribution_inventory.py`
pins the fail-closed behaviour and the drift between bundle, SBOM and lock.

**Review addendum (PR #490, 14 October 2026).** Requires-Dist is a minimum, not a
complete frozen inventory: PyInstaller also collected build/dev packages and setuptools'
vendored libraries. The original 47-component artifact omitted that code while its own
check passed. The spec now attributes actual Analysis pure modules, binaries, data and
runtime scripts through physical wheel RECORD paths. Nested vendored RECORDs take
precedence over their containing wheel. The bundle carries those exact metadata/license
files and `ogp-collected-distributions.json`, recording module/file ownership. Verification
reads the executable's PYZ independently and reconciles module names, owner identities and
collected file presence with the manifest and SBOM. Installed and vendored versions remain
distinct; a vendored version is verified through its containing wheel's locked version,
without a package-name exemption. Declared `License-File` entries must exist and their texts
must appear in the notices, including unusual filenames. The artifact-level regression
`test_frozen_hook_dependencies_are_in_the_inventory` was observed failing on the old build.
Synthetic metadata-only pipeline tests prove orchestration; they cannot establish frozen
code coverage. Collector tests pin nested ownership, both versions and refusal of unowned
wheel files. No runtime dependency, release permission or plan-format change.

## ADR-034 addendum: succession domain schema, determinism, and a SHARED season-segment fallback (US-D3.2, #331)

**Status**: Accepted (2026-10-01) | Adds `get_succession_plan` / `find_succession_gaps` / `suggest_succession` to the curated agent schema.

**Four season segments, not three — and the fallback belongs in the model.** Issue #331's own "verified repo facts" described the season segments as `spring` / `summer` / `fall`. The code has always had **four**: `early_spring`, `late_spring`, `summer`, `fall` (`SEASON_SEGMENTS` in `models/succession.py`, whose module docstring documents each boundary). An implementation written to the issue's prose would have mislabelled a third of the growing season; the issue's *acceptance criterion* ("labels matching `models/succession.py`'s own segment definitions - pinned against the documented formulas, not against a re-implementation") is the instruction that was followed instead. `test_agent_succession_domain.py` pins the four names and the inclusive-boundary behaviour: segments are contiguous and `date_to_segment` returns the **first** match, so a date exactly on the `early_spring`/`late_spring` boundary belongs to `early_spring`.

The second consequence is about **where** the no-location fallback lives. A plan with no geo-location has no frost dates, and the succession dialog already handled that with a private `_FALLBACK_BOUNDARIES` / `_fallback_segments` pair (calendar-month boundaries). Rather than copy that table into the agent layer — or, worse, return "segments unknown" and leave an agent unable to reason in seasons at all — the definition moved **into `models/succession.py`** as `compute_fallback_segments`, and both the dialog and `resolve_season_segments` call it. One definition, so a bed can never be segmented one way on screen and another way for an agent; the fallback is still reported honestly, via `coverage: "no_frost_dates"` **and** `segments_are_fallback: true`, alongside the fallback segments rather than instead of them. `resolve_season_segments(year, location) -> (segments, are_fallback)` is the single entry point both surfaces use.

**Degradation is a marker, never an empty list.** A bed with no plan reports `has_plan: false` — distinct from an empty plan, which reports `has_plan: true` with no entries, because "deliberately fallow" and "never planned" are different facts. A slot whose dates do not parse covers **nothing** in `find_succession_gaps`, so a malformed entry surfaces as a gap instead of reading as a full bed.

**Determinism is part of the contract, so every ordering ends in a stable tiebreak.** `suggest_succession` sorts on `(fits_window desc, days_to_maturity asc, species_key asc)`; the schema models, gap list and plan view are all built in `SEASON_SEGMENTS` order. No set or dict iteration order reaches the output. Two tests pin it: the ranking is identical when the candidate list is reversed, and identical when the same input is passed twice.

**`fits_window: false` is deliberately overloaded, and the docstring says so.** It means the crop is too slow for the gap **or** its days-to-maturity is unknown — the two are distinguishable via `days_to_maturity`. An unknown maturity is never reported as a fit, because an unfalsifiable "fits" is the same fabrication class as a fabricated spacing pass (ADR-045's honesty invariant). A too-slow candidate is still **returned**, ranked last, rather than dropped: silently omitting a considered candidate makes the answer unaccountable. `_effective_maturity_days` takes the **minimum** of `days_to_maturity_min`/`_max`, because the question is "can this crop finish before the next slot starts" and only a range's optimistic end answers it.

**Machine fields versus display strings.** `species_key`, `family`, `days_to_maturity` and `fits_window` are the English API contract and are what an agent branches on. `reasons[]` is **English and never localised** - ADR-033 makes MCP output an English contract - so it is documentation for a human reading the result and must not be parsed. (US-D3.3's question about *generated task titles*, which genuinely ARE translated at the generator because the GUI is their primary consumer, is a different problem and gets a different answer.)

**The two filter inputs are deliberately asymmetric.** The write tool's `species_key` is canonicalised (`.lower()`) both before the roster membership test and before storage, so a bundled plant's key is its scientific name and the persisted plan matches every other per-species surface - including the GUI dialog, which already stored a lowercased name. `suggest_succession`'s `candidates` instead goes through the case-insensitive `lookup_species`, exactly as `set_species` does, so `"Garlic"` is a valid candidate and an invalid `species_key`. An earlier version refused proper-case keys here while both sibling tools accepted them. The canonical key is derived with `models.plant_data.species_key()` (ADR-016) rather than read from a field — there is no `species_key` attribute on a species record, and deriving it a second way is how per-species state desyncs. For a bundled plant that key is the **scientific** name, because ADR-016 prefers `source_id -> scientific_name -> common_name`; `"beans"` is not a valid key, `"phaseolus vulgaris"` is.

No `FILE_VERSION` change: succession plans already serialise under the additive `succession_plans` key.

## ADR-036 addendum: the FIRST agent write into `ProjectData`, not the scene graph (US-D3.2, #331)

**Status**: Accepted (2026-10-01) | `set_succession_plan` is the first agent write that mutates project data rather than `QGraphicsScene`.

**Every prior agent write mutated the scene; this one mutates `ProjectManager`.** D2's tools (and D2.6's geometry escape hatches) all resolve a live Qt item and change it. Succession plans live on `ProjectManager.succession_plans`, a `bed_id -> dict` map in `ProjectData`. The interesting consequence is that **most of the invariants the scene-write path was built around simply do not apply**, and the ones that do apply arrive by a different route:

* **Nothing to preview.** There is no `prepareGeometryChange`, no badge, no `scene.changed` fan-out. The GUI's own dialog had to call `_refresh_succession_indicators()` explicitly after its command.
* **The agent path does NOT duplicate that call.** `succession_plans_changed` is already connected to `_on_succession_plans_changed` -> `_refresh_succession_indicators` in `application.py`, and `SetSuccessionPlanCommand.execute` calls `pm.set_succession_plan`, which emits it. Copying the dialog's explicit call would be a second refresh path for the same signal — the drift §8.19 warns about. This is asserted by a test rather than assumed, because "the badge updates for free via a signal chain wired in a different story" is exactly the kind of claim a green suite cannot see.
* **`geometry_apply.py` is irrelevant here.** There is no geometry. The one-undo-step contract is inherited from `CommandManager.execute` and nothing else.
* **The refusal contract matters more, not less.** With no scene to inspect, a half-applied write would leave a *stored plan* corrupted with nothing on screen to reveal it. So validation is complete **before** the command is constructed: unknown bed, non-soil-container target, overlapping ranges, non-ISO dates, `end_date < start_date`, unknown `species_key`, and a nonsensical year are all refused with `succession_plans` **and** the undo stack asserted untouched (the year guard included, which the MCP-level suite does not reach). A refused call must not half-apply — a test writes a good plan, then refuses an overlapping replacement, and asserts the good plan and the undo depth are both unchanged.

**Soil-capable, not merely plant-parent.** Succession planning attaches to a bed, so bed resolution uses `is_bed_type` (ADR-031's soil-capable set) rather than the looser `is_plant_parent_type` that `check_placement` uses. A TRELLIS is a plant parent that holds no soil, so it is refused. This is a deliberate difference from D3.1's `check_placement`, and it is commented at the resolution site so a later reader does not "harmonise" the two into one predicate.

**Rotation exclusion is two rules, and only one of them is reusable.** The acceptance criterion — never propose a species creating a crop-rotation conflict with an *earlier entry in the same bed* — cannot be met by calling `CropRotationService.check_plant_placement`. That method compares a candidate only against `records[0]`, the single most recent planting record (`crop_rotation_service.py:153`), so it cannot see "tomato after the garlic entry three slots ago"; and succession entries never enter rotation history at all, because only the Crop Rotation panel writes `PlantingRecord`s. So:

* the **cross-year** 3-year family cooldown is reused verbatim, via `CropRotationService.get_recommendation(bed_id).avoid_families`, which is already Qt-free and already feeds `get_diagnostics`;
* the **within-plan** rule is new logic, computed from the plan's own earlier entries and confined to one resolver, `_entry_species_names`, which reads `species_key` FIRST (`common_name` then `scientific_name` as fallbacks for a free-text slot). An earlier version preferred `common_name`, which the write tool never validates, so `{species_key: "solanum lycopersicum", common_name: "Cabbage"}` steered the filter at Brassicaceae and excluded the wrong family entirely.

Recording this rather than quietly writing a second family-cooldown implementation is the point: the alternative was a plausible-looking `check_plant_placement` call that would have silently passed every test while excluding almost nothing.

## ADR-036 addendum: agent writes ARE canvas-clamped — an off-plan staging capability is retired (issue #380)

**Status**: Accepted (2026-10-02) | The agent write path now clamps to the canvas, joining the GUI, and the earlier "stage an object just off-plan" design is deliberately retired.

**The asymmetry and why it was wrong.** The GUI clamps an object to the plan canvas — which spans `(0, 0)` to `(width, height)` in scene cm — in five places: interactive drag (`canvas_view._clamp_dragged_items_to_canvas`), arrow-key nudge (`_clamp_delta_to_canvas`), the properties panel's numeric X/Y, the mirror tool, and the resize handle. The agent path clamped nothing: `agent_api/creates.require_reachable_position` allowed **one full canvas of slack on every side**, and its docstring recorded the reason — so "an agent can stage an object just off-plan". Loose input beyond that (an object at `1e9`) was refused because it is invisible, unselectable and un-deletable through the GUI.

Two things made the original rationale untenable. First, the same slack applied to `move_object` and `set_object_position`, because all the clamping lives in the Qt view layer and `core/commands.py` contains none of it — so tightening only `create_object`, as the issue first framed it, would have missed the movement half entirely. Second, **nothing brings a stranded object back**: the GUI clamp touches only the items being moved, so an off-plan object is not pulled in by moving some other object, and there is no reconcile-on-load sweep. "Stage off-plan" therefore meant "hide it where the user cannot find it".

**Decision — option (c): clamp, and make the capability that remains discoverable.**

1. **One clamp rule, in one place.** New Qt-free `core/canvas_bounds.py` holds `clamp_shift_within_canvas`, `clamp_delta_within_canvas` and `rect_intersects_canvas` over plain `(left, top, right, bottom)` tuples. The GUI's `_clamp_items_to_canvas`/`_clamp_delta_to_canvas` were rewritten to call it, and the agent create/move paths call it too. This is the repo's standing "one canonical path, never a second one" rule: a second copy of the edge-selection rule would drift, and nothing would tell us when one stopped matching the other. A parity test drives a real `CanvasView._clamp_items_to_canvas` and asserts it produces the same shift as the shared function for the same rect.
2. **`create_object` clamps the whole creation group.** A HOUSE and its derived ROOF_RIDGE shift together, so they cannot be clamped apart. The clamp is applied in `application._do_agent_create_object` — not in `creates.py`, which stays Qt-free — where the live bounding rects exist.
3. **`move_object`/`set_object_position` clamp the moved group** — the item plus any contained plants it carries — in `_agent_apply_object_move`, so a move that would strand an object is trimmed to the canvas edge. `BackgroundImageItem` is exempt, matching the GUI (a background image is meant to extend past the plot).
4. **The gross-input guard stays.** `require_reachable_position` still refuses absurd coordinates and still leaves the scene **and** the undo stack untouched; it is now documented as the refuse-absurd guard, no longer as a staging allowance.
5. **A pre-existing off-plan object is made discoverable**, which neither clamping nor documentation can do on its own: `ObjectRef`/`ObjectDetail` gain `outside_canvas` (bounding-box based — true only when the box does not intersect the canvas at all; an empty canvas never flags, so a degenerate plan does not light up), and `get_diagnostics` gains an `outside_canvas` kind, produced by the existing `ProjectManager.diagnostics_snapshot` harvest rather than a new producer.

**Vertex writes are deliberately out of scope.** `set_vertex`/`add_vertex`/`delete_vertex` (D2.6) can also move geometry off-plan, and they are not among the GUI's five clamp sites. They are covered by the `outside_canvas` flag only. Widening the clamp to them would be new behaviour with no GUI precedent, so it is recorded here rather than done.

**Consequences.** FR-AGENT-26 records the contract; §11.4 records the reversal; the two existing unit tests that pinned the old "staging slack is reachable" reading were rewritten to pin the new one (accepted by the gross guard, then clamped by the caller). Every clamped write remains exactly one undo step, which the integration suite asserts over the real MCP transport. **A move whose delta the clamp erases entirely is REFUSED**, not executed as a no-op: without that, the tool ran a `MoveItemsCommand` that changed nothing and pushed a dead undo step — a Ctrl+Z that visibly does nothing (found in review). That matches the pre-existing unclamped no-op guard in `set_object_position`, and a test asserts the undo depth is unchanged.

## ADR-036 addendum: the rotation panel shows a succession plan as PLANNED, never as history (issue #378)

**Status**: Accepted (2026-10-02) | `CropRotationPanel` gains a display-only "Planned This Season" section; `CropRotationService` is untouched.

**The visible disagreement.** A bed can carry a succession plan (several planned crop slots in one season) and show a succession badge on the canvas, while the crop rotation panel beside it reports "no planting history — every crop is suitable" and the bed's rotation indicator stays unset. The two features are independent by construction: `ProjectData.succession_plans` is what is *planned*, `ProjectData.crop_rotation` is what was *grown*, and only the Crop Rotation panel's "Add Planting Record…" button writes the latter. Nothing is broken — but an agent that has just been told, by `suggest_succession`, to exclude a crop for rotation reasons gives an answer the panel next to it cannot explain, which is the least useful place to stop.

The issue listed three options. **Option 1 is taken**: the panel reads the plan directly and shows it as a separate, clearly-labelled section, with each planned crop's botanical family and an explicit note that these are planned, not history. When a plan exists and no history does, the recommendation text names the gap — "the rotation advice cannot see this bed's planned crops" — instead of a bare "every crop is suitable".

**Option 2 is rejected, and the rejection is the load-bearing part.** Feeding the plan into `CropRotationService.get_recommendation` (or `check_plant_placement`) would change the **3-year cross-year cooldown semantics for every caller**, because the service would begin treating planned crops as grown ones. That is a silent behaviour change to a shared service to fix a display problem. The plan therefore never enters the service, and a test asserts `get_recommendation` returns identical `status`/`suggested_demand`/`avoid_families` before and after a plan is present.

**The panel refreshes from the existing signal.** It connects to `ProjectManager.succession_plans_changed` — the same signal the canvas badge chain already uses — rather than polling or duplicating a refresh call, so a plan set through the GUI dialog or an agent's `set_succession_plan` updates the section live. An unresolvable `species_key` (e.g. an API-imported species with no bundled record) still lists its row with "family unknown" rather than being dropped.

**Consequences.** FR and §8 docs updated; the ADR-036 US-D3.2 addendum's `suggest_succession` exclusions are now explainable from the GUI, which satisfies the stronger branch of the issue's acceptance criteria. No `FILE_VERSION` change.


## Addendum — in-app release checksum verification (A1, #453, 2026-10-13)

An immutable release descriptor carries the exact tag, expected installer basename,
asset size and `SHA256SUMS.txt` URL through the checker, application and update bar.
Missing, duplicate, wrong-release or unsafe assets disable in-app installation while
preserving the manual release link. Downloads begin on the exact repository/tag
GitHub HTTPS path; every redirect and final response must remain on an exact HTTPS
GitHub asset host (`github.com`, `release-assets.githubusercontent.com` or
`objects.githubusercontent.com`), with at most five hops.

The manifest is bounded to 64 KiB and must contain exactly one valid matching
SHA-256 basename. Installer bytes are streamed in 64 KiB chunks, bounded by and
matched to the release asset size, hashed and finalized only after verification.
Cancellation/failure produces no launch and removes partial files. A typed verified
result is rechecked immediately before process launch. Signed query strings and
raw network exceptions never enter user-facing failures.

This validates integrity against the release manifest over permitted HTTPS origins.
It does not independently verify build provenance, add Authenticode signing, change
the release workflow or establish any effect on antivirus reputation. Attestation
verification and signing evaluation remain their existing separate processes.
