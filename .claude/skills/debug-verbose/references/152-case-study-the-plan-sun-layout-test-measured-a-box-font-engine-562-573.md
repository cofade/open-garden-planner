## Case study: the Plan & Sun layout test measured a box font engine (#562/#573)

**Symptom.** `tests/integration/test_plan_sun_controls.py` failed 20 cases on the Windows dev box and passed on Linux CI; German/Spanish groups wrapped into 3–4 rows at 800 px instead of 2.
**Wrong theories.** The translated labels were too long; the theme padding differed; a leaked `arial.ttf` registration from `test_plan_timeline.py` changed the font (a separate defect, not the cause).
**Evidence.** Under `QT_QPA_PLATFORM=offscreen`, `QFontDatabase.families()` was empty and `horizontalAdvance("i") == horizontalAdvance("W") == 12`; Verdana 9 pt "Today" measured 60 px. Registering `C:/Windows/Fonts/verdana.ttf` and setting `qapp.setFont(QFont("Verdana", 10))` made it 34 px, and the file passed 78/78. `QT_QPA_PLATFORM=minimal:enable_fonts` gave the same real-engine answer.
**Root cause/fix.** Offscreen Windows has no font database, so every family resolves to the box engine; the assertions were right and the environment was wrong. `tests/conftest.py::ui_font_family` registers the real faces once and sets the application font; `tests/unit/test_test_font_contract.py` fails on a box engine; the per-test `addApplicationFont` in `test_plan_timeline.py` is gone.
**Lesson.** A text-metric failure that disappears on CI is an environment fact, not a translation fact. Assert `i` and `W` differ before trusting a width, and register the font at session scope rather than inside one test, where it leaks into every later test.

