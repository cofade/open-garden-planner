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
