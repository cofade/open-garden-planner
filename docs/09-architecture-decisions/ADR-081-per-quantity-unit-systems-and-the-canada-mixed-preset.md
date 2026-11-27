---
id: ADR-081
title: "Per-quantity unit systems and the Canada (mixed) preset"
status: "Shipped in v1.41.0 after owner acceptance (issue #907; [PR #989](https://github.com/cofade/open-garden-planner/pull/989))."
refs: ["#907"]
legacy_anchor: adr-081-per-quantity-unit-systems-and-the-canada-mixed-preset-issue-907
---

# ADR-081: Per-quantity unit systems and the Canada (mixed) preset

**Status**: Shipped in v1.41.0 after owner acceptance (issue #907; [PR #989](https://github.com/cofade/open-garden-planner/pull/989)).

**Context**: ADR-078 shipped one Metric/Imperial choice over the centimetre model. That
choice covered layout lengths, areas and container volumes; temperature, precipitation
and harvest mass stayed metric, and a Canadian gardener could not have feet for beds and
degrees Celsius for the weather at the same time. Issue #907 asked for a per-quantity
profile and a Canadian mixed preset, while keeping the centimetre geometry model, the
Agent API units and every saved file unchanged.

**Decision**:
1. **One immutable profile, six quantities.** `core/unit_preference.py` defines
   `Quantity` (length, area, volume, temperature, precipitation, mass) and a frozen
   `UnitProfile` mapping each to `UnitSystem`. `UnitPreference` holds the process
   profile, emits the legacy `changed(length)` signal and a `profile_changed(profile)`
   signal for the new surfaces. `set_system` remains the one-value API and sets every
   quantity; `set_quantity_system` moves one.
2. **Presets and storage.** `UnitPreset` names Metric, Imperial (US), Canada (mixed)
   and Custom. `AppSettings` stores `units/profile` plus one `units/<quantity>` key;
   an absent profile reads the legacy `units/system` for every quantity, and the
   legacy key is kept truthful as the length system. No `.ogp` key changes.
3. **Pure conversions, one display seam.** `core/units.py` gains
   `format_temperature` / `parse_temperature` (Celsius), `format_precipitation` /
   `parse_precipitation` (millimetres) and `format_mass` / `parse_mass` (kilograms).
   `core/measurement_display.py` adapts temperature and precipitation to the active
   profile and Qt locale; the harvest log keeps its explicitly entered unit, with
   `default_mass_unit()` choosing only a new entry's default.
   `TemperatureSpinBox` keeps its value in Celsius while displaying °C or °F.
4. **Surfaces.** The preferences General tab exposes the preset and the six rows; the
   weather panel, frost thresholds, germination temperature and harvest log read the
   profile. Harvest records keep their explicit unit as the aggregation key
   (`kg`, `g`, `lb`, `oz`, `pcs`, `bunch`, `L`), so totals never mix units.
5. **Canada (mixed), provisionally.** Length and area are imperial; volume,
   temperature, precipitation and mass are metric. This is a recorded starting point,
   not a claim that every Canadian gardener chooses it; changing any row yields
   Custom, and the defaults are revisited when feedback exists.

**Alternatives considered**:
- *One global system only.* Rejected: it cannot express the mixed profile the issue
  asks for, and it forces a Canadian user to choose between feet and Celsius.
- *Convert stored values when the display changes.* Rejected: it mutates geometry and
  saved data, violating ADR-078 and the Agent API's centimetre contract.
- *Convert harvest totals to one unit.* Rejected: a bunch, a kilogram and a pound are
  not interchangeable records; the existing per-unit aggregation is the honest total.
- *A locale-derived unit default.* Rejected: the UI language decides formats, not
  measurement systems; the user chooses the profile.

**Consequences**: Adds `UnitProfile`, `UnitPreset`, `Quantity`, the three conversion
families, `TemperatureSpinBox`, and the per-quantity preferences rows. Weather and
germination displays refresh on `profile_changed`; existing settings and plans open
unchanged. Tests: `tests/unit/test_units.py`, `tests/unit/test_unit_preference.py`,
`tests/integration/test_unit_quantities.py`, `tests/ui/test_plant_database_panel.py` and the
preferences suites. Cross-refs: ADR-078, FR-MEAS-07..10, §8.3 (locale), issue #907.
