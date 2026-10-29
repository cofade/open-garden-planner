## Case study: Preferences controls squeezed to 0–14 px (#569)

**Symptom.** On a short display, Edit → Preferences clipped input text and
collapsed several Agent API controls to zero height; the form needed about
1137 px but the dialog's minimum was 550 x 400.
**Reported by** @jbuijgers, with a fork branch
(`fix/preferences-dialog-height`, commit 5bb91037) as the reproduction.
**Wrong theories.** The theme's font sizes (measured at both 10 and 14 pt — the
compression happened at both); the API-key widgets' own size policies (the plain
line edits and combo boxes were compressed too).
**Evidence.** A probe compared every visible control's `height()` with its
`minimumSizeHint().height()` at 550 x 400 and 550 x 800: line edits and buttons
measured 0 px and 14 px against a 26 px hint. The form's layout was simply
being squeezed into the dialog's own height.
**Root cause/fix.** The dialog put the form directly in its `QVBoxLayout` and
never scrolled, so Qt compressed children below their hints. Put the form in a
`QScrollArea` with Save / Cancel outside the viewport, and size the dialog from
the content height capped to the available screen. The regression test asserts
every visible control keeps its hint at 400 and 800 px in both fonts, that Tab
reveals the last setting, and that Save/Cancel still work after scrolling.
**Lesson.** `setMinimumSize` on a dialog is not a minimum for its children; a
tall form needs a scroll area. Measure `height()` against `minimumSizeHint()`,
not against the layout's total, and keep the action row outside the scroll so it
cannot be scrolled away.

