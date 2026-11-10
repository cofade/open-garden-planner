## Case study: a light theme that painted white on cream — the app set one of three carriers of "light or dark" (#791, fixed 2026-11-10)

**Symptom**: with the app's light theme on a dark-mode Windows, "61 plant(s) in project" and the seed statistics line were white on cream, unchecked check boxes had no visible outline, plant-detail links were salmon on cream, and the toolbar's overflow button could hardly be seen. In the dark theme the Planting Calendar chart, the soil sparkline and the canvas rulers were light pictures. Every one of these looked right on a machine whose Windows mode matched the app's theme.

**Theories entertained (wrong)**:
- *"Two labels use `palette(text)`; replace those two."* True for the two labels, and it would have left every link, placeholder text and native control as they were.
- *"The pitfall catalogue already has this (PF-UI-09)."* It did record that `apply_theme()` only writes a stylesheet — as a rule for callers ("pass the user's theme mode"), not as a defect. A fact filed as a rule stopped being questioned.
- *"The toolbar's overflow button follows the colour scheme, so pinning the scheme fixes it."* On the `windows11` style it does. Rendered in the test style it was still 1.58:1.

**What instrumentation revealed** (a probe on the owner's machine, Qt 6.12, style `windows11`, and contrast measured on rendered widgets):

```
styleHints().colorScheme() = Dark      palette Window #1e1e1e  Text #ffffff  Link #fb9d8b
setColorScheme(Light)   -> palette Window #f3f3f3 Text #000000, synchronously
setColorScheme(Unknown) -> the system's again
label with color: palette(text)        light app / dark Windows   1.05
rich-text link                         light app / dark Windows   1.95
unchecked QCheckBox outline vs window  1.67 (light)  1.06 (dark)  in EVERY combination
[EXT] geom QRect(785, 4, 12, 36)  -> the overflow glyph is drawn 2 px wide
```

The last line is the second finding: the check box and the overflow button were weak in every combination, also where Windows and the app agreed. No palette could fix those.

**Root cause**: a Qt application has three carriers of "light or dark": the stylesheet, the application palette and Qt's colour scheme. `apply_theme()` set the first. `palette(text)` in a widget stylesheet, rich-text links and placeholder text read the second; the native style draws everything no stylesheet rule covers in the third. Both stayed the operating system's. Separately, the stylesheet's own `QToolButton { padding: 4px; border: 1px … }` rule also applied to the 12 px wide `QToolBarExtension`, leaving 2 px for its picture, and there was no `QCheckBox::indicator` rule at all. And a widget that paints with module-level `QColor` constants is outside all three carriers.

**Fix** (`ui/theme.py`): `build_palette(colors)` maps every palette role to a token and `apply_theme()` sets it; `_pin_color_scheme` tells Qt the app's scheme and hands it back for `ThemeMode.SYSTEM`. The trap this opens: `detect_system_theme()` read the application palette, which is now the app's last theme — it asks `QStyleHints.colorScheme()` instead (`_system_color_scheme`, the seam tests replace). Indicator rules for check boxes; a `QToolBarExtension` rule with the theme's glyph, no padding, placed AFTER the `QToolButton` rules (same specificity: the later one wins). Painters read `theme_qcolor(token)` while painting, and a second lint gate lists every painted colour literal left in chrome with its reason.

**A second symptom the same way of working found** (#796): the calendar's "Today's Tasks" showed one and a half of thirteen rows. `QScrollArea.sizeHint()` caches its first answer (measured: 18 px for content that had grown to 336 px), so the fix was `updateGeometry()` after the rebuild — which worked in a probe and not in the window. One print at the end of `set_data`:

```
[SD] set_data n 13  scroll hidden False  content hint 8  scroll hint 8  item hint 8
[SD] end: scroll h 8                                  (later, same widget: content hint 375)
```

The content's own hint was 8 px right after thirteen rows had been added. A child added to a VISIBLE parent is shown by a queued call, and a layout does not count a hidden child; the probe had filled the list before showing it. The scroll area now answers its hint from its content every time and calls `updateGeometry()` on the content's `LayoutRequest`.

**After**: text 5.44 (light) and 7.13 (dark) in all four combinations of app theme and Windows mode, where it had been 1.05 to 1.24 in the mixed ones; check-box outline 5.44 / 7.13; the chart's rows are the theme's `input` and `background_alt`, and its harvest bars 3.45:1 on dark rows where the reference colour is 2.18.

**Lesson**: measure the rendered widget in every combination before naming the cause — the two symptoms that were wrong in ALL combinations pointed at a second cause the first fix would have hidden. When a fix works in a probe and not in the app, print the value the fix depends on at the moment it is used. And read a "known pitfall" as a claim about the code: this one described the defect and was filed as a rule.
