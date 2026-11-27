---
id: ADR-078
title: "A unit preference over the centimetre model"
status: "Shipped in v1.40.0; owner confirmed manual acceptance (issue #673; discussion #671, with defaults informed by @ciru-chan). Partly superseded by ADR-081 (#907): the display preference is per quantity."
refs: ["#673"]
legacy_anchor: adr-078-a-unit-preference-over-the-centimetre-model-issue-673
---

# ADR-078: A unit preference over the centimetre model

**Status**: Shipped in v1.40.0; owner confirmed manual acceptance (issue #673; discussion #671, with defaults informed by @ciru-chan). Partly superseded by ADR-081 (#907): the display preference is per quantity.

**Context**: US gardeners read seed packets, plants and site dimensions in different native units. Converting the model would break geometry, constraints, saved plans and clients. The issue's November 8 survey predates ADR-077's locale formatting and the shipped #782 PDF scale-bar correction; both remain in effect.

**Decision**:

1. **Global display preference.** `units/system` in AppSettings defaults to Metric; unknown settings normalize to Metric. `UnitPreference` holds the process value and `UnitsNotifier` adapts its plain channel to a Qt signal. Application startup applies it before building widgets; saving Preferences updates the existing document's displays. No new plan key, migration or FILE_VERSION bump.
2. **Pure conversion, localized presentation.** `core/units.py` imports only the standard library. `UnitSystem`, values, styles, numeric-format callbacks and the decimal mark are explicit arguments. `measurement_display` passes the active preference and the UI locale to these functions. Existing fixed-decimal UI paths retain Qt's rounding through `format_decimal`; whole-number shopping plant summaries retain their prior Python rounding. Paired vertex coordinates retain their common metric unit and precision, or show two imperial lengths. Legacy `measurements` exports are aliases, preserving import compatibility without duplicate format definitions. The AST guard includes units after a closing coordinate parenthesis and prevents new inline measurement formats; precipitation and SVG's machine-readable physical-unit XML are documented exceptions.
3. **Notation follows the quantity.** Layout uses feet plus eighth-inches from twelve rounded inches; smaller lengths use fractional inches. Half-up rounding of the absolute value handles carry and negative zero. Plant size uses whole inches, depth eighth-inches without feet, area switches from in² to ft² at one square foot, and real litres use US qt below one US gallon and gal above. Nominal pot classes are names, never converted volumes. The fraction denominator is configurable through the pure formatter API (default 8).
4. **Metric styles retain their established precision.** AUTO switches from one-decimal cm to two-decimal m at 100 cm; METRES always uses two-decimal m; CENTIMETRES one-decimal cm; COORDINATE two-decimal cm; RULER compact cm/m; SCALE_BAR compact cm/m/km; PLANT_SIZE whole cm; DEPTH retains the given value's precision; FEET uses whole m for elevation. PLANT_METRES preserves the plant-search panel's one-decimal metres, with whole-inch imperial output. Decimal marks follow ADR-077 in either system.
5. **Values and edits keep their original unit.** `LengthSpinBox.value`, ranges and signals stay cm, or metres where explicitly configured; `VolumeSpinBox` stays litres. Metric delegates to Qt's existing formatting and steps. Imperial keeps twelve internal decimal places and an exact-value shadow, accepts explicit metric/imperial units and either decimal mark, and commits edited text on acceptance. Reinterpreting an unchanged rounded readout returns its exact value. A signal-blocked switch restores that value; it creates no command. Steps select the nearest native increment in log distance (ties smaller), with whole-inch plant steps and eighth-inch depth steps. Bare imperial numbers mean inches; a metre-valued field reads bare numbers as feet. The grid is one foot, fine nudge one quarter-inch.
6. **One syntax boundary for coordinates.** The coordinate bar accepts bare active units and attached `mm/cm/m/in/ft` suffixes. Its angle is always degrees. Compound feet/inches notation belongs to spin boxes and calibration, because whitespace separates coordinate fields. Existing Y-axis semantics are unchanged.
7. **Reports keep their meaning.** Scale bars choose native round distances and draw their exact length, preserving #782's correction. PDF plant positions follow the display preference. Soil and mulch use distinct `soil_fill:ft3` / `mulch:ft2` price identities, so a stored metric price is never applied to an imperial quantity. Save-time pruning retains both native price records while their material remains in the list; switching display units must not erase the alternate price.

**Intentional metric text changes**: resize tooltips gain a space before their unit; canvas-size messages and export/print descriptions use AUTO precision and a unit beside each dimension; 3D focus/keyframe descriptions use AUTO precision. Explicit unit tokens in the coordinate bar are additive. The issue's proposed fifth change, correcting a clamped PDF scale bar (#782), was already shipped and is preserved.

**Alternatives considered**:
- *Convert geometry or Agent API parameters.* Rejected: presentation must not change what a plan means.
- *Per-plan units.* Deferred until requested; a second persisted preference is unnecessary for v1.
- *Read the global preference in pure formatters.* Rejected: explicit arguments make conversions deterministic and reusable.
- *Use the issue's original 3 ft switch and fractions for plant sizes.* Superseded by the horticultural feedback in #671.
- *Force English decimal marks to keep the pure module Qt-free.* Rejected: the explicit decimal-mark argument and thin adapter preserve the later locale contract.

**Consequences**: No dependency or file-format change. Metric remains the default. ADR-081 extends the preference to temperature, precipitation, harvest mass and Canada (mixed), one system per quantity; DXF unit selection and per-plan overrides are deferred. Tests: `test_units.py`, `test_unit_preference.py`, `test_unit_spin_box.py`, `test_units_surfaces.py`, `test_unit_dialogs.py`, `test_unit_reports.py`, `test_units_guard.py`, `test_coordinate_units.py` and the save/reopen workflow in `tests/integration/test_unit_system.py`. FR-MEAS-07; §8.9.19.
