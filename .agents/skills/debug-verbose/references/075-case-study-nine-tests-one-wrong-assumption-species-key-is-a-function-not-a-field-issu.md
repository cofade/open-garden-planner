## Case study: nine tests, one wrong assumption - `species_key` is a function, not a field (issue #331, fixed 2026-10-01)

**Symptom**: Adding `suggest_succession` to the Agent API (US-D3.2). Nine unit tests in
`tests/unit/test_agent_succession_domain.py` failed, and they failed *identically* - several
returning an empty list where a ranked candidate list was expected, others raising `KeyError` on a
species key that had been returned by the function under test a moment earlier.

**Wrong theories, in order**. (1) That the family-exclusion filter was too aggressive and was
discarding everything - plausible, because three of the failures were exactly "expected 3 species,
got 0", and `within_plan_families` was the newest input. (2) That the window-fit arithmetic was
wrong (`fits_window` was `False` in two cases). (3) That `PlantSpeciesData` simply had no
`family` populated, since `_species()` built the records by hand and `family` came back empty.
Each of these would have justified a "fix" that changed the filter, the date maths, or the test
fixture. All three were wrong, and theories (1) and (3) were actively misleading: the filter was
never reached, because the candidate loop skipped every record before reaching it.

**Key evidence**: two `KeyError`s that were decisive. A test asserted `by_key["beans"]` after
`by_key` had been built from the function's own output - so the key `beans` had to be in the input
somewhere. It was not. Following it into `_species()` showed the fixture setting
`scientific_name`/`common_name` but never a `species_key` field, and
`suggest_succession_for_agent` deriving its key with `getattr(record, "species_key", "")`. That
attribute does not exist: `species_key(species_dict)` is a **module-level function** in
`models/plant_data.py` (ADR-016). `getattr` returned `""` for all 118 bundled species, the
`if not key: continue` guard skipped every one, and the function returned `[]`. Nine symptoms, one
assumption.

**Two further facts surfaced only after that was fixed**, and both would have broken the story in
production rather than in tests. (a) ADR-016's priority is `source_id -> scientific_name ->
common_name`, so a bundled plant's canonical key is its **scientific** name: `"phaseolus
vulgaris"`, never `"beans"`. The first integration run failed with
`Unknown species_key 'beans'`, having already passed every unit test. (b) `WriteResult` has no
`message`/`undo_step` fields - it has `action: Literal[...]` and `undo_description: str` - so the
write tool's return value failed pydantic validation with `2 validation errors`. Both were caught
only because the integration test wired a **real** command instead of a stub.

**Root cause**: a `getattr` with a default, used to read a field that had been imagined. The
default made the bug silent - no `AttributeError`, just an empty result that reads as a legitimate
answer ("this bed has no suitable crops") rather than a crash.

**Fix**: Derive the key with `species_key(record)` inside the domain function, and change the
contract from "species objects" to "raw species dicts" so the canonical derivation is the only
path. Also switched the schema's `species_key` derivation and the test fixtures to real scientific
names, and corrected the `WriteResult` construction in both `application.py` and the test.

**Lesson**: (1) When many tests fail the *same* way, hunt the shared assumption before fixing any
of them - three theories in this case each pointed at a different function, and none was the cause.
(2) `getattr(obj, "field", default)` converts a missing-attribute bug into a silent empty result;
prefer an explicit lookup so a renamed or non-existent field fails loudly. (3) Verify the
*constructor* of any shared result schema before building on it - `WriteResult` had accumulated
required fields, and a unit test with a stub could never have noticed. (4) An integration test
built from stubs proves the transport and nothing else; the three defects above were all invisible
to unit tests and all visible the moment a real `CommandManager` and real schema were used.


