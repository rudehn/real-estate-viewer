"""Search normalization shared by ingest (stored keys) and the API (queries).

Stored keys and queries must normalize identically, and prefix search uses a
[prefix, upper bound) range so a plain btree index serves it on both SQLite
and Postgres (LIKE 'x%' cannot use an index on either without extra setup).
"""
import re

_DROP = re.compile(r"[''.]")
_TO_SPACE = re.compile(r"[^A-Z0-9 ]+")
_SPACES = re.compile(r"\s+")
_HOUSE_NUMBER = re.compile(r"^\d+[A-Z]?\s+")
_DIRECTIONS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW"}
_SUFFIXES = {"ST", "AVE", "RD", "DR", "LN", "CT", "PL", "BLVD", "WAY", "PIKE", "CIR", "TER", "PKWY"}


def normalize_search(text: str | None) -> str:
    if not text:
        return ""
    upper = _DROP.sub("", text.upper())
    return _SPACES.sub(" ", _TO_SPACE.sub(" ", upper)).strip()


def parcel_id_key(text: str) -> str:
    return re.sub(r"\s+", "", text).upper()


def prefix_upper_bound(prefix: str) -> str:
    return prefix[:-1] + chr(ord(prefix[-1]) + 1)


def street_key(address: str) -> str:
    """Street part of an address, for "search by street name" matching.

    Drops the house number and a leading direction ("2301 S ARAGON AVE" gives
    "ARAGON AVE"), but keeps a lone direction letter that is the street name
    itself ("120 E ST" gives "E ST").
    """
    rest = _HOUSE_NUMBER.sub("", address.strip())
    parts = rest.split()
    street_named_by_direction = len(parts) == 2 and parts[1] in _SUFFIXES
    if len(parts) >= 2 and parts[0] in _DIRECTIONS and not street_named_by_direction:
        parts = parts[1:]
    return " ".join(parts)
