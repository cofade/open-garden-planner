## Case study: A1 trust boundaries (#453, 2026-10-13)

**Symptoms.** Non-finite JSON reached scene preparation and could overwrite a good
plan; an image/png header allowed HTML into the cache; duplicate installer assets
selected the first entry; native Linux Qt 6.11 settings were mode 0644 under umask 022.
**Wrong theories.** No runtime hypothesis adopted before baseline reproduction.
The Windows registry sandbox failure was isolated by running the same failing-first
tests outside the sandbox; it was not treated as product behavior.
**Evidence.** The failing regression emitted `[A1-NUMERIC] invalid data reached scene
preparation`, with the load -> _prepare_scene_data stack. The save test reported
`DID NOT RAISE ValueError`; the image test returned a cached path for HTML; the
duplicate test returned a download URL. A disposable Linux Qt probe printed
`{'qt': '6.11.0', 'umask': '022', 'mode': '0o644'}`.
**Root cause.** Permissive JSON at several independent file paths, content-type-only
cache validation, unbound updater metadata/download/launch, and reliance on Qt's
default creation permissions. Conditional angle serialization could also omit NaN.
**Fix.** Shared strict/atomic plan I/O; detached journal reconciliation; a release-bound
verified installer result and pre-launch recheck; bounded image streaming plus full
decode and atomic PNG caches; Linux descriptor protection in the existing settings
factory and explicit startup refusal. Keep Windows/native stores and existing keys.
**Lesson.** Pin every bypass, not only the main caller. Finite operands can overflow;
headers are not data validation; a downloaded path is not a verification result; a
mocked Windows chmod does not establish Linux permissions. Probe logs are task
artifacts only. Pins live in the A1 unit/integration safety tests and settings isolation.

