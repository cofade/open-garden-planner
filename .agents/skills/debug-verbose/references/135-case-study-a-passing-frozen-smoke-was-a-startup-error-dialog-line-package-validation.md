## Case study: a passing frozen smoke was a startup error dialog (line-package validation)

**Symptom.** The windowed executable survived eight seconds, but --selftest produced
no log or supervising process. Its window title was "Unhandled exception in script".
A separate console build exposed a DLL-load failure importing QtWebEngineWidgets.

**Wrong theory.** Root VC runtime DLLs were older than the Qt wheel's copies;
replacing them in the separate diagnostic artifact did not fix startup. The original
copies were restored before the successful next experiment. Major Qt DLL hashes
matched the installed wheel, and source imports succeeded.

**Evidence.** Analysis selected icuuc.dll from the Codex host's Poppler directory
on PATH. Its ICU78 exports are versioned; Qt6Core imports unversioned Windows ICU
symbols. System32 ICU supplies those symbols. Moving only the foreign ICU out of
the diagnostic artifact let self-test exit zero. No installed files were changed.

**Root cause/fix.** Dependency discovery searched the agent host's tool PATH and
collected an incompatible DLL. Rebuild from scratch with a controlled PATH of
Windows, base Python and the locked environment's Scripts directory. Do not ship a
hand-edited bundle. Source, lock and installer logic need no change for this host
finding. The clean rebuilt windowed artifact must still pass both frozen checks.

**Lesson.** Smoke proves survival, including a modal failure dialog. Require the
windowed self-test and its actual log. Audit a collected DLL's source path and
exports before changing dependency pins. See the controlled-build recipe in
ogp-build-and-run and the deployment documentation.

