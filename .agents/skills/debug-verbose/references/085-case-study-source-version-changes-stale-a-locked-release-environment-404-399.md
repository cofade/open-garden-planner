## Case study: source version changes stale a locked release environment (#404/#399)

**Symptom:** a mechanical version-only source edit failed the proposed lock-freshness gate.
**Initial assumption tested:** version sync could continue to change only the two source
version declarations. **Key evidence:** the temporary-copy probe returned a stale-lock error
from `uv lock --check --offline`; `uv lock --offline` changed the editable project's version
while preserving third-party selections. **Root cause:** the project version is lock metadata.
**Fix:** prepare_version_sync stages source, native lock and export together, compares complete
third-party package records, and writes only with --apply. **Lesson:** prove metadata-only
changes against the actual install path. The subprocess regression covers dry-run nonmutation,
apply, export agreement and idempotent reruns; no remote production merge is part of this test.


