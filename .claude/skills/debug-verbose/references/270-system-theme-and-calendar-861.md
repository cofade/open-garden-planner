# Live System theme (#861)

- **Symptom** — Matching the system theme worked at launch. Changing system appearance left the existing palette and canvas surround in the old mode.
- **Initially plausible** — Qt's palette already propagated the application's tokens.
- **Evidence** — Emitting `QStyleHints.colorSchemeChanged` in System mode left `is_dark_theme()` false. The painted light calendar's indoor-sow blue was 2.96:1 on white.
- **Cause and fix** — Theme application had no subscriber to the OS scheme signal. The queued handler waits for Qt to finish its palette update, then reuses the full theme application. Series colors are calibrated to the lowest-contrast chart row in each theme.
- **Pinned by** — `tests/integration/test_startup_theme_refresh.py` and `tests/integration/test_theme_surfaces.py`.
