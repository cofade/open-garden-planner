# Pitfalls — UI forms and layout

### PF-UI-28

- **Rule:** A form taller than the screen scrolls in a `QScrollArea`; Save/Cancel stay outside it and the dialog opens at content height capped to the screen.
- **Pinned by:** `tests/integration/test_preferences_layout.py`
- **Source:** #569
- **Status:** standing
- **Legacy:** none
