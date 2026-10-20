# Pitfalls: agent API, MCP and security

Standing rules for this area, one entry each. The heading is the rule. Pins and sources are listed under each entry. Index: [§11.4](../README.md#114-known-development-pitfalls).

### PF-API-01


- **Rule:** A CLI's SUCCESS output needs the same treatment as its failure output.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** pointer → [§8: 8.19 Agent API — Embedded MCP Server & Thread Marshaling (US-D1.1–D1.6, D2.0–D2.6, D3.1–D3.4, ADR-033/034/](../../08-crosscutting-concepts/README.md#819-agent-api--embedded-mcp-server--thread-marshaling-us-d11d16-d20d26-d31d34-adr-033034035036)
- **Legacy:** README L183

Held in [§8: 8.19 Agent API — Embedded MCP Server & Thread Marshaling (US-D1.1–D1.6, D2.0–D2.6, D3.1–D3.4, ADR-033/034/](../../08-crosscutting-concepts/README.md#819-agent-api--embedded-mcp-server--thread-marshaling-us-d11d16-d20d26-d31d34-adr-033034035036). The entry keeps the rule and its pin; the account is in the link.

### PF-API-02


- **Rule:** An INDETERMINATE answer must never select the more DANGEROUS option.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** pointer → [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16)
- **Legacy:** README L185

Held in [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16). The entry keeps the rule and its pin; the account is in the link.

### PF-API-03

- **Rule:** "Unparseable" and "empty" are different failures, and only one of them is dangerous.
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #366
- **Status:** standing
- **Legacy:** README L186

- **"Unparseable" and "empty" are different failures, and only one of them is dangerous.** (Issue #366, the owner's manual test): the onboarding merge's fail-closed rule is "an unreadable file we don't own is left byte-for-byte untouched". The owner's `~/.gemini/config/mcp_config.json` was **0 bytes** — which is what several clients ship before their first MCP server — and the merge reported `Could not read existing … (Expecting value: line 1 column 1 (char 0)); left untouched`. That message is `json.loads("")`. So a fail-closed rule written as "if we cannot use it, do not touch it" quietly answers a question the safety rule never asked: it protects *content*, and a 0-byte file provably has none. The general shape: **a guard phrased around the parser's opinion of the file inherits every quirk of that parser, including its opinion of an empty one.** The fix is a positive notion of emptiness (`_is_effectively_empty`) applied *before* parsing, in both the JSON/JSONC and TOML paths, and it must be applied under the STRICT `replace_on_parse_error=False` policy — otherwise "we protect your file" still quietly excludes "a file you have not written yet". The companion test asserts one byte of junk still fails closed, because the distinction that matters is empty vs corrupt, not lenient vs strict.

### PF-API-04

- **Rule:** A refusal nobody asked for is a capability removal wearing a safety hat.
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #366
- **Status:** standing
- **Legacy:** README L187

- **A refusal nobody asked for is a capability removal wearing a safety hat.** (Issue #366, same manual test, and a decision reversal recorded in ADR-035): a too-old client CLI was made to refuse rather than be handled, on the reasoning that its flags and config shape were unverified. The consequence was not a clear error — it was `install_method="manual"`, so **the Add button silently disappeared from the dialog**, and the owner reported the button missing. The refusal was also unnecessary: running the older binary against a throwaway config showed it writes the *user* config when the newer flag is absent, i.e. the fallback was not merely tolerable but correct. Three lessons. (1) **When a guard changes what the UI offers, check what the UI now offers** — a refusal that demotes a control to a snippet is a feature removal, and it will be reported as "the button is missing" rather than as the error it actually is. (2) **The blast radius of a safety decision is wider than the code it guards**: one `install_method` value moved a button. (3) **A CLI's config shape can differ between generations, not just its flags** — 1.18.x stores servers flat as `mcp.<name>` where 2.x nests them, so supporting both generations means the *reader* must accept both too, or it reports a working registration as absent. The manual snippet must follow the installed generation for the same reason: a snippet in the wrong shape is silently ignored, which reads as "OGP is broken".

### PF-API-05


- **Rule:** Verify the installed binary's CAPABILITY, not the product's documented interface — and check that a stub cannot stand in for a real binary.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** pointer → [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16)
- **Legacy:** README L189

Held in [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16). The entry keeps the rule and its pin; the account is in the link.

### PF-API-06


- **Rule:** A refusal must leave the filesystem exactly as it found it — so take the backup as late as possible.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** pointer → [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16)
- **Legacy:** README L191

Held in [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16). The entry keeps the rule and its pin; the account is in the link.

### PF-API-07


- **Rule:** "Unparseable" and "parseable but the wrong shape" are different failures and must not share a policy.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** pointer → [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16)
- **Legacy:** README L192

Held in [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16). The entry keeps the rule and its pin; the account is in the link.

### PF-API-08


- **Rule:** A "best-effort, never raises" reader must own its failure type — and, more importantly, must not enumerate.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** pointer → [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16)
- **Legacy:** README L193

Held in [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16). The entry keeps the rule and its pin; the account is in the link.

### PF-API-09


- **Rule:** A guard checked on some paths is not a guard.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** pointer → [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16)
- **Legacy:** README L194

Held in [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16). The entry keeps the rule and its pin; the account is in the link.

### PF-API-10


- **Rule:** A required dataclass field is a contract with an explicit consumer list, not a struct you can extend freely.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #277, #291, #365
- **Status:** pointer → [ADR: ADR-038 addendum: issue #277 — the release shipped a mismatched Qt micro (post-mortem)](../../09-architecture-decisions/README.md#adr-038-addendum-issue-277--the-release-shipped-a-mismatched-qt-micro-post-mortem)
- **Legacy:** README L195

Held in [ADR: ADR-038 addendum: issue #277 — the release shipped a mismatched Qt micro (post-mortem)](../../09-architecture-decisions/README.md#adr-038-addendum-issue-277--the-release-shipped-a-mismatched-qt-micro-post-mortem). The entry keeps the rule and its pin; the account is in the link.

### PF-API-11


- **Rule:** A tool's declared return model is part of its contract, and testing the provider is not the same as testing the tool.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #365
- **Status:** pointer → [ADR: Addendum (US-D3.3 + US-D3.4 — the D3 localisation convention)](../../09-architecture-decisions/README.md#addendum-us-d33--us-d34--the-d3-localisation-convention)
- **Legacy:** README L197

Held in [ADR: Addendum (US-D3.3 + US-D3.4 — the D3 localisation convention)](../../09-architecture-decisions/README.md#addendum-us-d33--us-d34--the-d3-localisation-convention). The entry keeps the rule and its pin; the account is in the link.

### PF-API-12


- **Rule:** A third-party config file is a *superset* of the format you assume, and fail-closed turns that into a dead end.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** pointer → [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16)
- **Legacy:** README L198

Held in [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16). The entry keeps the rule and its pin; the account is in the link.

### PF-API-13


- **Rule:** Never re-serialise a file you do not own.
- **Pinned by:** none — pending Phase 3 review
- **Source:** #366
- **Status:** pointer → [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16)
- **Legacy:** README L199

Held in [ADR: ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)](../../09-architecture-decisions/README.md#adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16). The entry keeps the rule and its pin; the account is in the link.

### PF-API-14

- **Rule:** A CLI's default scope can write into the user's project directory.
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #366
- **Status:** standing
- **Legacy:** README L200

- **A CLI's default scope can write into the user's project directory.** (Issue #366): `opencode mcp add` writes the **project** config unless `--global` is passed. Omitting the flag does not fail — it silently drops an `opencode.json` into whatever directory the user happened to be in, and the registration appears to work while applying to nothing. Verify a CLI's flags by *running* `--help` (this one was verified by running it), and pin any scope/flag that is load-bearing with a test asserting its presence in the argv.

### PF-API-15


- **Rule:** At a trust boundary that ingests untrusted files, catch `Exception` at the ingestion seam — do NOT enumerate exception families
- **Pinned by:** `tests/unit/test_smart_symbol_library.py`
- **Source:** #236
- **Status:** pointer → [ogp-failure-archaeology: Index — scan this first](../../../.claude/skills/ogp-failure-archaeology/SKILL.md#index--scan-this-first)
- **Legacy:** README L244

Held in [ogp-failure-archaeology: Index — scan this first](../../../.claude/skills/ogp-failure-archaeology/SKILL.md#index--scan-this-first). The entry keeps the rule and its pin; the account is in the link.

### PF-API-16

- **Rule:** Agent API described the compass backwards (issue #267, fixed)
- **Pinned by:** none — the tests this narrative names are cited in the archive (see Status); pending review
- **Source:** #267
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l282-agent-api-described-the-compass-backwards-issue-267-fixed)
- **Legacy:** README L282

### PF-API-17


- **Rule:** **Agent creation must share the loader's construction path and its undo
- **Pinned by:** none — pending Phase 3 review
- **Source:** #329
- **Status:** pointer → [ADR: Addendum (US-D3.3 + US-D3.4 — the D3 localisation convention)](../../09-architecture-decisions/README.md#addendum-us-d33--us-d34--the-d3-localisation-convention)
- **Legacy:** README L442

Held in [ADR: Addendum (US-D3.3 + US-D3.4 — the D3 localisation convention)](../../09-architecture-decisions/README.md#addendum-us-d33--us-d34--the-d3-localisation-convention). The entry keeps the rule and its pin; the account is in the link.

### PF-API-18

- **Rule:** A stable geometry API must read live transforms, and a constrained write must refuse rather than half-run the solver
- **Pinned by:** `tests/integration/test_agent_api_geometry.py::test_rotated_polygon_geometry_is_live_scene_space_and_round_trips_exactly`; `tests/integration/test_agent_api_writes.py::test_constrained_geometry_read_succeeds_but_every_d26_write_refuses`
- **Source:** #330
- **Status:** standing
- **Legacy:** README L464

**A stable geometry API must read live transforms, and a constrained write must refuse rather than half-run the solver** (US-D2.6, #330, 2026-09-25): the tempting shortcut was to reuse `get_object(raw=True)` and the serializer's polygon points. That is wrong for an edit contract — serializer points are pre-rotation storage, while the agent needs the vertices' current scene positions; at 215° the two frames visibly diverge. The inverse shortcut is equally subtle: `mapToScene` followed by `mapFromScene` moved a rotated polyline by about `5.7e-14 cm`, enough to make an unchanged request look like a real mutation even though the drift was invisible. `ui/canvas/geometry_inspect.py` therefore maps live vertices with `mapToScene`, and `geometry_apply.local_vertex_for_scene` reuses the exact local `QPointF` for an unchanged request within `1e-9 cm`. `set_vertex` then refuses that unchanged request as a no-op before any command is built, so the read/write pair cannot pollute history. The second trap is policy: the live constraint solver can move several connected items, so a one-shot agent tool that moved only the addressed object would silently violate intent. `_agent_require_unconstrained` now refuses every geometry write with the blocking constraint type/UUID, while unauthenticated `get_geometry` lists those constraints. Refusals happen before command execution, so scene, graph, history, and dirty state stay untouched. Pinned by `tests/integration/test_agent_api_geometry.py::test_rotated_polygon_geometry_is_live_scene_space_and_round_trips_exactly`, `tests/integration/test_agent_api_writes.py::test_constrained_geometry_read_succeeds_but_every_d26_write_refuses`, and the default-on orchestration tests. Lesson: for geometry APIs, document and test the coordinate frame at the transform boundary; for multi-item solvers, a refusal with an inspectable reason is safer than a partial mutation.

### PF-API-19

- **Rule:** Three guards in the wrong place (US-D3.2 final pre-merge review, #374)
- **Pinned by:** `tests/unit/test_agent_succession_review_fixes.py`
- **Source:** #366, #374
- **Status:** standing
- **Legacy:** README L519 (legacy 11.4.1)

The `set_succession_plan` work passed 6635 tests, an out-of-process dogfood
harness, and a real manual test in the built exe. The final review still found
three defects, and all three are the same mistake: **a guard that sits at the
wrong boundary**. Each one was fixed and pinned by
`tests/unit/test_agent_succession_review_fixes.py` (21 tests, each failing
against the pre-fix code).

1. **A guard around the parse does not cover the parse's consequences.**
   `PlantingRecord.from_dict` does `data["year"]` and never type-checks, so a
   `.ogp` carrying `{"year": "2025"}` produced a record whose `year` was the
   *string* `"2025"`. Both readers caught four enumerated exception types around
   the `from_dict` call - and the row sailed through, because nothing had thrown
   *yet*. The `TypeError` arrived later, inside `get_records_for_area`'s sort:
   outside the loop the guard was protecting, and inside a Qt signal handler
   whose own handler catches only `RuntimeError`. That is an uncaught exception
   in the event loop, the `qFatal()`/abort shape #366 recorded. **Enumerating
   exception types at an ingestion seam is a guess about a parser you do not
   control; catch broadly (invariant 14: a `.ogp` is untrusted input) AND
   validate the field you actually depend on** - here
   `_read_crop_rotation_record` in `app/application.py` catches `Exception` and
   requires `isinstance(rec.year, int)`. A list year, a `None` year and a
   missing year are now all dropped instead of detonating later.

2. **Re-resolving a name through the bundled DB silently drops every
   non-bundled species.** The write validator collected species *names* from the
   bundled database plus the plants placed on the canvas, then pushed all of
   them back through `lookup_species` to get keys. A Permapeople or custom
   species has no bundled record, so it resolved to `None` and was skipped: the
   roster missed every custom plant, and `set_succession_plan` refused a species
   the app had just shown the agent - while the sibling tool `set_species`
   accepted it. **Three agent tools disagreeing about one plant is a worse
   failure than any one of them being wrong**, and it was invisible because
   every bundled species worked. The validator now derives keys directly,
   `_agent_known_species_keys()` calling `species_key(dict)` (ADR-016) on the
   plant's own `metadata["plant_species"]`, never a round trip through the
   bundled index. Same class as the `species_key` corollary above: **derive the
   key; do not resolve a name back to the thing you already had.**

3. **A stored object that holds one year must not answer a question about
   another year.** `get_succession_plan(bed_id, year=2027)` on a bed holding a
   2026 plan returned `has_plan: true`, 2026 entry dates, and `season: null` on
   every entry - because the season is derived from the requested year and the
   dates are not. `null` reads as a data fault, not as "that is next year's
   question", so the agent had no way to tell a mismatch from corruption. The
   view now reports `has_plan: false` and carries a `plan_year` field naming the
   year the bed actually has. **When a store is keyed by a dimension the caller
   supplies, an explicit parameter that does not match the store is a miss, not
   a hint to return the wrong row** - and the miss must be legible in the
   response shape.

The common thread: each guard was written where the *code* was, not where the
*trust boundary* or the *key space* is. Review found all three; the suite and the
dogfood harness found none of them.

### PF-API-20

- **Rule:** Six defects a single package found, and what each one was really about (US-D3.3 #332 + US-D3.4 #333)
- **Pinned by:** none — the tests this narrative names are cited in the archive (see Status); pending review
- **Source:** #332, #333
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l737-six-defects-a-single-package-found-and-what-each-one-was-really-about-us-d33-332--us-d34-333)
- **Legacy:** README L737 (legacy 11.4.3)

### PF-API-21

- **Rule:** Review and frozen-client findings in D3.3/D3.4 (#332/#333)
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #332, #333
- **Status:** standing
- **Legacy:** README L820 (legacy 11.4.4)

- **Call the public tool with the production provider graph.** The first
  handover reported 6951 passing tests, but a real MCP client against the frozen
  exe found `get_soil_status` failing with six missing model fields,
  `get_soil_mismatches` failing with missing `total`, and the soil prompt failing
  likewise. Providers returned aggregate `beds` envelopes while the server
  constructed single-bed models. The purported real-client suite only called
  provider methods and prompt renderers directly. Explicit aggregate schemas
  now preserve per-bed coverage; the prompt extracts its requested bed.
  `TestRealMcpTransport` in `tests/integration/test_agent_task_soil_tools.py`
  calls all nine tools and both prompts using `app._build_agent_providers()`.
  Four status/prompt tests and a separate mismatch test were observed failing
  before the fix. Stub registration and direct provider success are evidence
  about different boundaries.
- **Generate a requested period before applying urgency.** A plant with April
  sowing and June/July harvest returned an empty, fully-covered annual calendar
  when queried in October. Future years were also empty because `year` never
  reached generation. `actionable_only=False` retains the schedule for agent
  annual/explicit-window reads while GUI reminders keep their existing default.
  A December-to-January task was dropped from both years; intervals are now
  clipped to year boundaries. Pinned by
  `test_calendar_generates_the_full_requested_year`,
  `test_explicit_task_window_generates_its_calendar_tasks` and
  `test_calendar_clips_cross_year_tasks`, all observed failing first. Propagation
  was absent because no plans were supplied to its generator. The extracted
  `build_propagation_plans` is now shared with the GUI and honors seed data and
  user overrides; `test_propagation_tasks_use_the_gui_calculator` failed for both
  current and future years before the fix.
- **Provenance and staleness must follow the same selected record.** An old
  global test was reported with `record_source=global` and
  `is_test_overdue=false` because staleness checked the bed's empty history.
  The service now resolves record/source/history together, and the existing
  record-only method delegates to it. Pinned by
  `test_global_fallback_uses_global_history_for_staleness` (failed first).
- **Language and input types must be checked at the actual boundary.** A
  German amendment test pinned English names, contrary to the API contract.
  Recommendation names now use the existing `Amendment.display_name(language)`;
  `test_amendment_names_follow_the_ui_language` failed first with English
  `Dolomite lime`/`Compost` versus `Dolomitkalk`/`Kompost`. MCP's permissive
  numeric validation also converted booleans and numeric strings into soil
  readings before the stricter domain validator saw them. Strict numeric
  annotations prevent that; three malformed-input transport cases failed first.
  The translator unit test now requests `qtbot`: it previously depended on an
  unrelated test creating QApplication, so a targeted run failed while the full
  run passed.

- **The requested year is not necessarily a task's frost-anchor year.** Round
  two reproduced bundled garlic sowing on October 15–29, 2026 only when the
  request extended into 2027. Bundled asparagus harvest uses offsets 104–156
  weeks, so a 2026 calendar must also consider prior anchors. Period generation
  now derives an anchor range from the actual calendar and propagation offsets,
  filters overlapping dates and preserves canonical anchor-year IDs. Annual
  calendars and task windows share this path. Both the garlic integration test
  and `test_bundled_multiyear_harvest_includes_prior_frost_anchors` failed first.
- **No recommendation is not a soil-health assessment.** An existing lab-only
  record (`n_ppm=100`, no kit levels) correctly returned unknown health and no
  amendments, yet the prompt claimed every measured value was near target.
  Neutral prompt/tool prose now states the engine's limited conclusion and
  names the unconverted lab readings. The real-client
  `test_lab_only_reading_is_not_presented_as_near_target` failed first.
- **Absolute dates need an absolute identity.** Wider frost-anchor generation
  reapplied a saved March 10 propagation override for every anchor, making three
  tasks in an annual read and five in a three-year read. The dates agreed but
  anchor-year IDs differed, so deduplication failed. The shared propagation
  generator now assigns overridden steps to their start-date year; relative
  steps retain anchor-year IDs. GUI and agent therefore agree.
  `test_absolute_propagation_override_has_one_shared_identity` failed first and
  checks identity, one result, GUI convergence and annual month counts.

### PF-API-22

- **Rule:** A product surface can be "protected" by a library default nobody pinned.
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L1086

- **A product surface can be "protected" by a library default nobody pinned.** Symptom: the Agent API's only barrier against a web page reaching it through DNS rebinding was the mcp SDK's Host/Origin validation, and the declared floor (`mcp>=1.12`) admitted SDKs that leave it **off** — measured: on 1.22.0 a crafted `Host: evil.example` initialize returned HTTP 200 with a full MCP result, where the 1.30.0 wheel answers 421. No shipped exe was known to be exposed, because every release happened to bundle a 1.30-era wheel. Root cause: the property belonged to *whichever wheel resolved at build time*, not to the product. Fix: `build_server` now takes the host/port it binds and passes explicit `TransportSecuritySettings`, and the floor rises to `mcp>=1.23`. The instructive part is the test design: with mcp 1.30.0 installed, the black-box 421/403 tests **pass even with our settings deleted** (measured). So does a naive object-level assertion that the settings are not None and the flag is True — the SDK auto-enable returns exactly such an object. What actually detects the removal is asserting something the default cannot satisfy: that `allowed_hosts` names the **bound port** and that no entry is a wildcard. Measured: deleting the `transport_security=` argument fails 3 of the 4 object-level tests. *A test that passes because of a library default is not testing your code; assert the configuration object as well as the behaviour it produces.*
