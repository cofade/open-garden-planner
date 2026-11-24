"""Extract coordinates from supported map share links."""

import re
from urllib.parse import parse_qs, unquote, urlsplit

_NUMBER = r"[+-]?\d+(?:\.\d+)?"
_PAIR = rf"({_NUMBER}),\s*({_NUMBER})"
_GOOGLE_MAPS_HOSTS = {"google.com", "www.google.com", "maps.google.com"}
_OSM_HOSTS = {"openstreetmap.org", "www.openstreetmap.org"}


def short_map_url(value: str) -> str | None:
    """Build a canonical request URL from a supported short link."""
    try:
        url = urlsplit(value.strip())
        if url.scheme != "https":
            return None
        host = url.netloc.lower()
        pattern = {"maps.app.goo.gl": r"/[A-Za-z0-9_-]{8,64}/?",
                   "maps.apple": r"/p/[A-Za-z0-9_-]{8,64}/?"}.get(host)
        if pattern and re.fullmatch(pattern, url.path):
            return f"https://{host}{url.path}"
    except ValueError:
        pass
    return None


def map_link_coordinates(value: str) -> tuple[float, float] | None:
    """Return latitude/longitude, preferring a Google place over its viewport."""
    value = value.strip()
    match = re.fullmatch(_PAIR, value)
    if match is not None:
        return _valid_pair(match)
    try:
        url = urlsplit(value)
    except ValueError:
        return None
    if url.scheme not in {"http", "https"}:
        return None

    host = url.netloc.lower()
    path = unquote(url.path)
    match = None
    if host in _OSM_HOSTS:
        query = parse_qs(url.query)
        marker = ",".join(query.get(key, [""])[0] for key in ("mlat", "mlon"))
        match = re.fullmatch(_PAIR, marker)
        if match is None or _valid_pair(match) is None:
            match = re.search(rf"(?:^|&)map=\d+(?:\.\d+)?/({_NUMBER})/({_NUMBER})(?=&|$)", url.fragment)
    elif host == "maps.apple.com":
        match = _query_coordinates(url.query, ("coordinate", "destination", "daddr", "ll", "sll", "center", "q"))
    elif host in _GOOGLE_MAPS_HOSTS or host == "earth.google.com":
        if host in _GOOGLE_MAPS_HOSTS:
            match = re.search(rf"!3d({_NUMBER})!4d({_NUMBER})(?=!|$)", path)
            if match is None:
                match = _query_coordinates(url.query, ("query", "q", "ll", "center"))
        if match is None:
            match = re.search(rf"@{_PAIR}(?=,|/|$)", path)

    return _valid_pair(match) if match is not None else None


def _query_coordinates(query: str, keys: tuple[str, ...]) -> re.Match[str] | None:
    values = parse_qs(query)
    for key in keys:
        for entry in values.get(key, []):
            match = re.fullmatch(_PAIR, entry.strip())
            if match is not None and _valid_pair(match) is not None:
                return match
    return None


def _valid_pair(match: re.Match[str]) -> tuple[float, float] | None:
    lat, lon = float(match[1]), float(match[2])
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        return lat, lon
    return None
