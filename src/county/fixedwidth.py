"""Reader for the county's Oracle SQL*Plus fixed-width spools (CAMA .DAT files).

Framing rules, verified against the 2026-08-31 CAMA export:

- A physical line that starts with a non-blank character begins a record.
- A line that starts with a blank continues the previous record: SQL*Plus
  writes the part of a value that did not fit its column on its own line,
  starting at that column. The text is appended to the field whose span
  contains the line's first non-blank column.
- In tables with ``Layout.wrapped`` columns (DWELL, OBY), the last column did
  not fit the spool line width at all and sits alone on the next line as a
  bare DD-MON-YY date.
- Empty lines separate wrapped records and carry no data.

Values: text is stripped (blank -> None); numbers are right-aligned and may
lack a leading zero (".2900"); '###' means the number overflowed its column
and is unknown (None). Dates are DD-MON-YY (or DD-MON-YYYY).

A row with an unparseable number or date is skipped and counted as bad.
``SpoolReader.check`` rejects the file when more than 1% of rows are bad,
which is how a layout change shows up instead of silently loading garbage.
"""
from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import BinaryIO

ALPHA, NUM, DATE = "A", "N", "D"
YEAR_PIVOT = 40  # two-digit years 00-40 are 2000s, 41-99 are 1900s

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"],
        start=1,
    )
}
_DATE_LINE = re.compile(r"^\d\d-[A-Z]{3}-\d\d(\d\d)?$")


class TooManyBadRows(Exception):
    """A county file had more unparseable rows than the allowed ratio."""


@dataclass(frozen=True)
class Column:
    name: str
    start: int  # 1-based, as in the county's layout documents
    length: int
    kind: str  # ALPHA, NUM or DATE

    @property
    def end(self) -> int:
        """0-based exclusive end offset."""
        return self.start - 1 + self.length


@dataclass(frozen=True)
class Layout:
    table: str
    columns: tuple[Column, ...]
    wrapped: tuple[str, ...] = ()

    @property
    def record_length(self) -> int:
        return max(c.end for c in self.columns)


def parse_date(text: str) -> dt.date | None:
    s = text.strip()
    if not s:
        return None
    parts = s.split("-")
    if len(parts) != 3 or parts[1].upper() not in _MONTHS:
        raise ValueError(f"bad date {text!r}")
    day, month, year_text = int(parts[0]), _MONTHS[parts[1].upper()], parts[2]
    year = int(year_text)
    if len(year_text) == 2:
        year += 2000 if year <= YEAR_PIVOT else 1900
    return dt.date(year, month, day)


def parse_number(text: str) -> int | float | None:
    s = text.strip()
    if not s or set(s) == {"#"}:
        return None
    if "." in s:
        return float(s)
    return int(s)


def decode_lines(stream: BinaryIO) -> Iterator[str]:
    """Yield decoded lines without terminators; splits on LF, drops a trailing CR.

    cp1252 is one byte per character, so fixed-width offsets are preserved.
    """
    for raw in stream:
        yield raw.decode("cp1252", errors="replace").rstrip("\r\n")


class SpoolReader:
    def __init__(self, layout: Layout):
        self.layout = layout
        self.total = 0
        self.bad = 0
        self._by_name = {c.name: c for c in layout.columns}

    def records(self, lines: Iterable[str]) -> Iterator[dict[str, object]]:
        current: list[str] | None = None  # [main line, *overflow lines]
        wrapped_values: list[str] = []
        for text in lines:
            if not text.strip():
                continue
            if self.layout.wrapped and current is not None and _DATE_LINE.match(text.strip()):
                wrapped_values.append(text.strip())
                continue
            if text[0] == " ":
                if current is not None:
                    current.append(text)
                continue
            if current is not None:
                row = self._build(current, wrapped_values)
                if row is not None:
                    yield row
            current, wrapped_values = [text], []
        if current is not None:
            row = self._build(current, wrapped_values)
            if row is not None:
                yield row

    def check(self, max_bad_ratio: float = 0.01) -> None:
        if self.total and self.bad / self.total > max_bad_ratio:
            raise TooManyBadRows(
                f"{self.layout.table}: {self.bad} of {self.total} rows could not be parsed"
            )

    def _build(self, lines: list[str], wrapped_values: list[str]) -> dict[str, object] | None:
        self.total += 1
        main = lines[0].ljust(self.layout.record_length)
        raw = {c.name: main[c.start - 1 : c.end] for c in self.layout.columns}
        for extra in lines[1:]:
            self._merge_overflow(raw, extra)
        for name, value in zip(self.layout.wrapped, wrapped_values, strict=False):
            raw[name] = value
        for name in self.layout.wrapped[len(wrapped_values) :]:
            raw[name] = ""
        try:
            return {name: self._convert(self._by_name[name], value) for name, value in raw.items()}
        except ValueError:
            self.bad += 1
            return None

    def _merge_overflow(self, raw: dict[str, str], extra: str) -> None:
        column_number = len(extra) - len(extra.lstrip(" ")) + 1
        for c in self.layout.columns:
            if c.kind == ALPHA and c.start <= column_number < c.start + c.length:
                raw[c.name] = raw[c.name] + extra[c.start - 1 :].rstrip()
                return

    @staticmethod
    def _convert(column: Column, value: str) -> object:
        if column.kind == NUM:
            return parse_number(value)
        if column.kind == DATE:
            return parse_date(value)
        return value.strip() or None
