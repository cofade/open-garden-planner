# Pitfalls — UI forms and layout

### PF-UI-28

- **Rule:** A form taller than the screen scrolls in a `QScrollArea`; Save/Cancel stay outside it and the dialog opens at content height capped to the screen.
- **Pinned by:** `tests/integration/test_preferences_layout.py`
- **Source:** #569
- **Status:** standing
- **Legacy:** none
### PF-UI-29

- **Rule:** A control that is the only way to SET a value must never be gated on that value already existing. Ask "can this object carry the property?" (does it have a footprint?), not "does it carry one already?".
- **Pinned by:** `tests/integration/test_height_property.py::test_every_footprint_type_offers_the_height_field`; `tests/integration/test_height_property.py::test_a_generic_shape_can_be_given_a_height`; `tests/integration/test_height_property.py::test_an_item_without_a_footprint_has_no_height_row`
- **Source:** #628 (owner manual pass of #627)
- **Status:** standing
- **Legacy:** none (new entry)

The Properties panel's "Object height" row was gated on `object_height.has_height_semantics(type, metadata)`, whose last clause is "an explicit height already exists". For every type with a per-type default that is harmless (the first clause passes), but a generic shape, an in-ground bed, a terrace, a pond, a lawn, a path or a driveway has no default — so the only way to become eligible was a value the field alone can write. Measured: a polygon's Properties showed Typ/Name/Ebene/Position/Füllfarbe/Füllmuster/Linienfarbe/Linienstärke/Linienstil/Anordnen and no height row; switching the object's TYPE to Garage (which has a default) made the shadow work, at the cost of the object's look and 3D builder.

The fix splits the question in two: `has_height_semantics` stays the type-level answer, and the panel asks the new `shows_height_field(..., has_footprint=item_has_footprint(item))` — the yes/no form of `item_outline`, so answering it does not build a 16 000-vertex outline — every item with a footprint gets the row, "Auto" (0) is no height, so nothing changes until the user types one. `lies_on_ground` already yields the moment a height is set, which is what makes "a terrace with a height is a platform" coherent rather than a special case.

The class is general: any "only way in" control (a height, a parent link, a style) gated on the state it produces is unreachable, and the suite will not notice because every test that exercises it starts from an object that already has the state.

### PF-UI-30

- **Rule:** Properties panel type dropdown items must resolve a valid icon across all ObjectType enum values; missing SVG category/tool icon mappings leave blank rows in the selector dropdown.
- **Pinned by:** `tests/ui/test_properties_panel.py`
- **Source:** #643
- **Status:** standing
- **Legacy:** none (new entry)

The object type combo box in the Properties panel visualizes each type with an icon.
Omitting mappings in `_get_object_type_icon()` for newly added or specialized types
(such as `CONTAINER`, `CONTAINER_ROUND`, `WALL_PLANTER`, `TRELLIS`, `GENERIC_ELLIPSE`,
and `HEDGE_POLYGON`) resulted in null icons and missing visual cues. All enum values
must map to appropriate category or tool icons.


### PF-UI-31

- **Rule:** A re-entrant form rebuild detaches its widgets and `deleteLater()`s them; never call `QFormLayout.removeRow()` from a handler that can run inside one of those widgets' own signals.
- **Pinned by:** `tests/integration/test_cad_precision_integrity.py::test_layer_combo_change_does_not_destroy_the_sender`
- **Source:** #658
- **Status:** standing
- **Legacy:** none (new entry)

Choosing a hidden or locked layer in the Properties panel moves the item and
deselects it. The selection change rebuilds the panel synchronously, and
`_clear_form()` called `removeRow(0)` in a loop - which deletes the field
widgets immediately, including the `QComboBox` whose `currentIndexChanged` was
still being delivered. On the source fork's macOS host that aborted the process
with exit 139; on Windows/Qt 6.11 it survived but the signal was silently
dropped, so the panel cleared while the layer edit's own notification never ran.
The rebuild now takes each row, hides and detaches its widgets and schedules
`deleteLater()`, which is safe to do from inside the sender's handler and keeps
the widget alive for the rest of the delivery. The test wires the real
selection-to-panel path and asserts through `sip.isdeleted` that the sender is
alive while its signal runs.


### PF-UI-32

- **Rule:** A tooltip shows a shortcut once, in the user's own spelling. Keep shortcuts out of the translated tooltip text and append `ui.shortcut_text.localized_shortcut()`: Qt's key name plus the app's translated modifier tokens (`ShortcutsDialog` context: Strg/Umschalt/Auf). A baked literal is untranslated and duplicates the shortcut when the builder appends it; `QKeySequence.toString(NativeText)` alone stays English because Qt's own catalogs are not installed.
- **Pinned by:** `tests/unit/test_toolbar.py::test_the_constraint_toolbars_shortcut_is_native_and_appears_once`; `tests/unit/test_toolbar.py::test_the_constraint_toolbars_shortcut_is_german_in_a_german_ui`
- **Source:** manual-test follow-up 2026-10-31, PR #672
- **Status:** standing
- **Legacy:** none (new entry)

The constraint toolbar's entries already read "Chamfer (Shift+C) — bevel a
corner" and `ConstraintToolbar` appended `({shortcut})` itself. In German the
chamfer button therefore read "Anfasen (Umschalt+C) — Ecke abschrägen
(Shift+C)": the shortcut twice, and the second one in English because the
appended literal was not translated. The tooltip keys now carry no shortcut; the
builder appends `localized_shortcut()`, which renders the Qt key name and then
translates the modifier tokens through the shortcuts dialog's existing
`ShortcutsDialog` strings ("Umschalt+C", "Mayús+C"). Qt's own `NativeText` alone
was measured to stay English here: the app installs its own catalog, not Qt's.
The test asserts one parenthesised group and pins the complete German tooltip, so
a future entry cannot reintroduce either half.

### PF-UI-33

- **Rule:** A text-only `QToolButton` whose only job is to open a menu (`InstantPopup`) sets the `menuChevron` property: the app's style draws its menu arrow UNDER the last letter, and the button then reads as a label. The theme's chevron rule (`ui/theme.py`, shared with the plan strip's hidden-plants button) gives the arrow 16 px of its own beside the text.
- **Pinned by:** `tests/integration/test_living_garden.py::test_the_strip_s_menu_buttons_read_as_buttons`
- **Source:** #389 (owner's manual test of PR #699)
- **Status:** standing
- **Legacy:** none (new entry)

The owner could not find how to set the 3D weather: the 3D strip's "Wetter: Klar" button, an
auto-raised text-only `QToolButton` with `InstantPopup`, drew its `menu-indicator` squeezed
under the "r", and looked like a status label — as "Analyse" had since L2. A probe of the
real window showed the menu itself worked and held every choice. "Rundgang" did not look
broken because it is a `MenuButtonPopup` (its arrow has a section of its own), and the plan
strip's "0 ausgeblendet ⌄" because `QToolButton#PlanDateHiddenPlants` had a rule for it. The
rule now also matches `QToolButton[menuChevron="true"]`; set the property before the button
is first polished. The test checks both strip buttons carry it and that the rule gives the
arrow room (a probe button with the property is wider than one without, light and dark).

### PF-UI-34

- **Rule:** `QDialog.reject()` (Esc) hides a dialog without calling `closeEvent`, so a dialog that must stop something before it goes overrides both, and the two agree on what happens.
- **Pinned by:** `tests/integration/test_directors_cut.py::test_esc_cancels_a_recording_and_the_dialog_stays_to_say_so`; `tests/integration/test_directors_cut.py::test_closing_the_dialog_during_a_recording_stops_it_first_and_then_closes`
- **Source:** #390 (Phase 17 L6), senior review
- **Status:** standing
- **Legacy:** none (new entry)

The camera tour's dialog stopped a recording in its `closeEvent`. Esc went through `reject()`, which
hides and never calls `closeEvent`: the recording went on behind a dialog nobody could reach, with
the clock held. Now Esc cancels and the dialog stays, to say what happened; the X cancels, ignores
the close, and closes when the recording has stopped.

### PF-UI-35

- **Rule:** A list row that swaps one widget for another (a `QLabel` for a `QLineEdit`) pins its row height; the list measures rows from their real size hints plus its frame, never from a fixed per-row constant.
- **Pinned by:** `tests/integration/test_layers_panel_height.py`
- **Source:** #774 / #775
- **Status:** standing
- **Legacy:** none (new entry)

Two owner-reported layers-panel defects with one cause: the panel assumed every row was 36 px. `_adjust_list_height` multiplied the layer count by 36 and ignored the list's frame, so a font/DPI that made rows taller clipped the last row and left an empty band under it (#774). And the inline rename hid the `QLabel` and showed a `QLineEdit` whose size hint is shorter, so the row shrank while editing (#775). `LayerListItem` now sets a minimum height (`ROW_HEIGHT`), `_refresh_list` uses the row's real hint (at least `ROW_HEIGHT`), and `_adjust_list_height` uses the same fixed height in both the "all rows" and "scroll at five" branches, adding `2 * frameWidth()`.

### PF-UI-36

- **Rule:** Two window shortcuts on the same key fire NEITHER. A tool shortcut must be checked against every `QAction` shortcut in the main window; a `QToolButton` shortcut and a `QAction` shortcut are both registered on the top-level window.
- **Pinned by:** `tests/integration/test_split_shapes.py::test_the_split_shortcut_does_not_collide_with_snap`
- **Source:** #664, PR #783, ADR-075 addendum
- **Status:** standing
- **Legacy:** 11.4.21 (new entry)

The split tool first shipped with `S`, matching its name. `S` is also the main
window's **Snap to Grid** action. Qt did not prefer one: with both shortcuts
enabled in one window it dispatched an ambiguous-shortcut warning and ran
neither handler, so the new tool's advertised shortcut was dead while the
toolbar button itself worked. Measured on Qt 6.12 with a bare `QToolButton`
and a `QAction` in the same window (an empty hit list), and in the app the
canvas-level key fallback never saw the key either because the window's
shortcut map consumed it. The fix is `Shift+S`; the test asserts the tool
shortcut exists, differs from `snap_action`'s `S`, and that `S` still belongs
to Snap to Grid. Offscreen Qt has no focus window, so the test pins the
configuration rather than synthesising a key press.

### PF-UI-37

- **Rule:** `apply_theme()` sets all three carriers of light-or-dark — Qt's colour scheme, the application palette and the stylesheet — and nothing that DETECTS the system's mode reads `QApplication.palette()`, which is the app's own since then.
- **Pinned by:** `tests/unit/test_theme_palette.py`; `tests/integration/test_theme_surfaces.py::test_the_main_window_follows_the_theme_whatever_windows_says`
- **Source:** #791, ADR-039 addendum
- **Status:** standing
- **Legacy:** none (new entry)

The app's light theme on a dark-mode Windows painted white text on cream (1.05:1), invisible
check boxes and red links. `apply_theme()` wrote a stylesheet and nothing else, and a Qt
application has three carriers of "light or dark". The palette is read by `palette(text)` in a
widget stylesheet, by rich-text links (`QPalette.Link`) and by `palette().placeholderText()`. The
colour scheme (`QStyleHints.colorScheme()`) is what the native style draws everything in that no
stylesheet rule covers. Both stayed the operating system's. Measured on Qt 6.12, style
`windows11`: `setColorScheme(Light)` changes the palette synchronously, `Unknown` hands it back to
the system, and a role set with `app.setPalette` survives a later scheme change.

The fix builds a full `QPalette` from the tokens (`build_palette`) and pins the scheme. The trap
it creates is the second half of the rule: `detect_system_theme()` used to read the application
palette, which would now be the app's last theme, so "system" could never follow the system
again. It asks `_system_color_scheme()` (the seam tests replace), and for `ThemeMode.SYSTEM`
`apply_theme()` first un-pins the scheme, then resolves. Two things a palette does not reach were
found by rendering: a check box needs an `::indicator` rule, and the toolbar's overflow button is
a picture of the style's own, squeezed to 2 px by the `QToolButton` padding rule — it has a
`QToolBarExtension` rule with the theme's glyph. A widget that PAINTS reads `theme_qcolor(token)`
while painting; the calendar chart, the soil sparkline and the seed-viability cells each kept a
light picture in the dark theme, and `tests/unit/test_no_hardcoded_qss_colors.py` now lists every
painted literal that may stay, with its reason.

### PF-UI-38

- **Rule:** A stylesheet's box rules beat the sizes code sets: a `QPushButton` in a row, a header or a table opts out of the 80 px dialog minimum with `theme.set_compact()`, and a list row that is a widget is sized with `theme.list_row_size_hint()`, which adds the item padding back.
- **Pinned by:** `tests/integration/test_chrome_layout.py::test_a_compact_button_keeps_the_size_its_code_asks_for`; `tests/integration/test_chrome_layout.py::test_find_plants_rows_keep_their_descenders`; `tests/integration/test_chrome_layout.py::test_the_selection_panels_fit_the_sidebar`
- **Source:** #796
- **Status:** standing
- **Legacy:** none (new entry)

Four layout defects had one cause. The app stylesheet gives `QPushButton` `min-width: 80px`; with
padding and border that is a 110 px minimum, and a stylesheet minimum replaces the one
`setFixedWidth` / `setFixedSize` set (measured: an icon button with `setFixedSize(26, 20)` has
minimum width 110 and maximum width 26, and is laid out 110 px wide). So the Properties panel's
Arrange row was four 110 px buttons in a 440 px form with no horizontal scroll bar, which cut the
row AND every field above it; the Tasks tab's arrow was 110 px wide; and every `setFixedWidth(50)`
on an Edit or Delete button was dead code. Removing the minimum globally was rejected: those dead
fixed widths would start to apply and cut their texts. `set_compact(button)` sets a `compact`
property the stylesheet answers with `min-width: 0`; a compact button with a translated text gets
NO fixed width.

The same box model squeezes a list row that is a widget: the view gives an item widget the row's
rectangle minus `QListWidget::item`'s padding, so a row sized to `widget.sizeHint()` was 10 px too
low and Find Plants cut the descenders of its second line. `list_row_size_hint()` adds the padding
from the constant the stylesheet itself uses. A one-line row with a minimum height (the layers
panel, PF-UI-35) absorbs the loss and never showed it.

### PF-UI-39

- **Rule:** A `QScrollArea` remembers its widget's size hint from the FIRST call, and a row added to a visible parent counts in no hint until the event loop has turned; a list that must be as tall as its rows overrides `sizeHint()` and calls `updateGeometry()` on its content's `LayoutRequest`.
- **Pinned by:** `tests/integration/test_chrome_layout.py::test_todays_tasks_shows_whole_rows_not_one_and_a_half`
- **Source:** #796
- **Status:** standing
- **Legacy:** none (new entry)

The Planting Calendar's "Today's Tasks" showed one and a half of eighteen rows. Its scroll area
was created empty and filled later, and `QScrollArea.sizeHint()` caches its widget's hint the
first time it is asked (measured: 18 px for a list that had grown to 336 px, while a fresh area
around the same content said 288). The first fix, `updateGeometry()` at the end of the rebuild,
worked in a probe and not in the window. A print at the end of `set_data` showed why: the
content's own hint was 8 px right after thirteen rows had been added, and 375 px one turn of the
event loop later. A child added to a VISIBLE parent is shown by a queued call, and a layout does
not count a hidden child. `_FittedScrollArea` (`ui/views/planting_calendar_view.py`) therefore
answers `sizeHint()` from its content every time and calls `updateGeometry()` whenever the content
posts a `LayoutRequest`, which is when the rows have arrived.
