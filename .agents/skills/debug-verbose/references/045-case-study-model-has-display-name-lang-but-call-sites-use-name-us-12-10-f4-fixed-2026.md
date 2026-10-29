## Case study: model has display_name(lang) but call sites use .name (US-12.10/F4, fixed 2026-05-03)

**Symptom**: With German locale active, the soil-test dialog's amendments list and the Amendment Plan table both showed substance names in English ("Dolomite lime", "Blood meal") despite the bundled `amendments.json` carrying perfect German `name_de` translations and the `Amendment` dataclass having a `display_name(lang)` helper.

**Root cause**: [`format_amendment_line`](src/open_garden_planner/ui/dialogs/soil_test_dialog.py) and [`AmendmentPlanDialog._populate_table`](src/open_garden_planner/ui/dialogs/amendment_plan_dialog.py) both read `rec.amendment.name` directly — bypassing the localisation helper.

**Lesson**: When you add a localisation helper to a model (`display_name(lang)`), grep every read of the underlying field (`.name`) in the same package and switch them over. A helper added without consumers is dead code that gives a false impression of i18n coverage. Same family of bug as F2 ("ghost field") but at the *call site* instead of the UI layer.

---

