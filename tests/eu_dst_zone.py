"""An EU daylight-saving zone for tests, standard library only.

``ZoneInfo`` needs ``tzdata`` on a bare Windows venv (the repo's locked venv has none), so
the tests that must exercise both clock changes use this rule instead. It is the real EU
rule: +1 h, +2 h from 02:00 on the last Sunday of March to 03:00 on the last Sunday of
October, with the repeated autumn hour selected by ``fold`` and the skipped spring hour
resolved by PEP 495's pre-gap offset.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, tzinfo

__all__ = ["EU_DST", "EuDstZone"]


def _last_sunday(year: int, month: int) -> date:
    day = 31
    while date(year, month, day).weekday() != 6:   # Sunday
        day -= 1
    return date(year, month, day)


class EuDstZone(tzinfo):
    """Europe/Berlin's offset rule without IANA tz data."""

    def _offset(self, wall: datetime, fold: int) -> timedelta:
        day, at = wall.date(), wall.time()
        spring, autumn = _last_sunday(day.year, 3), _last_sunday(day.year, 10)
        if day < spring or day > autumn:
            return timedelta(hours=1)
        if day == spring:
            return timedelta(hours=2 if at >= time(3, 0) else 1)
        if day == autumn:
            if at < time(2, 0):
                return timedelta(hours=2)
            if at < time(3, 0):   # the repeated hour
                return timedelta(hours=2 if fold == 0 else 1)
            return timedelta(hours=1)
        return timedelta(hours=2)

    def utcoffset(self, value: datetime | None) -> timedelta:
        if value is None:
            return timedelta(hours=1)
        return self._offset(value.replace(tzinfo=None), value.fold)

    def dst(self, value: datetime | None) -> timedelta:
        return self.utcoffset(value) - timedelta(hours=1)

    def tzname(self, value: datetime | None) -> str:
        return "CEST" if self.utcoffset(value) >= timedelta(hours=2) else "CET"

    def fromutc(self, value: datetime) -> datetime:
        """UTC -> local for a two-offset rule, with the repeated hour's ``fold``.

        The default ``tzinfo.fromutc`` adds ``dst()`` to the candidate and turns
        01:30 UTC on the autumn day into 03:30 CEST, one hour past the instant; it has no
        notion of which occurrence of a repeated wall time an instant belongs to."""
        utc = value.replace(tzinfo=None)
        for hours in (2, 1):   # the summer offset first: the spring gap prefers it
            offset = timedelta(hours=hours)
            for fold in (0, 1):
                local = (utc + offset).replace(tzinfo=self, fold=fold)
                if self.utcoffset(local) == offset:
                    return local
        return (utc + timedelta(hours=1)).replace(tzinfo=self)


EU_DST = EuDstZone()
