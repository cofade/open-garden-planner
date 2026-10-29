## Case study: undo cleared species data but kept its profile identity (PR #556 manual pass)

**Symptom.** Ctrl+Z restored the generic tree and cleared the form, while Turkey oak,
its image, links and attribution remained above it.
**Wrong theory.** Sprite/metadata undo tests were assumed to cover the whole sidebar.
**Evidence.** An isolated tagged probe printed `[PROFILE-UNDO] removed None
headerHidden False name Turkey oak (Quercus cerris) licenseHidden False`. A real-window
assignment/undo regression failed on the visible profile header before the fix.
**Root cause/fix.** _show_no_metadata and _hide_details only hid form rows. A shared
_clear_profile_header now clears/hides the profile identity, thumbnail, licence line
and source tooltip in both paths. Keep the selected species-free item for Create Custom.
**Lesson.** A panel's empty-state transition must clear every representation of its
identity, not just the editable form. Undo/redo coverage checks the header too.
Pinned by test_undo_species_assignment_clears_the_whole_profile_and_redo_restores_it
in tests/integration/test_apply_database_species.py. No diagnostic prints remain.


