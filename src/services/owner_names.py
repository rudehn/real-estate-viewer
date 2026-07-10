"""Owner-name canonicalization for ranking analytics.

The county records the same entity under many spellings: "DAYTON CITY OF" /
"CITY OF DAYTON", "HUD SEC OF" / "SECRETARY OF HOUSING AND URBAN...", etc.
Rankings grouped by the raw string split those entities and understate them.

Normalization happens in Python *after* SQL aggregation: the ranking
endpoints over-fetch a few multiples of `limit`, merge rows whose
normalized keys match, then truncate. That keeps one source of truth (this
module), needs no schema change or backfill, and is exact for the heads of
the distributions these endpoints return.
"""
import re
from collections.abc import Iterable

# Patterns that identify one well-known institution regardless of spelling.
# Checked against the cleaned (uppercased, de-punctuated) name, in order.
_INSTITUTION_PATTERNS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"HOUSING AND URBAN|HOUSING & URBAN|^HUD\b|\bHUD SEC\b"),
     "US DEPT OF HOUSING & URBAN DEVELOPMENT"),
    (re.compile(r"FEDERAL NATIONAL MORTGAGE|FANNIE MAE"), "FANNIE MAE"),
    (re.compile(r"FEDERAL HOME LOAN MORTGAGE|FREDDIE MAC"), "FREDDIE MAC"),
    (re.compile(r"VETERANS AFFAIRS|VETERANS ADMINISTRATION"),
     "US DEPT OF VETERANS AFFAIRS"),
)

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[.,;:'\"]")


def normalize_owner(name: str) -> str:
    """Return a canonical grouping key for an owner name."""
    cleaned = _WS.sub(" ", _PUNCT.sub(" ", name.upper())).strip()

    for pattern, canonical in _INSTITUTION_PATTERNS:
        if pattern.search(cleaned):
            return canonical

    # County style writes "DAYTON CITY OF" for "CITY OF DAYTON"; rotate the
    # trailing "<UNIT> OF" back to the front so both spellings collide.
    tokens = cleaned.split(" ")
    if len(tokens) >= 3 and tokens[-1] == "OF":
        cleaned = " ".join(tokens[-2:] + tokens[:-2])

    return cleaned


def merge_owner_rows(
    rows: Iterable[dict],
    sum_fields: tuple[str, ...],
    limit: int,
    sort_field: str | None = None,
    name_field: str = "owner_name",
) -> list[dict]:
    """Merge aggregation rows whose owner names normalize to the same entity.

    Each merged row keeps the display name of its largest contributor and
    the sums of `sum_fields`. Result is sorted by `sort_field` (default:
    first sum field) descending and truncated to `limit`.
    """
    merged: dict[str, dict] = {}
    weight_field = sort_field or sum_fields[0]
    for row in rows:
        row = dict(row)
        key = normalize_owner(row[name_field])
        existing = merged.get(key)
        if existing is None:
            merged[key] = row
            continue
        # Keep the display name of the bigger contributor.
        if (row.get(weight_field) or 0) > (existing.get(weight_field) or 0):
            existing[name_field] = row[name_field]
        for f in sum_fields:
            existing[f] = (existing.get(f) or 0) + (row.get(f) or 0)
    ordered = sorted(merged.values(), key=lambda r: r.get(weight_field) or 0, reverse=True)
    return ordered[:limit]
