## Case study: a probe "isolated" its settings with the QApplication name (#587)

**Symptom.** The owner's startup Welcome dialog disappeared; the code was intact and the registry key held `startup/show_welcome = false`. The owner had not changed it.
**Wrong theories.** A regression in the startup path; a settings migration; the dialog's own default. The code path was correct.
**Evidence.** The registry key was written four seconds after a review probe saved it. The probe built `GardenPlannerApp`, gave the QApplication a throwaway name and called `QSettings.setDefaultFormat(IniFormat)`, believing both isolated it. `create_qsettings()` passes the module's `(organization, application)` to `QSettings(org, app)`, and that constructor always uses the native format.
**Root cause/fix.** A probe outside `scripts/` is outside `test_script_isolation.py`'s gate, and nothing refused the production names. `create_qsettings()` now refuses them under `offscreen`/`minimal` or an exact agent-session variable unless `main()` (`OGP_PRODUCT_PROCESS`) or `script_isolation`'s rebound names marked the process; `OGP_ALLOW_PRODUCTION_SETTINGS` is the deliberate override.
**Lesson.** A throwaway QApplication name and `setDefaultFormat` are not isolation. Guard the store at the chokepoint, not in the probe's discipline, and make the refusal name the fix.

