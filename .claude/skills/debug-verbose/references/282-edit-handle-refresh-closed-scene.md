# Case study: Edit handles refreshed after their canvas scene was destroyed (#666 review)

**Symptom.** Closing the packaged app could show an unexpected-error
dialog mentioning a deleted CanvasScene.

**Wrong theory.** The error belonged to reference-point data or its undo history.

**Key evidence.** The application crash log names CanvasView._refresh_edit_handles
and the access to CanvasScene.selectedItems. Deleting the scene with its view
still alive makes view.scene() return None and reproduces the same exception
when calling the slot.

**Cause and fix.** The view cached a Python wrapper after Qt had detached and
destroyed the underlying scene. Retrieve the attached scene through the view
and skip the refresh if it is absent.

**Lesson.** Check the Qt association before refreshing scene decorations
from callbacks that can still run during teardown.
