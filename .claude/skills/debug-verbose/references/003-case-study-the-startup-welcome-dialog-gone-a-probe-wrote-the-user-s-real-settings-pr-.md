## Case study: the startup Welcome dialog gone - a probe wrote the user's real settings (PR #584 manual pass 2)

**Symptom.** The owner: the startup dialog for opening previous plans is missing, "a
regression we fixed several times".
**Wrong theory.** A code regression on the branch. The startup path was intact:
`_startup_sequence` -> `_show_welcome_dialog`, which returned early on the setting.
**Evidence.** `HKCU\Software\cofade\Open Garden Planner\startup`: `show_welcome =
false`, the key last written 14:25:35 (RegQueryInfoKey), 4 s after the reviewer's
`measure_strip.py` was saved. Three more scratchpad probes had the same defect;
one write is evidenced.
**Root cause.** The probes "isolated" with a throwaway QApplication name and
`setDefaultFormat(IniFormat)`. `create_qsettings()` passes the module's own names to
`QSettings(org, app)`, which always uses the registry. `scripts/script_isolation.py`
existed, but its gate reads only `scripts/`.
**Fix.** The key backed up, `show_welcome` restored and the recent list pruned to
the owner's own plan. The startup test runs the real path without timed waits.
PF-TST-27, §8.8/§8.10 and the reviewer definitions: a probe calls the helper.
**Lesson.** A script that builds the app is a user of the real store unless it
calls `script_isolation`. Check what a probe writes before running it.

