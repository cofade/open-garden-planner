"""The portable raster assertions still reject the original defects (#897)."""

import pytest

from open_garden_planner.ui.canvas import plan_labels
from open_garden_planner.ui.canvas.items.garden_item import SuccessionBadgeItem
from open_garden_planner.ui.canvas.sun_legend import SunMapLegendItem
from tests.integration.test_succession_badge_export import (
    test_what_stands_in_the_bed_does_not_cover_the_badge as check_badge_order,
)
from tests.integration.test_sun_map_legend import (
    mapped,  # noqa: F401 - reuse the real worker/map fixture
)
from tests.integration.test_sun_map_legend import (
    test_no_label_of_the_plan_touches_the_key_in_a_picture as check_label_exclusion,
)


def test_badge_order_oracle_rejects_painting_the_tag_below_the_pot(qtbot, monkeypatch):
    # Restore the original defect: a badge paints as its bed's child, before
    # later objects, and is absent from the foreground pass.
    monkeypatch.setattr(SuccessionBadgeItem, "paint", lambda self, painter, *_: self.paint_badge(painter))
    monkeypatch.setattr(plan_labels, "_paint_badge", lambda *_: None)
    with pytest.raises(AssertionError, match="the pot covers ink"):
        check_badge_order(qtbot)


def test_sun_key_oracle_rejects_ink_when_the_key_does_not_block_labels(mapped, monkeypatch):  # noqa: F811
    # Remove the exclusion, so the label is painted over the key. The tolerated
    # raster rounding must remain far smaller than that visible error.
    monkeypatch.delattr(SunMapLegendItem, "plan_label_blocker")
    with pytest.raises(AssertionError, match="the label was painted under the key"):
        check_label_exclusion(mapped)
