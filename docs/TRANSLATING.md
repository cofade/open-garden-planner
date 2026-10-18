# Maintaining complete application translations

Every language registered in `SUPPORTED_LANGUAGES` must cover the current UI source
inventory. Adding a language requires all existing keys; adding a wrapped UI string
requires translations in every registered target language in the same PR. Compare
Qt context/source/disambiguation keys, never word counts or catalog counts.

Use the locked Python environment from the development setup. From the repository root:

```powershell
$env:PYTHONUTF8 = "1"
.venv/Scripts/python.exe scripts/update_translations.py
.venv/Scripts/python.exe scripts/fill_translations.py
# Complete remaining target translations in each .ts file, then:
.venv/Scripts/python.exe scripts/compile_translations.py
.venv/Scripts/python.exe scripts/check_translations.py
```

`update_translations.py` extracts current source into temporary output, supplements
Qt extraction with audited helper/table declarations, preserves existing translations,
adds new target entries as unfinished, and marks removed keys vanished. English is the
source language: its template contains source identities. Do not copy the old English
catalog as an inventory. `fill_translations.py` is a German convenience mapping, not
a translator for other languages and not the definition of which strings exist.

For a new locale, register its native display name in
`src/open_garden_planner/core/i18n.py`, run the update command, and complete its generated
`resources/translations/open_garden_planner_<code>.ts`. Preserve translator comments,
HTML markup and interpolation fields. Compile and check before submitting a draft PR.
Incomplete registered languages fail automatically; no test parameter list needs editing.

## Source patterns

Use `self.tr("literal")` in QObject widgets, or
`QCoreApplication.translate("Context", "literal")` elsewhere. Local aliases of the
latter and simple single-argument `_tr` forwarding functions are audited. Keep Qt marker
names unaliased. Call local helpers directly, with a positional or named source argument;
imported helpers and callback aliases require explicit Qt calls. Calls through another
object must use an explicit context rather than inheriting the caller's class context.
Context-less module markers and dynamic source lookups require a narrow
declaration in `scripts/i18n_bindings.json`, selecting the actual production symbol/table
and its consuming context. Unknown dynamic lookups and stale declarations fail extraction.
Do not add duplicated English literal lists or derive required keys from German mappings.
Custom/provider names, Latin names and machine identifiers keep their documented data
boundaries; finite bundled common names are extracted from the bundled JSON itself.

Declarations cover object/path styles, descriptor labels, gallery/plant names, parser
errors, command fragments and other bounded helper inputs. When adding a table member,
the inventory grows automatically. A new unsupported expression requires an explicit
source binding and an extraction/mutation test, not a file-wide exemption.
Declarations select complete table values or display-bearing constructor fields, including
plain strings without markers. Dynamic consumers retain their disambiguation comments.

## What the required check enforces

- Every registered catalog has exactly the active source keys; vanished/obsolete records
  cannot supply coverage. Duplicates and wrong contexts/comments fail.
- Target values are completed and nonblank. Matching source text can be legitimate
  (for example `Ctrl+S` or a proper name); identity text alone is not proof of completeness.
- Python fields/conversions/format specifications and Qt placeholders are preserved.
- Compiled `.qm` files match the validated `.ts` and actual Qt lookups, including Unicode.
- The checker is read-only and returns nonzero with locale/key/source-location diagnostics.

The compiler is currently singular-only. Numerus/plural or length-variant messages fail
explicitly until a change adds tested compiler support and locale-form validation. They
must never silently fall back to English. The gate does not judge linguistic quality,
visual fit, or arbitrary text that was never wrapped for translation.

The existing required CI `Test` job runs the checker before pytest, and pytest includes
the same source/binary gate. Menu mnemonic tests enumerate `SUPPORTED_LANGUAGES`.
Keep the PR draft until maintainer manual acceptance: View > Language > select locale,
restart, inspect menus/dialogs in both themes, and check translated data fallbacks.
See arc42 section 8.3, ADR-008's #496 addendum, and the translation gate tests.
