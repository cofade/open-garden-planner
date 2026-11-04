## Case study: a "constant" button width measured on a font engine that does not exist (PR #584 manual pass 2)

**Symptom.** The owner: the strip's Past/Future label pushes the controls after it while
the month slider is dragged. The fix, a Today button that says Past/Future in place at
one width, passed its offscreen tests in every language and theme.
**Wrong theory.** That offscreen widths are font widths. The ADR draft quoted the button
as 48 / 108 px wider "at Verdana 9 pt", and #573's local strip failures were blamed on
Verdana being present on Windows.
**Evidence.** The senior review's probes: offscreen on Windows, "Today" = 60 px, "Hoy" =
36, "Vergangenheit" = 156 - exactly 12 px a character in every family (a box engine,
no font database). With `-platform windows` and `QT_SCALE_FACTOR=1.25` the width moved
by 1 px in 378 of 480 font/size/language combinations; the strip's row estimate for
German 10 pt at 800 px read three rows.
**Root cause.** `horizontalAdvance` rounds to nearest; `QToolButton::sizeHint` measures
`fontMetrics().size(Qt::TextShowMnemonic, ...)`, a rect rounded up. Box advances are
whole, so offscreen could never show the difference, nor real widths.
**Fix.** Measure each text as the widget does; slider floor 70 px. Tests: unhinted fonts
at fractional sizes; themed narrow strip asserting the reflow's own estimate. Run with
`QT_QPA_PLATFORM=minimal:enable_fonts` for real fonts, headless: all 41 strip tests pass.
**Lesson.** Before writing a pixel number down, check which font engine produced it
(PF-TST-26). Measure a widget's text with the widget's own measure.

