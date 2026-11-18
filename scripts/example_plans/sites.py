"""Where the new example plans lie.

Public city coordinates, never a private garden (ADR-066). Every place is in Central
European Time: the app's clock and a tour's time range read the computer's time zone and
the plan's own zone is not read (#945), so a garden in another zone would show shifted
times on a Central European machine.

The frost dates are illustrative round values for a mild, an average or a harsh site of
the region, in the ``MM-DD`` form the Location dialog writes. They are not climate data
and the plans' hints say so.
"""

from __future__ import annotations


def _site(name, latitude, longitude, timezone, last_spring_frost, first_fall_frost):
    return {"name": name, "latitude": latitude, "longitude": longitude, "timezone": timezone,
            "frost_dates": {"last_spring_frost": last_spring_frost,
                            "first_fall_frost": first_fall_frost}}


SITES = {
    "valencia": _site("Valencia", 39.4699, -0.3763, "Europe/Madrid", "02-01", "12-20"),
    "leipzig": _site("Leipzig", 51.3397, 12.3731, "Europe/Berlin", "04-25", "10-20"),
    "bamberg": _site("Bamberg", 49.8988, 10.9028, "Europe/Berlin", "05-05", "10-12"),
    "cologne": _site("Cologne", 50.9375, 6.9603, "Europe/Berlin", "04-10", "11-05"),
    "munich": _site("Munich", 48.1351, 11.5820, "Europe/Berlin", "05-01", "10-15"),
    "vienna": _site("Vienna", 48.2082, 16.3738, "Europe/Vienna", "04-15", "10-25"),
    "lueneburg": _site("Lüneburg", 53.2464, 10.4115, "Europe/Berlin", "05-05", "10-15"),
    "duesseldorf": _site("Düsseldorf", 51.2277, 6.7735, "Europe/Berlin", "04-10", "11-05"),
    "heidelberg": _site("Heidelberg", 49.3988, 8.6724, "Europe/Berlin", "04-08", "11-01"),
    "bonn": _site("Bonn", 50.7374, 7.0982, "Europe/Berlin", "05-15", "10-15"),
}
