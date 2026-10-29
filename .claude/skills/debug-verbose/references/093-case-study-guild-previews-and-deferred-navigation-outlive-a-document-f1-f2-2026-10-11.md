## Case study: guild previews and deferred navigation outlive a document (F1/F2, 2026-10-11)

**Symptom.** Independent review reproduced a deleted-wrapper exception when a plan was cleared while its guild preview was open. A pending sidebar click selected an object in a newly loaded copy of the plan.
**Wrong theories.** None adopted; the old branch was exercised directly before changing the lifecycle contract.
**Evidence.** A temporary probe against the second review snapshot printed `[GUILD-LIFECYCLE] markers_after_clear 4`, followed by `RuntimeError: wrapped C/C++ object of type QGraphicsEllipseItem has been deleted` in `clear_preview()`. The same probe printed `[GUILD-NAVIGATION] selected_after_load 1` when the replacement document reused the original UUIDs. The final regression passes after the fix; all probe prints and files were removed.
**Root cause.** A UUID guards object identity within a document, not across document replacement. Preview wrappers also outlived the C++ objects owned by the scene.
**Fix.** Close the picker on `document_replaced` before scene teardown, invalidate its document generation, and tolerate already-destroyed preview wrappers during idempotent cleanup. Stop pending sidebar navigation and discard queued IDs at replacement.
**Lesson.** Every deferred GUI operation needs both object identity and a document-lifetime boundary. A teardown test must cover a replacement that retains the same object UUIDs, not just an empty scene.

