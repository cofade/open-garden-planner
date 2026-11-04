## Case study: readiness must protect exports even without a sun map (US-F4 combined controls)

**Symptom:** the new export guard failed on a fresh plan: CanvasScene has no
_document_generation attribute until its first document reset. An already-ready
no-map Future also carried no document identity.
**Wrong theories:** none adopted; the failing integration trace identified the
missing attribute directly, and the explicit replacement test exposed the missing
no-map check rather than a worker problem.
**Key evidence:** AttributeError at SunExportGate._begin on the untouched fresh
CanvasScene; controlled export tests then exercise generation zero, replacement,
pending workers, cancellation and API-thread timeout without writing output.
**Root cause:** exposure readiness and export document identity are different
contracts. The exposure collector already treats a missing generation as zero.
**Fix:** capture generation/revision/wall time independently of optional exposure,
use the collector's zero-generation convention, and validate immediately before
rendering. **Lesson:** an optional analysis cannot be the sole identity token for
a mandatory export boundary.


