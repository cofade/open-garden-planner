"""#795: an example's moment on the one session clock, and the way back (Qt-free)."""

from datetime import UTC, date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest

from open_garden_planner.core.showcase_moment import ShowcaseMoment
from open_garden_planner.core.sim_clock import SimClock
from open_garden_planner.core.templates import (
    BUNDLED_EXAMPLES,
    example_showcase_moment,
    template_title,
)

LATE = datetime(2026, 11, 10, 22, 30)
JUNE = (date(2026, 6, 21), time(11, 0))
SEPTEMBER = (date(2026, 9, 21), time(11, 0))
BERLIN = timezone(timedelta(hours=2))            # summer time on both reference dates


def clock_in(zone=BERLIN):
    return SimClock(LATE, tz=zone)


def test_an_example_takes_the_clock_to_its_date_and_a_daytime_sun():
    clock = clock_in()
    moment = ShowcaseMoment(clock)
    assert not moment.active
    moment.document_opened(JUNE)
    assert moment.active
    assert clock.plan_date == date(2026, 6, 21)
    assert clock.utc == datetime(2026, 6, 21, 11, 0, tzinfo=UTC)
    assert clock.wall == datetime(2026, 6, 21, 13, 0)


@pytest.mark.parametrize("offset", [-10, -8, -5, 0, 2, 5.5, 9, 12, 13, 14])
def test_the_date_is_the_reference_date_on_a_wall_clock_anywhere(offset):
    """The clock reads wall time in the computer's zone. A wall-clock midday would be
    night over Berlin for a user in Auckland; a UTC time of day on the local reference
    date is daylight over the garden everywhere."""
    clock = clock_in(timezone(timedelta(hours=offset)))
    ShowcaseMoment(clock).document_opened(JUNE)
    assert clock.plan_date == date(2026, 6, 21), "plants grow for the reference date"
    assert clock.utc.time() == time(11, 0), "and the sun stands where it does at 13:00 in Berlin"


def test_the_users_reading_comes_back_with_the_next_document():
    clock = clock_in()
    moment = ShowcaseMoment(clock)
    moment.document_opened(JUNE)
    moment.document_opened(None)
    assert clock.wall == LATE and not moment.active


def test_a_second_example_keeps_the_users_reading_not_the_first_examples():
    clock = clock_in()
    moment = ShowcaseMoment(clock)
    moment.document_opened(JUNE)
    moment.document_opened(SEPTEMBER)
    assert clock.plan_date == date(2026, 9, 21)
    moment.document_opened(None)
    assert clock.wall == LATE


def test_a_scrub_inside_the_example_is_not_carried_into_the_users_plan():
    clock = clock_in()
    moment = ShowcaseMoment(clock)
    moment.document_opened(SEPTEMBER)
    clock.set_datetime(datetime(2026, 9, 21, 17, 30))     # the tutorial's "17:30" step
    moment.document_opened(None)
    assert clock.wall == LATE


def test_without_an_example_the_clock_is_left_alone():
    clock = clock_in()
    moment = ShowcaseMoment(clock)
    mine = datetime(2026, 5, 1, 9, 15)
    clock.set_datetime(mine)
    seen = []
    clock.instant_changed.connect(seen.append)
    moment.document_opened(None)
    moment.document_opened(None)
    assert clock.wall == mine and not seen


def test_saving_the_copy_ends_the_showcase_and_later_settings_are_the_users():
    clock = clock_in()
    moment = ShowcaseMoment(clock)
    assert moment.copy_saved() is False, "saving a plan that is no example changes nothing"
    moment.document_opened(JUNE)
    assert moment.copy_saved() is True
    assert clock.wall == LATE and not moment.active
    mine = datetime(2027, 4, 1, 10, 0)
    clock.set_datetime(mine)
    assert moment.copy_saved() is False
    moment.document_opened(None)
    assert clock.wall == mine, "nothing older is put over the user's own choice"


def test_a_raising_listener_does_not_leave_a_reading_behind():
    clock = clock_in()
    moment = ShowcaseMoment(clock)
    moment.document_opened(JUNE)

    def broken(_change):
        raise RuntimeError("listener")

    clock.instant_changed.connect(broken)
    with pytest.raises(RuntimeError):
        moment.copy_saved()
    clock.instant_changed.disconnect(broken)
    assert clock.wall == LATE and not moment.active


class Tour:
    """The inner holder: a tour that moves the clock and puts one reading back."""

    def __init__(self, clock):
        self.clock, self.hold = clock, clock.wall

    def held_reading(self):
        return self.hold

    def rebase_hold(self):
        if self.hold is not None:
            self.hold = self.clock.wall

    def finish(self):
        reading, self.hold = self.hold, None
        self.clock.set_datetime(reading)


def test_a_tour_under_the_showcase_returns_to_the_document_open_when_it_ends():
    clock = clock_in()
    tours = []
    moment = ShowcaseMoment(clock, inner_hold=lambda: tours[-1] if tours else None)
    moment.document_opened(JUNE)
    tours.append(Tour(clock))                       # holds the example's moment
    clock.set_date(date(2026, 12, 21))              # a frame
    moment.document_opened(None)                    # an agent opens the user's plan
    clock.set_date(date(2026, 12, 24))              # the next frame
    tours[-1].finish()
    assert clock.wall == LATE, "not the example's moment on the user's plan"

    # an example opened under a tour: the user's reading is the HELD one, not the frame's
    tours.append(Tour(clock))
    clock.set_date(date(2026, 12, 21))
    moment.document_opened(SEPTEMBER)
    tours[-1].finish()
    assert clock.plan_date == date(2026, 9, 21)
    moment.document_opened(None)
    assert clock.wall == LATE


def test_opening_an_example_notifies_the_clocks_listeners_once():
    clock = clock_in()
    dates, instants = [], []
    clock.date_changed.connect(dates.append)
    clock.instant_changed.connect(instants.append)
    ShowcaseMoment(clock).document_opened(JUNE)
    assert dates == [date(2026, 6, 21)] and len(instants) == 1


# ── the sidecar ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("slug", "day"), [("family-garden", date(2026, 6, 21)),
                                           ("food-forest", date(2026, 9, 21)),
                                           ("raised-bed", date(2026, 9, 21)),
                                           ("balcony", date(2026, 9, 21))])
@pytest.mark.parametrize("folder", ["", "de", "es"])
def test_every_shipped_copy_of_an_example_names_the_same_moment(slug, day, folder):
    assert example_showcase_moment(BUNDLED_EXAMPLES / folder / f"{slug}.ogp") == (day, time(11, 0))


def test_only_a_shipped_example_has_a_showcase_moment(tmp_path: Path):
    # a user's file of the same name, a copy of the folder layout, a locale that does not ship
    assert example_showcase_moment(tmp_path / "family-garden.ogp") is None
    (tmp_path / "de").mkdir()
    assert example_showcase_moment(tmp_path / "de" / "family-garden.ogp") is None
    assert example_showcase_moment(BUNDLED_EXAMPLES / "xx" / "family-garden.ogp") is None
    assert example_showcase_moment(BUNDLED_EXAMPLES / "no-such-example.ogp") is None
    assert example_showcase_moment(BUNDLED_EXAMPLES / "family-garden.meta.json") is None


def test_the_title_follows_the_copys_language_then_the_users():
    base = BUNDLED_EXAMPLES / "family-garden.ogp"
    assert template_title(base) == "Family garden - 24 x 16 m"
    # Russian has a name in the sidecar and no translated plan: the base copy is opened
    assert template_title(base, "ru") == "Семейный сад - 24 x 16 м"
    assert template_title(base, "xx") == "Family garden - 24 x 16 m"
    # a translated copy is named in its own language, whatever the interface speaks
    assert template_title(BUNDLED_EXAMPLES / "de" / "family-garden.ogp", "es") == "Familiengarten - 24 x 16 m"


def test_a_users_template_is_titled_by_its_file(tmp_path: Path):
    assert template_title(tmp_path / "family-garden.ogp", "de") == "family-garden"
