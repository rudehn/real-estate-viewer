"""Tax district codes: the first 3-4 characters of a parcel id.

Names come from the tax roll's utility rows (src/county/data/tax_districts.json);
about a quarter are blank there, and those fall back to the jurisdiction the
district letter belongs to.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

JURISDICTIONS = {
    "A": "BUTLER TWP", "B": "VANDALIA", "C": "CLAY TWP", "D": "GERMAN TWP",
    "E": "HARRISON TWP", "F": "JACKSON TWP", "G": "JEFFERSON TWP", "H": "TROTWOOD",
    "I": "RIVERSIDE", "J": "MORAINE", "K": "MIAMI TWP", "L": "PERRY TWP",
    "M": "ENGLEWOOD", "N": "KETTERING", "O": "WASHINGTON TWP", "P": "HUBER HEIGHTS",
    "Q": "OAKWOOD", "R": "DAYTON",
}
_SCHOOL = re.compile(r"([A-Z .]*(?:CSD|LSD|EVSD|SD))\s*$")


@lru_cache(maxsize=1)
def _names() -> dict[str, str]:
    path = Path(__file__).parent / "data" / "tax_districts.json"
    return json.loads(path.read_text())


def jurisdiction_name(code: str) -> str:
    return JURISDICTIONS.get(code[:1].upper(), code)


def district_info(code: str) -> tuple[str, str | None]:
    """(name, school district or None) for a tax district code."""
    name = (_names().get(code) or "").strip()
    if not name:
        return (jurisdiction_name(code) if code[:1].upper() in JURISDICTIONS else code), None
    match = _SCHOOL.search(name.split("-")[-1])
    return name, match.group(1).strip() if match else None
