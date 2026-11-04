## Case study: English unnamed objects in German constraint rows (#457, 2026-10-13)

**Symptom.** Owner screenshot showed `Polygon – Rectangle Deckungsgleich`, while
Properties correctly showed `Rechteck`. Other unnamed types shared the path.
**Wrong theory.** A missing Rectangle translation was ruled out by the compiled
translator. No theory was adopted before tracing the label builder.
**Evidence.** `[A5-LABEL] GENERIC_RECTANGLE row= Rectangle canonical= Rechteck`;
`traceback.format_stack()` traced command-history refresh into `_build_item_labels`.
An exhaustive catalog test additionally found missing Hedge/Roof Ridge entries.
**Root cause.** Enum title-casing bypassed the canonical translated object names.
Direct descriptor tests supplied `A`/`B`, so they never exercised this boundary.
**Fix.** Reuse `get_translated_display_name` for unnamed constraint endpoints and
compare-overlay plants; register Hecke/Dachfirst. Preserve explicit names and data.
Four failing-first regressions cover all 52 object types, duplicate numbering,
explicit names, real German row/tooltip wiring and all three overlay plant types.
Remove temporary prints before commit.
**Lesson.** Verify translated templates with real upstream object labels, and
check catalog coverage against the full enum rather than only registered messages.


