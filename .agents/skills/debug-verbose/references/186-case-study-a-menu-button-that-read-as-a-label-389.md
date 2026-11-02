# Case study: a menu button that read as a label (#389, fixed 2026-11-02)

**Symptom.** In the owner's manual test of L5 the four weather steps failed with "I don't
see any way how to set the weather?" and "which button shows the weather?". The owner had
switched the garden's life off, and that switch lives in the same Weather menu. The 3D
strip showed "Wetter: Klar" at its right end.

**Theories entertained (wrong).**
1. "The weather choices are disabled or missing in some engine state." Nothing in
   `workspace_living.py` disables an action, and none is hidden.
2. "The menu opens behind the native 3D window." It is a top-level popup, and the Analyze
   menu, built the same way, had worked since L2.

**What instrumentation revealed** (a probe script on an isolated profile: the real window in
German and dark, split view; it clicked the button and grabbed the strip and the menu):

```
button visible True text 'Wetter: Klar' enabled True popup InstantPopup size 80x29
  action 'Klar' … 'Schnee' enabled True visible True; 'Heutiges Wetter'; 'Tiere und fallendes Laub'
popup QMenu visible True
```

The menu worked and held every choice. The strip's picture showed the problem: on
"Analyse" and "Wetter: Klar" the menu arrow was drawn as a tiny hook UNDER the last letter.
"Rundgang" had a proper arrow because it is a `MenuButtonPopup`, which gives the arrow a
section of its own. The plan strip's "0 ausgeblendet ⌄" had one because a
`QToolButton#PlanDateHiddenPlants` theme rule pads it.

**Root cause.** A text-only, auto-raised `QToolButton` with `InstantPopup` gets its
`menu-indicator` drawn over its text by the app's stylesheet, so it reads as a status label.

**Fix.** The theme's chevron rule also matches `QToolButton[menuChevron="true"]`, and both
strip buttons set the property (PF-UI-33). The test compares the size hints of probe buttons
with and without the property, in light and dark.

**Lesson.** When the owner cannot find a control, photograph the real widget before reading
code: the code was right and only the picture showed the fault. A manual-test checklist
should also name a control by what it looks like on screen ("Wetter: Klar ⌄ at the right end
of the 3D pane's top strip"), not by its role.
