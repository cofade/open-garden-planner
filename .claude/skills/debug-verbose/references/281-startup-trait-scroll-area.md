# Case study: Plant filters appeared as windows during startup (#666 review)

**Symptom.** Brief windows flashed near the centre of the monitor before
the main window of the frozen application opened.

**Wrong theory.** The startup sequence opened and dismissed ordinary dialogs.

**Key evidence.** [STARTUP-NATIVE] recorded separate Qt windows lasting around
one frame. [STARTUP-QT] traced Show on QScrollArea to setVisible during
CategoryDropdown construction, before the layout adopted the scroll area.

**Cause and fix.** The filter scroll area had no parent when it was shown.
Give it the popup as parent at construction so it is a child before visibility
can change.

**Lesson.** A later layout insertion cannot prevent a top-level window from
flashing earlier. Construct widgets with their parent before showing them.
