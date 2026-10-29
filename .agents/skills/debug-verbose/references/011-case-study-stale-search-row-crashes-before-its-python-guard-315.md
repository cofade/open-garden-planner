## Case study: stale search row crashes before its Python guard (#315)

**Symptom.** The full parallel suite crashed on a search-result click after clearing
the document, despite a passing focused run and a live-membership check.
**Wrong theory.** Filtering the returned item after reading QVariant data was
assumed sufficient; the crash happened before that guard could run. An initial
numeric id() fix also ignored the existing PF-UI-03 UUID rule. Independent
review reproduced address reuse selecting unrelated new-plan items after Select All.
**Evidence.** The Windows access-violation dump pins find_replace_panel.py's
list_item.data(UserRole), called by the document-replacement regression after
CanvasScene.clear. The native stack is the instrumentation: no Python exception
is delivered and no later membership check can catch it.
**Root cause.** A QGraphicsItem stored in QVariant can become a dangling C++ pointer
when its scene deletes it. Reading that QVariant dereferences it inside SIP.
**Fix.** Apply PF-UI-03: store stable item UUIDs, resolve live items at click time,
use the canonical select_by_ids path and defer selection with an owned timer.
Document replacement clears matches/rows and stops pending selection. Select All
rebuilds rows. The test asserts the UUID payload before deletion (a deterministic
pin), positive live clicks and stale rejection across Select All and new items.
**Lesson.** Validate identity before crossing a native pointer boundary; retaining
a Python wrapper does not keep a scene-owned C++ item alive. Pinned by
test_find_replace_revalidates_cached_results_after_date_and_document_changes.

