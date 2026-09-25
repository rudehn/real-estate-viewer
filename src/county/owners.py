"""Owner-name heuristics. County owner names are upper case, surname first."""
import re

_GOVERNMENT = re.compile(
    r"\b(CITY OF|COUNTY|STATE OF|VILLAGE OF|TOWNSHIP|TWP|BOARD OF|SCHOOL|LAND REUTILIZATION|"
    r"LAND BANK|HOUSING AUTHORITY|METROPOLITAN HOUSING|SECRETARY OF|HUD|HOUSING AND URBAN|"
    r"UNITED STATES|USA|DEPT OF|DEPARTMENT OF|COMMISSIONERS|CONSERVANCY|PORT AUTHORITY|"
    r"REGIONAL TRANSIT|PARK DISTRICT|FIVE RIVERS)\b"
)
_COMPANY = re.compile(
    r"\b(LLC|L L C|INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LP|LLP|LTD|LIMITED|PARTNERS|"
    r"PARTNERSHIP|HOLDINGS|PROPERTIES|INVESTMENTS|INVESTMENT|REALTY|GROUP|ASSOC|ASSOCIATION|"
    r"BANK|MORTGAGE|FUND|ENTERPRISES|MANAGEMENT|DEVELOPMENT|HOMES|CHURCH|MINISTRIES)\b"
)
_TRUST = re.compile(r"\b(TRUST|TRUSTEE|TRUSTEES|TR|TRS|REVOCABLE|LIVING TRUST)\b")
_STATE_ZIP = re.compile(r"\b([A-Z]{2})\s+\d{5}(?:-\d{4})?\s*$")


def classify_owner_name(name: str | None) -> str | None:
    if not name:
        return None
    upper = re.sub(r"[.,]", " ", name.upper())
    if _GOVERNMENT.search(upper):
        return "government"
    if _TRUST.search(upper):
        return "trust"
    if _COMPANY.search(upper):
        return "company"
    return None


def mailing_state(line: str | None) -> str | None:
    if not line:
        return None
    match = _STATE_ZIP.search(line.upper().strip())
    return match.group(1) if match else None
