"""Montgomery County daily tax roll (TAXROLL_YYYYMMDD.zip, one CSV inside).

One row per parcel for the current tax year. Quirks:
- cp1252 text, CRLF line endings, quoted values padded with spaces.
- Numbers are zero-padded and signed ("-000000000109.82"); some are blank.
- Dates are DD-MON-YY spanning 1964-2026.
- FULLYRAMTDUE is the remaining balance, not the bill. The annual net bill is
  the sum over both halves of ADJ + RLBK + HMSD + HMRB + SPASMTS + DAYCRDT
  (verified against GROSSRATE for 99.97% of parcels).
- The file carries columns its layout PDF does not document: CITYNAME,
  OWNOCC, PARCEL LOCATION ZIP, CENSUS TRACT.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import re
import zipfile
from collections.abc import Iterator
from pathlib import Path

from county.fixedwidth import TooManyBadRows, parse_date

BILL_COMPONENTS = ("ADJ", "RLBK", "HMSD", "HMRB", "SPASMTS", "DAYCRDT")
_FILE_DATE = re.compile(r"TAXROLL_(\d{8})", re.IGNORECASE)

REQUIRED_COLUMNS = {
    "PARCELID",
    "TXYR",
    "CLS",
    "LUC",
    "TXDST",
    "NBHD",
    "PARCELLOCATION",
    "OWNERNAME1",
    "OWNERNAME2",
    "MAILINGNAME1",
    "PADDR1",
    "PADDR2",
    "PADDR3",
    "ASMTTOTAL",
    "GROSSRATE",
    "EFFRATE",
    "FRCLSR",
    "AGLAND",
    "NETDELQ",
    "FULLYRAMTDUE",
    "YRBL",
    "SALESDTE",
    "PRICE",
    # Occupancy and abatement flags: read as "Y" or not, so a renamed column
    # would silently turn every parcel's flag off. Required, so it fails loudly.
    "OWNOCC",
    "HMSDFLAG",
    "RENTALREG",
    "AETASMTTOTAL",
    *(f"HLF{h}{c}" for h in (1, 2) for c in BILL_COMPONENTS),
}


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def _number(value: str | None) -> float | None:
    s = (value or "").strip()
    return float(s) if s else None


def _int(value: str | None) -> int | None:
    n = _number(value)
    return int(n) if n is not None else None


def _flag(value: str | None) -> bool:
    return (value or "").strip().upper() == "Y"


def annual_bill(raw: dict[str, str]) -> float:
    total = 0.0
    for half in (1, 2):
        for component in BILL_COMPONENTS:
            total += _number(raw.get(f"HLF{half}{component}")) or 0.0
    return round(total, 2)


def snapshot_date(zip_path: Path) -> dt.date:
    m = _FILE_DATE.search(Path(zip_path).name)
    if not m:
        raise ValueError(f"no date in {zip_path}")
    return dt.datetime.strptime(m.group(1), "%Y%m%d").date()


class TaxRollReader:
    def __init__(self) -> None:
        self.total = 0
        self.bad = 0

    def rows(self, zip_path: Path) -> Iterator[dict]:
        with zipfile.ZipFile(zip_path) as zf:
            (entry,) = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            with zf.open(entry) as fh:
                text = io.TextIOWrapper(fh, encoding="cp1252", errors="replace", newline="")
                reader = csv.reader(text)
                header = [h.strip() for h in next(reader)]
                header_set = set(header)
                missing = REQUIRED_COLUMNS - header_set
                if missing:
                    raise TooManyBadRows(f"TAXROLL: missing columns {', '.join(sorted(missing))}")
                for values in reader:
                    if not any(v.strip() for v in values):
                        continue
                    self.total += 1
                    if len(values) != len(header):
                        self.bad += 1
                        continue
                    try:
                        yield self._convert(dict(zip(header, values, strict=True)))
                    except ValueError:
                        self.bad += 1

    def check(self, max_bad_ratio: float = 0.01) -> None:
        if self.total and self.bad / self.total > max_bad_ratio:
            raise TooManyBadRows(f"TAXROLL: {self.bad} of {self.total} rows could not be parsed")

    @staticmethod
    def _convert(raw: dict[str, str]) -> dict:
        return {
            "parcel_id": raw["PARCELID"].strip(),
            "tax_year": int(raw["TXYR"].strip()),
            "parcel_class": raw["CLS"].strip(),
            "land_use_code": _text(raw["LUC"]),
            "tax_district": _text(raw["TXDST"]),
            "neighborhood": _text(raw["NBHD"]),
            "location": _text(raw["PARCELLOCATION"]),
            "city": _text(raw.get("CITYNAME")),
            "zip": _text(raw.get("PARCEL LOCATION ZIP")),
            "census_tract": _text(raw.get("CENSUS TRACT")),
            "owner_name": _text(raw["OWNERNAME1"]),
            "owner_name2": _text(raw["OWNERNAME2"]),
            "mailing_name": _text(raw["MAILINGNAME1"]),
            "mailing_address1": _text(raw["PADDR1"]),
            "mailing_address2": _text(raw["PADDR2"]),
            "mailing_address3": _text(raw["PADDR3"]),
            "market_value": _number(raw["ASMTTOTAL"]),
            "annual_bill": annual_bill(raw),
            "gross_rate": _number(raw["GROSSRATE"]),
            "effective_rate": _number(raw["EFFRATE"]),
            "owner_occupied": _flag(raw["OWNOCC"]),
            "homestead": _flag(raw["HMSDFLAG"]),
            "rental_registered": _flag(raw["RENTALREG"]),
            "foreclosure_date": parse_date(raw["FRCLSR"]),
            "cauv": (_number(raw["AGLAND"]) or 0) > 0,
            "abated": (_number(raw["AETASMTTOTAL"]) or 0) > 0,
            "net_delinquent": _number(raw["NETDELQ"]),
            "balance_due": _number(raw["FULLYRAMTDUE"]),
            "living_sqft": _int(raw.get("SQ. FT.")),
            "year_built": _int(raw["YRBL"]),
            "last_sale_date": parse_date(raw["SALESDTE"]),
            "last_sale_price": _number(raw["PRICE"]),
        }
