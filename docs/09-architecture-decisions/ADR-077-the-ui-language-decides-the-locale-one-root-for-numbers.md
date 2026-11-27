---
id: ADR-077
title: "The UI language decides the locale — one root for numbers, months and typed decimals"
status: "Accepted (visual-polish package, 2026-11-10); shipped in v1.38.0 (PR #838)"
refs: ["#792"]
legacy_anchor: adr-077-the-ui-language-decides-the-locale--one-root-for-numbers-months-and-typed-decimals-792
---

# ADR-077: The UI language decides the locale — one root for numbers, months and typed decimals

**Status**: Accepted (visual-polish package, 2026-11-10); shipped in v1.38.0 (PR #838)

**Context**: the app let the user choose a UI language and never told Qt a locale. Spin
boxes, date edits and every bare `QLocale()` formatted in the SYSTEM locale; Python
f-strings always wrote a decimal point. On the owner's machine (UI English, Windows
German) the planting calendar read "Mrz, Mai, Okt, Dez" and a spin box "155,8" beside a
status bar that said "0.00 cm"; the German UI showed "6361.7 cm²". Issue #792 states the
rule it expects: month names, decimal separators and every word follow the
application's chosen language, never the system locale on its own.

**Decision**:

1. **`core/i18n.load_translator` is the one place that decides.** It sets Qt's default
   locale (`QLocale.setDefault`) from the UI language, before any widget exists.
   Everything else asks `current_locale()` or a formatter below; a bare `QLocale()`
   agrees, because the decision is also Qt's default.
2. **The language decides; the system contributes its region only in the same
   language.** A German UI on an Austrian or Swiss system is `de_AT` / `de_CH`; an
   English UI on a German system is `en_US`. The locale is built from Qt's own data
   (`QLocale(language, territory)`), never the `QLocale.system()` object, whose names
   are Windows' ("Mrz", "Mo") — the same language must read the same on every machine.
3. **Every number in UI text goes through one formatter.** `format_decimal` (fixed
   decimals, no group separator: in a CAD readout "1.234" must never be readable as a
   decimal), `format_trimmed`, `format_integer` (counts, with group separators),
   `month_abbreviation`, `format_day_month` (the order of day and month is a translated
   Qt pattern). A translated template that carries its precision (`"{d:.2f} m"`) is
   handed a `LocalizedNumber`, so no source string and no catalog entry changes.
4. **A `,` or a `.` is the decimal mark in a number field, typed or pasted.** A
   `QDoubleSpinBox` silently drops the other convention's mark (measured: locale `en`,
   typed "155,8", value 1558). Since the locale follows the UI language and the keyboard
   does not, a German numeric keypad would enter values ten times too large into an
   English UI. `ui/number_fields` puts a validator in front of the focused spin box's
   own: a number with exactly ONE mark gets it rewritten to the field's decimal mark,
   whichever way the text arrives (a key, Ctrl+V, the context menu's Paste). The first
   version rewrote key events only, so a pasted "155,8" was still 1558 (review round 1).
   A text with more than one mark is handed to Qt untouched: its own grouping is read in
   the field's locale and the other convention's is refused, so nothing is guessed. A
   `QSpinBox` has no decimal mark and is left alone. `parse_decimal` is the same rule for
   free text (the typed-coordinate field, the shopping list's price): a sign, ASCII
   digits and at most one mark; it refuses a group separator, an exponent and everything
   only Python's `float` reads (`nan`, `inf`, `1_000`), and its result is finite.
   What the UI shows, it accepts back — in either convention.
5. **Machine-readable data never uses these formatters; a reader-facing picture does.**
   The plan file, DXF, CSV and the clipboard rows of the shopping list write a decimal point
   in every language. An SVG or PDF is a document for a reader — its text follows the UI
   language exactly as the canvas does (see the plan-truth addendum below).
6. **Dates stay ISO where they are fields or keys** (`yyyy-MM-dd` in every date edit
   but the planting calendar's year-less steps, the Tasks tab, the plan-date strip). Only
   names — months, weekdays — and the day-and-month label of the calendar dashboard
   follow the language.
7. **A date or time FIELD takes nothing from the locale's territory** *(review round 1;
   confirmed by the owner, 2026-11-10)*. An English UI on a non-English system is `en_US` (decision 2), and
   a field left to that locale read "3:30 PM" and "6/7/26" and its calendar popup started
   on Sunday (measured: `load_translator("en")` on a `de_DE` system; the camera tour's
   four fields had no display format). The user asked for English words, not for US
   conventions. `ui/date_fields.as_date_field` / `as_time_field` are the one place a field
   is configured: ISO (`yyyy-MM-dd`), 24 hours (`HH:mm`), and the planting calendar's
   year-less step dates as `dd MMM`. Every `QDateEdit` / `QDateTimeEdit` / `QTimeEdit` is
   handed to one of them where it is built, and nothing else calls `setDisplayFormat`,
   `setCalendarPopup`, `setCalendarWidget` or `setFirstDayOfWeek`:
   `tests/unit/test_date_fields.py` walks the source, so a new field cannot forget it.
8. **A calendar popup starts its week on Monday in every UI language** *(review round 1;
   confirmed by the owner, 2026-11-10)*. ISO 8601, and the convention of the app's users (European
   gardeners; German, Spanish and Russian locales give Monday anyway). The same helper
   sets it. Rejected: the locale's week start (Sunday for an English UI, the regression
   this decision answers) and a preference (no user asked for one).
9. **A date in UI text is day, month NAME, year** *(review round 1)*:
   `core/i18n.format_short_date` ("7 Jun 2026"; the order is a translated Qt pattern in
   context `DateFormat`, like `format_day_month`'s). Never a numeric day/month pair: its
   order belongs to the territory ("6/7/26" is 7 June in `en_US`). The 3D info card and
   the sun-path legend, the heatmap probe and the wipe label use it; nothing outside
   `core/i18n.py` formats with a bare `QLocale().toString(...)` (same test file).

**Rejected**: the system locale for formats with the UI language for words (the state
before: two conventions on one screen, and the issue's own counter-example); an
application-wide Python event filter for the decimal key (it would run for every event
of every object — the rule is a validator on the spin box that takes the focus);
rewriting key events only (the first version: a paste produces no key event); removing
the rewrite and documenting the trap (a silent factor of ten in a CAD field).

**Consequences**: a single `,` or `.` is always the decimal mark. That is a trade-off
and it has a loser: a user who writes a thousands separator. Measured in an English UI,
in a field with two decimals (three in brackets where it differs):

| Entered | Qt alone (before) | Now, typed | Now, pasted |
|---|---|---|---|
| `155,8` | 1558 | 155.8 | 155.8 |
| `1,234` | 1234 | 1.23 (1.234) | refused, the field keeps its value (1.234) |
| `1,234.5` | 1234.5 | 1.23 (1.234) | 1234.5 |

Typed, "1,234.5" is 1.23: the comma becomes the decimal mark, the digit beyond the
field's decimals and the second mark are refused key by key. Pasted as a whole it is
still 1234.5, because a text with two marks is left to Qt; a pasted "1,234" has one
mark, which is the decimal mark, and a field with two decimals refuses three. The first
version of this ADR said of the thousands separator that "nobody is known to do that in
a CAD field": that was a guess, and it is not the reason. The reason is that the other
choice loses more: a mark that is the decimal mark in one UI language and a group
separator in the other is a silent factor of ten or a thousand for everyone whose
keyboard or clipboard does not match the UI language, which is the owner's own setup.
The formatters write no group separator, so the UI never shows a number it would read
back differently, and the coordinate parser has read both marks as decimal since
Package A.

`core/i18n.py` imports QtCore only, because Qt-free services ask it for a formatter; the
number-field validator and the date-field helper live in `ui/`, and
`scripts/check_import_boundaries.py` holds that (`QT_CORE_ONLY`).

An English UI is `en_US` on a non-English system. That locale's month/day order, 12-hour clock and Sunday week start reach a widget
that takes its format from the locale; the app's own date and time fields and its dates in
text therefore take none of the three from it (decisions 7 to 9). The first version of this
ADR claimed here that the fields "all set" a display format; the camera tour's four did
not, and no field set a week start. The test session
has the application's locale like the app does (`conftest._app_locale`); before, it ran
in whatever the machine spoke. Numbers drawn on the plan (dimension lines, vertex labels,
the scale bar) **still used a decimal point when this ADR was written**; the plan-truth
addendum below (decision 10) is the later decision that changed them.

Cross-refs: PF-I18-09 (the account of the root cause and its traps); §8.3 "Locale";
FR-I18N-10, FR-I18N-11, FR-I18N-12. No debug-verbose case study covers this ADR: the first
version cited case study 220, which is the #791 theme case and says nothing about locale.

**Addendum (plan-truth package, 2026-11-11; shipped in v1.39.1, PR #903) - locale of
plan numbers and harvest units (#860, #863, #899)**:

10. **Every number a reader sees goes through `core.i18n`.** Dimension/angle
    readouts, vertex and resize labels, area labels, the ruler and scale bar,
    constraint conflict rows, the measure and constraint previews, the 3D focus
    distance, the report's plant positions and money cells, the PDF harvest total,
    the persisted harvest-journal text and the sun-mismatch diagnostic used
    Python's `:g`/`:.2f` and kept a decimal point in a German UI. They now call
    `format_decimal` / `format_trimmed` (or `LocalizedNumber` inside a translated
    template).
11. **A harvest unit is a stable stored key, translated only at display.** `kg`, `g`,
    `pcs`, `bunch` and `L` remain untranslated in `HarvestRecord.unit` and in the CSV
    (PF-I18-05); the dialog's combo carries the key as item data while showing
    `harvest_unit_label`, and the Harvest tab, PDF summary and linked journal note
    show the same label. A custom unit is shown as typed.

Cross-refs: FR-HARVEST-02, FR-HARVEST-07, FR-HARVEST-09; PF-I18-05; §8.36.

## ADR-039 addendum: the app owns the palette and the colour scheme, and chrome that paints reads tokens (#791)

ADR-039 made `ui/theme.py` the single source of chrome colours and delivered them through
ONE carrier, the generated stylesheet. A Qt application has three: the stylesheet, the
application palette and Qt's colour scheme. The two the app left alone stayed the
operating system's, so the app's light theme on a dark Windows had white text on cream
wherever a widget asked the palette (`palette(text)`, rich-text links, placeholder text)
and near-invisible native controls wherever no stylesheet rule reached.

1. **`apply_theme()` sets all three.** `build_palette(colors)` maps every palette role to
   a token (new token `link`); `_pin_color_scheme` tells Qt the app's scheme and, for
   `ThemeMode.SYSTEM`, hands it back first. `palette(...)` in a widget stylesheet is
   therefore a theme colour now.
2. **Detection never reads the application palette** (`detect_system_theme` asks
   `QStyleHints.colorScheme()`): the palette is the app's own, and a detection that read
   it could never follow the system again.
3. **A widget that paints reads `theme_qcolor(token)` while it paints.** The Planting
   Calendar chart, the soil sparkline, the canvas rulers and the seed-viability cells
   were light pictures in the dark theme. A DATA colour that keeps its hue in both themes
   (a chart series) is passed through `readable_on(color, surface)`.
   `tests/unit/test_no_hardcoded_qss_colors.py` gained a second gate that lists every
   painted colour literal left in chrome with the reason it is not chrome; the QSS
   allow-list stays empty.
4. **Geometry roles.** `set_compact(button)` and `list_row_size_hint(widget)` join
   `set_text_role` as the ways widget code states an intent the stylesheet answers
   (PF-UI-38).

Not built: following a change of the Windows mode while the app runs in `SYSTEM` (it
never did; `QStyleHints.colorSchemeChanged` is where it would be connected).

Cross-refs: PF-UI-37, PF-UI-38; §8.4.1 to §8.4.3, §8.4.5.

## ADR-060 addendum: the main window adopts the mode switch (#796)

Decision 2 put the Plan / 3D / Split row "floating over the canvas in Plan and Split". At
(28, 28) it covered the plan's top-left corner. `Workspace.adopt_mode_switch()` hands the
row to the window that hosts the workspace; the main window lays it out on the tab bar's
row, left of the frost badge, inside a holder it shows on the Garden Plan tab only. WHEN
the row shows is still the workspace's decision (Plan and Split, with the rest of the
chrome; in 3D the pane's strip has its own row), so `set_mode`, the fullscreen preview
and decision 3 ("nothing overlays the native 3D window") are unchanged. A workspace
without a host that adopts the row — every test that builds one alone — floats it as
before.
