## Case study: three i18n leaks the zero-unfinished gate cannot see (issues #393, #408, #410, fixed 2026-10-04)

**Symptom.** With German UI, generated soil-amendment task titles stayed English
(`Compost`, `Elemental sulfur`) while the same bed's amendment recommendations were
German; the agent `suggest_companions` tool returned English plant names while the
Companion panel was German; and the opt-in "Garden journal notes" PDF page printed five
strings in English. `test_german_ts_has_no_unfinished` was green throughout.

**Wrong theories.** "The `.ts` file is missing translations" (it was not — the strings
were either data-selected or never registered). "The agent layer must translate" (it
must not — localisation is upstream, and a second path is the failure the D3 convention
exists to prevent). "Make `display_name()` default to the active language" (that would
have changed the persisted task id and orphaned saved done/snooze state).

**Key evidence.** `ruff check scripts --select F601` reported five repeated
`TRANSLATIONS` keys; an `ast` diff showed 62 strings shadowed, 5 absent from `de.ts`.
`grep` found the only no-language call sites: `task_generator.py::_bed_amendment_recs`
and `companion_sets.py::suggest_companions`. `tests/unit/test_task_generator.py` pinned
the task id as `soil_amendment:bed-1:Garden lime`, proving the id was the English name.

**Root cause.** All three are display strings produced by shared, Qt-free services that
never resolved the active UI language (a `lang="en"` default), or were dropped by a
duplicated dict key before they could be registered. The gate only inspects strings
already in the table.

**Fix.** One shared `app/settings.py::active_language()`; `BedInput.amendment_recs`
carries `(stable_name, display_name, rationale)` so the id stays English and only the
title localises; `suggest_companions` takes a `language` argument; the five shadowed
`PdfReportService` strings were merged into their surviving block; and CI now runs
`ruff check src/ tests/ scripts/` with an `ast` uniqueness test.

**Lesson.** "All strings translated" is three separate claims: the string reaches
`tr()`, its literal matches the registered key, and the registry actually emits it. A
data-selected display name and a duplicated registry key each pass the gate while
failing the user.


### Case study: repeated absolute propagation overrides (2026-10-04)

**Symptom.** An annual task read counted one overridden propagation step three
times; a three-year read counted it five times.

**Wrong theory.** Deduplicating by canonical task ID handled absolute dates.

**Key evidence.** Temporary [D3-OVERRIDE] output showed five prick-out tasks
on 2026-03-10 with IDs ending in 2024 through 2028. The integration regression
failed before the fix.

**Root cause.** The expanded anchor loop reapplied the same override, but the
shared propagation generator assigned a different anchor-year ID to each copy.

**Fix.** Assign overridden steps to their start-date year in the shared generator;
relative steps retain anchor-year IDs. The regression checks one task, its ID,
GUI convergence and annual month counts. Temporary instrumentation was removed.

**Lesson.** Preserve the distinction between absolute and relative time through
identity, not just range calculation. Deduplication cannot repair wrong identity.

