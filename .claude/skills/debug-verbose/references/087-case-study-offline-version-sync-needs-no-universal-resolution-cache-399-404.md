## Case study: offline version sync needs no universal-resolution cache (#399/#404)

**Symptom:** Windows sync tests passed, while the first locked Linux suite failed its sync
subprocess. **Assumption refuted:** installing the lock necessarily primes all metadata that
an offline re-resolve needs. **Key measured evidence:** `[OFFLINE-COLD] 1` reported PyQt6 not
found in the cache for a Windows/Python >=3.15 resolution split; `[CHECK-COLD] 0` followed by
`[OFFLINE-AFTER-CHECK] 1` proved a freshness check alone did not prime that metadata.
**Root cause:** changing the editable project version invalidated the lock and triggered a
universal re-resolve; current-platform installation does not cache every other platform.
**Fix:** stage only the editable project's lock version alongside both source declarations,
then run native uv lock validation offline and regenerate the export. Compare full third-party
records before applying. **Lesson:** test cache independence explicitly. The real subprocess
sync test uses an empty UV_CACHE_DIR and passes on both Windows and Linux; underlying uv
stderr is now reported on failure. Supported-Python metadata and dependency selections stay
unchanged. No temporary instrumentation remains in production scripts.


