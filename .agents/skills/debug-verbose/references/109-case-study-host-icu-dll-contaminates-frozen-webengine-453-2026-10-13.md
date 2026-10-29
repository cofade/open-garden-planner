## Case study: host ICU DLL contaminates frozen WebEngine (#453, 2026-10-13)

**Symptom.** Source self-test passed, but the frozen self-test opened a missing-
procedure error while importing QtWebEngineWidgets.
**Wrong theories.** Qt micro-version mismatch remained unproven; source/frozen Qt
DLL hashes matched. A PE probe initially reported many missing Qt symbols because
pefile stopped after 8,192 exports; raising its export limit removed those false hits.
**Evidence.** Analysis-00.toc collected icuuc.dll from the host Poppler runtime.
The frozen ICU was 78.3 with suffixed exports; source Qt loaded Windows ICU 72.1.
Only the Qt6Core -> bundled ICU missing imports remained after correcting the probe.
**Root cause.** The build inherited an unrelated tool runtime on PATH, which made
PyInstaller bundle an incompatible ICU DLL ahead of the native Windows library.
**Fix.** Clean rebuild with a controlled PATH. Detached self-test exited 0 and the
eight-second smoke exited 124. No dependency pins or packaging spec were changed.
**Lesson.** Read actual loader paths and collection provenance before upgrading Qt.
A diagnostic tool's truncation limit can masquerade as a dependency defect.

