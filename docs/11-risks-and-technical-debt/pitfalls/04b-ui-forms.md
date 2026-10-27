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

The fix splits the question in two: `has_height_semantics` stays the type-level answer, and the panel asks the new `shows_height_field(..., has_footprint=item_outline(item) is not None)` — every item with a footprint gets the row, "Auto" (0) is no height, so nothing changes until the user types one. `lies_on_ground` already yields the moment a height is set, which is what makes "a terrace with a height is a platform" coherent rather than a special case.

The class is general: any "only way in" control (a height, a parent link, a style) gated on the state it produces is unreachable, and the suite will not notice because every test that exercises it starts from an object that already has the state.
