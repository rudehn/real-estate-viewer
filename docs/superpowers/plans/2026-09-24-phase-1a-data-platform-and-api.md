# Phase 1A: Data Platform and /v2 API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest the county's CAMA and tax roll data into new tables, build the per-parcel summary and map binary, and expose everything the new frontend needs through a `/v2` API, while the old endpoints keep working.

**Architecture:** New county readers (`src/county/`) parse the fixed-width CAMA spools and the tax roll CSV straight from their zip files. Ingest steps (`src/ingest/`) load them into new SQLModel tables in single transactions, and a derived step (`src/derived/`) rebuilds `parcel_summary`, `neighborhood_summary`, the map binary, and a `data_version`. Query logic lives in `src/services/analytics/`: new `/v2` queries are written there, and old `/analytics` route bodies that `/v2` also needs are moved there so both share them (the old routes become thin wrappers that plan 1B deletes).

**Tech Stack:** Python 3.12+, FastAPI, SQLModel/SQLAlchemy 2 async, aiosqlite (dev/test) and asyncpg (prod Postgres), httpx, pyproj, pytest + pytest-asyncio, ruff, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-24-map-centric-redesign-design.md` (sections 2, 3, 6, 7, 9, 10, 11). Data source details: `docs/data-sources/README.md` and the reports it links.

This is plan 1 of 2 for phase 1. Plan 1B (frontend) consumes the `/v2` API built here. Phases 2-4 get their own plans after phase 1 ships.

## Global Constraints

- Prod never runs alembic: new tables come from `SQLModel.metadata.create_all`; new columns on existing tables are added by idempotent repairs in `src/db/maintenance.py` (spec 6.5).
- All SQL must run on both SQLite and Postgres. Date math goes through `src/db/sqlutil.py`. Use `//` (not `/`) for integer division in SQLAlchemy expressions. Medians use the row_number/count window pattern already in `get_market_stats` (no `percentile_cont`).
- County text is cp1252. Never decode it as UTF-8 and never use `str.splitlines()` on county data (it splits on characters the county uses inside fields).
- Two-digit years: `00`-`40` mean 2000-2040, `41`-`99` mean 1941-1999 (`YEAR_PIVOT = 40`).
- A county file with more than 1% bad rows is rejected and its ingest step fails (spec 6.5).
- Full-refresh tables are replaced inside one database transaction, so a failed load leaves the previous data intact.
- Homestead data is stored only as flags or type codes, never applicant names, addresses or notes.
- Existing DB columns `transaction.assessed_*` hold 100% market value and `taxable_*` hold the 35% value; do not rename them. `/v2` responses call them `market_value` and `assessed_value_35pct`.
- New routes live under `/v2`. Old routes stay working (and tested) until plan 1B deletes them.
- Every `/v2` list or aggregate response includes `applied_filters: list[str]`, the filter names that endpoint honored.
- `/v2` errors use `{"error": {"code": str, "message": str}}`; unknown parcels and owners return 404; invalid filters return 422.
- Commit messages never include an agent co-author line. Never use the em dash character in code, comments, docs or commit messages.
- Lint must pass: `uv run ruff check src tests scripts`.

## Review Focus

1. A county file whose layout shifts (new column, changed width) must fail loudly instead of loading garbage: the 1% bad-row rule rejects it and the previous data stays. Pinned in Task 2 (`test_check_raises_when_too_many_bad_rows`) and Task 8 (`test_failed_ingest_leaves_previous_rows`).
2. Parcels that appear in sales history but no longer exist in CAMA (retired or combined IDs) must stay browsable: marked `is_active = false`, profile still returns their sales with "no dwelling on record". Pinned in Task 8 (`test_parcels_missing_from_cama_are_marked_inactive`) and Task 17 (`test_profile_of_inactive_parcel_without_cama_data`).
3. Search input with lowercase, extra spaces, punctuation or apostrophes (`"  6617 pheasant "`, `"o'neil"`, `"r72 00304"`) must normalize and return results without SQL errors. Pinned in Task 16 (`test_search_normalizes_messy_input`).
4. Contradictory or extreme filters (`price_min > price_max`, `year_built_min` in the future) must return a readable 422, and filters that match nothing must return empty results with zero totals, not errors. Pinned in Task 15 (`test_contradictory_filters_return_422`) and Task 19 (`test_filters_matching_nothing_return_zeros`).
5. Parcels with two or more dwellings must sum living area, beds and baths instead of showing only one card. Pinned in Task 12 (`test_summary_sums_multiple_dwellings`).

## File Structure

Created:

| File | Responsibility |
|---|---|
| `src/county/__init__.py` | Package marker |
| `src/county/fixedwidth.py` | Generic reader for the county's SQL*Plus fixed-width spools: framing, value parsing, bad-row accounting |
| `src/county/cama.py` | CAMA table layouts, zip entry access, code decodes, neighborhood names from `NBHD.DAT` |
| `src/county/taxroll.py` | Tax roll CSV reader and annual bill calculation |
| `src/county/neighborhood_codes.py` | Parser for the county's monthly neighborhood-codes HTML |
| `src/county/coords.py` | Ohio State Plane South (EPSG:3735) to WGS84 conversion |
| `src/county/tax_districts.py` + `src/county/data/tax_districts.json` | Tax district names and school districts |
| `src/county/sources.py` | Listing and downloading county files |
| `src/county/owners.py` | Owner-name classification (government, company, trust) and mailing-state parsing |
| `src/county/text.py` | Search normalization shared by ingest and API |
| `src/db/county_models.py` | New tables: `ParcelDetail`, `Dwelling`, `ParcelFeature`, `ParcelValue`, `Neighborhood`, `TaxDistrict`, `ParcelTax`, `ParcelSummary`, `NeighborhoodSummary`, `DataVersion` |
| `src/ingest/__init__.py` | Package marker |
| `src/ingest/bulk.py` | Chunked insert and replace-in-one-transaction helpers |
| `src/ingest/cama_ingest.py` | CAMA zip to `parcel`, `parcel_detail`, `dwelling`, `parcel_feature`, `parcel_value`, `neighborhood` |
| `src/ingest/taxroll_ingest.py` | Tax roll zip to `parcel_tax` |
| `src/ingest/neighborhood_ingest.py` | Neighborhood names HTML and tax districts to `neighborhood` and `tax_district` |
| `src/derived/__init__.py` | Package marker |
| `src/derived/summary.py` | Builds `parcel_summary` and `neighborhood_summary`, bumps `data_version` |
| `src/derived/mapbinary.py` | Encodes `parcel_summary` into the columnar map binary |
| `src/services/analytics/__init__.py` | Package marker |
| `src/services/analytics/{market,sales,neighborhoods,owners,distress,parcels,search,comps}.py` | Query logic shared by old and new routes |
| `src/api/__init__.py` | Builds the `/v2` router |
| `src/api/errors.py` | Error shape and exception handlers |
| `src/api/filters.py` | Shared filter model, validation, `applied_filters` |
| `src/api/cache.py` | In-process cache keyed by `data_version` |
| `src/api/routers/{meta,map,search,parcels,sales,market,neighborhoods,owners,investors,distress}.py` | `/v2` endpoints |
| `scripts/build_cama_fixture.py`, `scripts/build_taxroll_fixture.py` | Cut small real fixtures out of full county files |
| `scripts/export_openapi.py` | Writes `openapi.json` for frontend type generation |
| `scripts/verify_real_data.py` | End-to-end ingest of real county files with coverage and latency checks |
| `tests/fixtures/county/*` | Committed fixture files |
| `.github/workflows/test.yml` | CI for backend tests on SQLite and Postgres |

Modified:

| File | Change |
|---|---|
| `pyproject.toml` | Add `pyproj` |
| `src/db/models.py` | New `Parcel` columns |
| `src/db/maintenance.py` | Add new `parcel` columns on existing databases |
| `src/services/populate.py` | New ingest and derived steps |
| `src/main.py` | Old routes delegate to `services/analytics`; mount `/v2`; register error handlers |
| `tests/conftest.py` | `db_engine` fixture; Postgres support through `TEST_DATABASE_URL` |

## Fixture parcels

Tests use four real parcels cut from the 2026-08-31 CAMA export and the 2026-09-23 tax roll. Their true values (verified while writing this plan):

| Parcel | Why it is in the fixture | Key values |
|---|---|---|
| `A01 00101 0001` | Rural Butler Twp house, multi-line land, 1919 placeholder year | DWELL sfla 2464, yrblt 1919, beds 3, baths 1/0, style 05 OLD STYLE, grade C+, cdu VG, heat 3, fuel 4 (OIL), bsmt 3 (PART), extwall 1 (FRAME); LAND acres 0.29+0.71+1.0; LEGDAT x 1470869 y 704667 (lat 39.92128, lon -84.27433); APRVAL 73980/200340/274320; ASMT apr 85370/182190, reascd J; OBY RG1 768 sq ft (24x32), AL1; PARDAT 11974 FREDERICK PIKE, nbhd 48150000, luc 511; tax roll bill 6066.22, OWNOCC Y, census 39113-110100-1, last sale 2023-03-20 $320,000 |
| `A01 00102 0069` | Two dwellings (cards 1 and 2); app DB has latitude 0.0 | DWELL card 1 sfla 1770 beds 3 baths 1/1 yrblt 1985; card 2 sfla 720 beds 2 baths 1/0 yrblt 1970; ADDN card 2 line 1 code 13 area 552 (attached garage); PARDAT 920 ANTIOCH SCHOOL RD |
| `N64 00101 0003` | Kettering ranch with attached garage | DWELL sfla 1008, yrblt 1955, style 03 RANCH, heat 4 (central A/C); ADDN line 1 code 13 area 384; PARDAT 2301 S ARAGON AVE, nbhd 15007000, luc 510; APRVAL 26050/99200/125250; ASMT apr 30000/118670 |
| `R72 00304 0025` | Dayton, detached garage, TIF, dwelling on card 2 only | DWELL card 2 sfla 5103, yrblt 1890, style 20, grade A; OBY RS1 192 sq ft, RG1 960 sq ft (40x24); LEGDAT x 1491599 y 646501 (lat 39.76272, lon -84.19654); APRVAL 149460/101810/251270, revreas TIF, revcode 3; PARDAT 208 W MONUMENT AVE, nbhd 3100WALK |

---

### Task 1: Development environment, dependencies and CI

**Files:**
- Modify: `pyproject.toml`
- Modify: `tests/conftest.py`
- Create: `.github/workflows/test.yml`
- Test: `tests/test_conftest_engine.py`

**Interfaces:**
- Produces: pytest fixture `db_engine` (an `AsyncEngine` with all tables created, torn down after the test) and `TEST_DB_URL` read from the `TEST_DATABASE_URL` environment variable (default: a SQLite file under `tmp_path`). Every later task's ingest tests use `db_engine`.

- [ ] **Step 1: Recreate the virtual environment**

The committed `.venv` was copied from another project and its script shebangs point at a missing path.

```bash
rm -rf .venv
uv sync
uv run python -c "import fastapi, sqlmodel; print('ok')"
```
Expected: `ok`

- [ ] **Step 2: Add pyproj**

```bash
uv add "pyproj>=3.7"
```
Expected: `pyproject.toml` lists `pyproj>=3.7` under `dependencies` and `uv.lock` updates.

- [ ] **Step 3: Write the failing test for the new fixture**

Create `tests/test_conftest_engine.py`:

```python
from sqlalchemy import inspect


async def test_db_engine_has_all_tables(db_engine):
    async with db_engine.connect() as conn:
        tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
    assert {"parcel", "transaction", "datafile"} <= tables
```

- [ ] **Step 4: Run it to verify it fails**

Run: `uv run pytest tests/test_conftest_engine.py -v`
Expected: FAIL with `fixture 'db_engine' not found`

- [ ] **Step 5: Add the fixture and Postgres support to `tests/conftest.py`**

Replace the top of `tests/conftest.py` (imports and `TEST_DB_URL`) and add the `db_engine` fixture. Keep the existing `session` and `client` fixtures, but make `session` use `_engine_url(tmp_path)` too:

```python
import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import db.county_models  # noqa: F401  (registers the new tables with SQLModel.metadata)
from db.engine import get_session
from main import app


def _engine_url(tmp_path) -> str:
    """Postgres when TEST_DATABASE_URL is set (CI), else a throwaway SQLite file.

    A file rather than :memory: so several connections share one database.
    """
    return os.getenv("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{tmp_path}/test.db"


@pytest.fixture
async def db_engine(tmp_path):
    engine = create_async_engine(_engine_url(tmp_path))
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def session(db_engine):
    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as s:
        yield s
```

`import db.county_models` will fail until Task 7 creates it. Create an empty placeholder module now so the import resolves:

```bash
mkdir -p src/db && printf '"""County tables (filled in by Task 7)."""\n' > src/db/county_models.py
```

- [ ] **Step 6: Run the new test and the whole suite**

Run: `uv run pytest -q`
Expected: all tests PASS, including `test_db_engine_has_all_tables`.

- [ ] **Step 7: Add the CI workflow**

Create `.github/workflows/test.yml`:

```yaml
name: test

on:
  push:
    branches: [master, redesign]
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        db: [sqlite, postgres]
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U test" --health-interval 5s
          --health-timeout 5s --health-retries 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - run: uv run ruff check src tests scripts
      - name: pytest (sqlite)
        if: matrix.db == 'sqlite'
        run: uv run pytest -q
      - name: pytest (postgres)
        if: matrix.db == 'postgres'
        env:
          # db.engine and db.sqlutil read DATABASE_URL to pick the dialect;
          # the test fixtures read TEST_DATABASE_URL. Point both at Postgres.
          TEST_DATABASE_URL: postgresql+asyncpg://test:test@localhost:5432/test
          DATABASE_URL: postgresql+asyncpg://test:test@localhost:5432/test
        run: uv run pytest -q
```

- [ ] **Step 8: Run the suite against Postgres locally**

```bash
docker run -d --rm --name rev-pg -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test \
  -e POSTGRES_DB=test -p 55432:5432 postgres:16
sleep 5
TEST_DATABASE_URL=postgresql+asyncpg://test:test@localhost:55432/test \
DATABASE_URL=postgresql+asyncpg://test:test@localhost:55432/test \
  uv run pytest -q
```
Expected: all tests PASS. The suite has only ever run on SQLite, so an existing test may assume SQLite (for example querying `sqlite_master`). Fix any such test so it passes on both dialects, in this task, before moving on. Keep the container running for later tasks, or stop it with `docker stop rev-pg`.

- [ ] **Step 9: Run lint**

Run: `uv run ruff check src tests scripts`
Expected: `All checks passed!`

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml uv.lock tests/conftest.py tests/test_conftest_engine.py src/db/county_models.py .github/workflows/test.yml
git commit -m "Add pyproj, a shared db_engine test fixture and a CI test workflow"
```

---

### Task 2: Fixed-width spool reader

**Files:**
- Create: `src/county/__init__.py`, `src/county/fixedwidth.py`
- Test: `tests/county/__init__.py`, `tests/county/test_fixedwidth.py`

**Interfaces:**
- Produces:
  - `Column(name: str, start: int, length: int, kind: str)` with `kind` one of `ALPHA`, `NUM`, `DATE`; `start` is 1-based.
  - `Layout(table: str, columns: tuple[Column, ...], wrapped: tuple[str, ...] = ())`; `wrapped` names columns that SQL*Plus moved onto their own continuation line (always a bare date).
  - `SpoolReader(layout)` with `records(lines: Iterable[str]) -> Iterator[dict[str, object]]`, counters `total` and `bad`, and `check(max_bad_ratio: float = 0.01) -> None` raising `TooManyBadRows`.
  - `decode_lines(stream: BinaryIO) -> Iterator[str]`: splits on CRLF or LF and decodes cp1252.
  - `parse_date(text: str) -> date | None`, `parse_number(text: str) -> int | float | None` (both raise `ValueError` on malformed input).
  - Row values: alpha fields are stripped `str` or `None` when blank; numbers are `int`/`float`/`None` (`###` overflow is `None`); dates are `datetime.date`/`None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/county/__init__.py` (empty) and `tests/county/test_fixedwidth.py`:

```python
import datetime as dt
import io

import pytest

from county.fixedwidth import (
    ALPHA,
    DATE,
    NUM,
    Column,
    Layout,
    SpoolReader,
    TooManyBadRows,
    decode_lines,
    parse_date,
    parse_number,
)

# parid 1-14, qty 15-19, name 20-29, when 30-38
LAYOUT = Layout(
    "T",
    (
        Column("parid", 1, 14, ALPHA),
        Column("qty", 15, 5, NUM),
        Column("name", 20, 10, ALPHA),
        Column("when", 30, 9, DATE),
    ),
)
WRAPPED = Layout(
    "W",
    (
        Column("parid", 1, 14, ALPHA),
        Column("qty", 15, 5, NUM),
        Column("wen", 20, 9, DATE),
    ),
    wrapped=("wen",),
)


def line(parid="A01 00101 0001", qty="   12", name="SMITH     ", when="02-JAN-25"):
    return f"{parid:<14}{qty:>5}{name:<10}{when}"


def test_parses_one_record():
    rows = list(SpoolReader(LAYOUT).records([line()]))
    assert rows == [
        {"parid": "A01 00101 0001", "qty": 12, "name": "SMITH", "when": dt.date(2025, 1, 2)}
    ]


def test_blank_values_become_none():
    rows = list(SpoolReader(LAYOUT).records([line(qty="     ", name=" " * 10, when="")]))
    assert rows[0]["qty"] is None
    assert rows[0]["name"] is None
    assert rows[0]["when"] is None


def test_overflow_marker_is_none_not_bad():
    reader = SpoolReader(LAYOUT)
    rows = list(reader.records([line(qty="  ###")]))
    assert rows[0]["qty"] is None
    assert reader.bad == 0


def test_short_lines_are_padded():
    rows = list(SpoolReader(LAYOUT).records(["A01 00101 0001   12SMITH"]))
    assert rows[0]["name"] == "SMITH"
    assert rows[0]["when"] is None


def test_overflow_continuation_line_is_merged_into_its_field():
    # The value was cut at the field width; the rest sits on a blank-led line
    # starting at the field's own column.
    first = line(name="SETTLERS W")
    continuation = " " * 19 + "ALK"
    rows = list(SpoolReader(LAYOUT).records([first, continuation, ""]))
    assert len(rows) == 1
    assert rows[0]["name"] == "SETTLERS WALK"


def test_wrapped_date_column_is_read_from_its_own_line():
    first = "A01 00101 0001   12"
    rows = list(SpoolReader(WRAPPED).records([first, "02-JAN-25", "", first, "15-MAR-64", ""]))
    assert [r["wen"] for r in rows] == [dt.date(2025, 1, 2), dt.date(1964, 3, 15)]


def test_blank_lines_are_ignored():
    rows = list(SpoolReader(LAYOUT).records(["", line(), "   ", line(parid="A01 00101 0002")]))
    assert [r["parid"] for r in rows] == ["A01 00101 0001", "A01 00101 0002"]


def test_bad_rows_are_skipped_and_counted():
    reader = SpoolReader(LAYOUT)
    rows = list(reader.records([line(), line(qty=" 1x2 "), line(when="99-ZZZ-99")]))
    assert len(rows) == 1
    assert (reader.total, reader.bad) == (3, 2)


def test_check_raises_when_too_many_bad_rows():
    reader = SpoolReader(LAYOUT)
    lines = [line() for _ in range(98)] + [line(qty="  abc"), line(qty="  abc")]
    list(reader.records(lines))
    with pytest.raises(TooManyBadRows, match="T: 2 of 100 rows"):
        reader.check()


def test_check_passes_at_one_percent():
    reader = SpoolReader(LAYOUT)
    list(reader.records([line() for _ in range(99)] + [line(qty="  abc")]))
    reader.check()


def test_parse_date_pivot_and_formats():
    assert parse_date("02-JAN-25") == dt.date(2025, 1, 2)
    assert parse_date("31-DEC-40") == dt.date(2040, 12, 31)
    assert parse_date("01-JAN-41") == dt.date(1941, 1, 1)
    assert parse_date("15-MAR-1964") == dt.date(1964, 3, 15)
    assert parse_date("  ") is None
    with pytest.raises(ValueError):
        parse_date("2025-01-02")


def test_parse_number():
    assert parse_number("  42") == 42
    assert parse_number(".2900") == 0.29
    assert parse_number("-000000000109.82") == -109.82
    assert parse_number("###") is None
    assert parse_number("") is None
    with pytest.raises(ValueError):
        parse_number("12a")


def test_decode_lines_handles_crlf_and_cp1252():
    raw = b"O\x92NEIL\r\nSECOND\nTHIRD\r\n"
    assert list(decode_lines(io.BytesIO(raw))) == ["O’NEIL", "SECOND", "THIRD"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/county/test_fixedwidth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'county'`

- [ ] **Step 3: Implement `src/county/fixedwidth.py`**

Create `src/county/__init__.py` containing `"""Readers for Montgomery County public data files."""` and `src/county/fixedwidth.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/county/test_fixedwidth.py -v`
Expected: all 13 tests PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/county tests/county
git commit -m "Add a reader for the county's fixed-width SQL*Plus spools"
```

---

### Task 3: CAMA tables, decodes and fixture

**Files:**
- Create: `src/county/cama.py`
- Create: `scripts/build_cama_fixture.py`
- Create: `tests/fixtures/county/cama_fixture.zip` (generated in Step 2)
- Test: `tests/county/test_cama.py`

**Interfaces:**
- Consumes: `Column`, `Layout`, `SpoolReader`, `decode_lines`, `ALPHA`, `NUM`, `DATE` from Task 2.
- Produces:
  - `LAYOUTS: dict[str, Layout]` for `PARDAT`, `LAND`, `LEGDAT`, `DWELL`, `ADDN`, `OBY`, `APRVAL`, `ASMT`, `NBHD`.
  - `table_lines(zip_path: Path, table: str) -> Iterator[str]` (context-managed generator over the zip entry ending in `\TABLE.DAT` or `/TABLE.DAT`).
  - `read_table(zip_path: Path, table: str) -> tuple[SpoolReader, Iterator[dict]]`.
  - `Decodes` with `label(table: str, field: str, code: str | None) -> str | None`, `outbuilding(code) -> str | None`, `grade(code) -> str | None`, `heat(code) -> str | None`; built by `load_decodes(zip_path) -> Decodes`.
  - `neighborhood_names(zip_path: Path) -> dict[str, str]`.
  - `snapshot_date(zip_path: Path) -> date` parsed from the entry names (`Cama_Files_20260831\...` gives 2026-08-31).

- [ ] **Step 1: Write the fixture builder**

Create `scripts/build_cama_fixture.py`:

```python
"""Cut a small CAMA fixture zip out of a full county export.

Usage:
    uv run python scripts/build_cama_fixture.py SRC.zip DEST.zip PARID [PARID ...]

Copies every physical line (including wrapped and overflow continuation lines)
of each record whose parcel id is listed, for the data tables the ingest uses.
Lookup tables are copied whole. NBHD keeps the codes used by the chosen
parcels plus the first record that has an overflow continuation line, so the
fixture exercises that framing rule. Entry names are kept exactly.
"""
import sys
import zipfile

DATA_TABLES = ("PARDAT", "LAND", "LEGDAT", "DWELL", "ADDN", "OBY", "APRVAL", "ASMT")
WHOLE_TABLES = ("AEDIT", "GRADE", "HEAT", "RCOBY")


def entry_for(names: list[str], table: str) -> str:
    return next(n for n in names if n.replace("\\", "/").endswith(f"/{table}.DAT"))


def records(raw: bytes):
    """Split a spool into records.

    A record starts on a line beginning with a letter (parcel ids start with a
    district letter, NBHD lines with "PARDAT"). Blank-led overflow lines, bare
    DD-MON-YY wrapped-date lines and empty lines belong to the current record.
    """
    record: list[bytes] = []
    for line in raw.split(b"\n"):
        if line[:1].isalpha() and record:
            yield record
            record = []
        record.append(line)
    if record:
        yield record


def main(src: str, dest: str, parids: list[str]) -> None:
    wanted = {p.encode() for p in parids}
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zout:
        names = zin.namelist()
        nbhds: set[bytes] = set()
        for table in DATA_TABLES:
            entry = entry_for(names, table)
            kept: list[bytes] = []
            for record in records(zin.read(entry)):
                if record[0][:30].rstrip() in wanted:
                    kept.extend(record)
                    if table == "PARDAT":
                        nbhds.add(record[0][226:234].rstrip())
            zout.writestr(entry, b"\n".join(kept) + b"\n")
        for table in WHOLE_TABLES:
            entry = entry_for(names, table)
            zout.writestr(entry, zin.read(entry))
        entry = entry_for(names, "NBHD")
        kept, took_overflow = [], False
        for record in records(zin.read(entry)):
            code = record[0][12:21].rstrip()
            has_overflow = any(line.strip() for line in record[1:])
            if code in nbhds or (has_overflow and not took_overflow):
                kept.extend(record)
                took_overflow = took_overflow or has_overflow
        zout.writestr(entry, b"\n".join(kept) + b"\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
```

- [ ] **Step 2: Download the source export and build the fixture**

The county keeps monthly CAMA files for years, so this exact file stays available.

```bash
mkdir -p /tmp/county
curl -fL -A "Mozilla/5.0" -o /tmp/county/Cama_Files_20260831.zip \
  "https://go.mcohio.org/applications/treasurer/search/data/Cama/Cama_Files_20260831.zip"
mkdir -p tests/fixtures/county
uv run python scripts/build_cama_fixture.py /tmp/county/Cama_Files_20260831.zip \
  tests/fixtures/county/cama_fixture.zip \
  "A01 00101 0001" "A01 00102 0069" "N64 00101 0003" "R72 00304 0025"
ls -la tests/fixtures/county/cama_fixture.zip
```
Expected: a zip of well under 1 MB.

- [ ] **Step 3: Write the failing tests**

Create `tests/county/test_cama.py`:

```python
import datetime as dt
from pathlib import Path

import pytest

from county import cama

FIXTURE = Path(__file__).parent.parent / "fixtures" / "county" / "cama_fixture.zip"


def rows(table):
    reader, it = cama.read_table(FIXTURE, table)
    out = list(it)
    reader.check()
    assert reader.bad == 0
    return out


def by_parcel(table):
    out: dict[str, list[dict]] = {}
    for r in rows(table):
        out.setdefault(r["parid"], []).append(r)
    return out


def test_snapshot_date():
    assert cama.snapshot_date(FIXTURE) == dt.date(2026, 8, 31)


def test_dwell_single_card():
    (d,) = by_parcel("DWELL")["A01 00101 0001"]
    assert (d["card"], d["sfla"], d["yrblt"], d["rmbed"], d["fixbath"], d["fixhalf"]) == (
        1, 2464, 1919, 3, 1, 0
    )
    assert (d["style"], d["grade"], d["cdu"], d["heat"], d["fuel"], d["bsmt"]) == (
        "05", "C+", "VG", "3", "4", "3"
    )
    # "wen" is wrapped onto its own line by SQL*Plus.
    assert isinstance(d["wen"], dt.date)


def test_dwell_two_cards():
    cards = sorted(by_parcel("DWELL")["A01 00102 0069"], key=lambda d: d["card"])
    assert [(d["card"], d["sfla"], d["rmbed"]) for d in cards] == [(1, 1770, 3), (2, 720, 2)]


def test_addn_attached_garage_line():
    lines = {r["lline"]: r for r in by_parcel("ADDN")["N64 00101 0003"]}
    assert (lines[1]["first"], lines[1]["area"]) == ("13", 384)
    assert lines[0]["vect"] == "A0CU24R42D24L42"


def test_oby_detached_garage():
    items = {r["code"]: r for r in by_parcel("OBY")["R72 00304 0025"]}
    assert set(items) == {"RS1", "RG1"}
    assert (items["RG1"]["area"], items["RG1"]["meas1"], items["RG1"]["meas2"]) == (960, 40, 24)


def test_land_lines():
    acres = sorted(r["acres"] for r in by_parcel("LAND")["A01 00101 0001"])
    assert acres == pytest.approx([0.29, 0.71, 1.0])


def test_legdat_coordinates():
    (r,) = by_parcel("LEGDAT")["A01 00101 0001"]
    assert (r["xcoord"], r["ycoord"], r["taxdist"]) == (1470869, 704667, "A01")


def test_values():
    (apr,) = by_parcel("APRVAL")["R72 00304 0025"]
    assert (apr["aprland"], apr["aprbldg"], apr["aprtot"], apr["revreas"]) == (
        149460, 101810, 251270, "TIF"
    )
    (asmt,) = by_parcel("ASMT")["A01 00101 0001"]
    assert (asmt["aprland"], asmt["aprbldg"], asmt["reascd"]) == (85370, 182190, "J")


def test_pardat_situs_and_codes():
    (p,) = by_parcel("PARDAT")["N64 00101 0003"]
    assert (p["adrno"], p["adrdir"], p["adrstr"], p["adrsuf"]) == (2301, "S", "ARAGON", "AVE")
    assert (p["nbhd"], p["luc"], p["class"]) == ("15007000", "510", "R")


def test_decodes():
    decodes = cama.load_decodes(FIXTURE)
    assert decodes.label("DWELDAT", "STYLE", "05") == "OLD STYLE"
    assert decodes.label("DWELDAT", "CDU", "VG") == "VERY GOOD"
    assert decodes.label("DWELDAT", "EXTWALL", "1") == "FRAME"
    assert decodes.label("DWELDAT", "FUEL", "4") == "OIL"
    assert decodes.label("ASMT", "LUC", "511").startswith("R - ")
    assert decodes.label("DWELDAT", "STYLE", None) is None
    assert decodes.label("DWELDAT", "STYLE", "ZZ") is None
    assert decodes.heat("4") == "CENTRAL A/C"
    assert decodes.grade("C+") == "AVERAGE +"
    assert decodes.outbuilding("RG1") == "FRAME OR CB DETACHED GARAGE"


def test_neighborhood_names():
    names = cama.neighborhood_names(FIXTURE)
    assert names["48150000"] == "N BUTLER TWP"
    assert "15007000" in names
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run pytest tests/county/test_cama.py -v`
Expected: FAIL with `ImportError: cannot import name 'cama'`

- [ ] **Step 5: Implement `src/county/cama.py`**

The layouts are copied from the verified prototype parsers in `docs/data-sources/prototype-parsers/` (`cama_parse.py` `SPECS` for `DWELL`, `PARDAT`, `LAND`, `OBY`, `ADDN`; `cama_values_parse.py` `LAYOUTS` for `LEGDAT`, `ASMT`, `APRVAL`, `NBHD`). They include the corrections where the county's PDF is wrong (DWELL heat width, OBY offsets, ADDN date order); see `docs/data-sources/cama-building-column-maps.md`.

```python
"""Montgomery County CAMA export (monthly Cama_Files_YYYYMMDD.zip).

Layouts come from the county's "AA407 Data File Description" PDF with the
corrections verified against the 2026-08-31 export (see
docs/data-sources/cama-building-column-maps.md). Only the tables the ingest
uses are defined here.
"""
from __future__ import annotations

import datetime as dt
import re
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from county.fixedwidth import ALPHA as A
from county.fixedwidth import DATE as D
from county.fixedwidth import NUM as N
from county.fixedwidth import Column, Layout, SpoolReader, decode_lines


def _layout(table: str, spec: list[tuple[str, int, int, str]], wrapped=()) -> Layout:
    return Layout(table, tuple(Column(*c) for c in spec), tuple(wrapped))


LAYOUTS: dict[str, Layout] = {
    "DWELL": _layout("DWELL", [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("card", 37, 5, N),
        ("taxyr", 42, 5, N), ("seq", 47, 4, N), ("stories", 51, 4, N),
        ("extwall", 55, 2, A), ("style", 57, 2, A), ("yrblt", 59, 5, N),
        ("yrremod", 64, 5, N), ("rmtot", 69, 3, N), ("rmbed", 72, 3, N),
        ("rmfam", 75, 2, N), ("fixbath", 77, 3, N), ("fixhalf", 80, 3, N),
        ("fixaddl", 83, 3, N), ("fixtot", 86, 3, N), ("remkit", 89, 1, A),
        ("rembath", 90, 1, A), ("bsmt", 91, 1, A),
        # The PDF says heat is 1 wide; the data has 2, shifting all later columns by 1.
        ("heat", 92, 2, A), ("heatsys", 94, 1, A), ("fuel", 95, 1, A),
        ("grade", 96, 3, A), ("class", 99, 4, A), ("cddesc", 103, 2, A),
        ("attic", 105, 1, A), ("intext", 106, 1, A), ("unitno", 107, 10, A),
        ("rectype", 117, 1, A), ("flr1area", 118, 8, N), ("mastrimarea", 126, 7, N),
        ("unfinarea", 133, 7, N), ("recromarea", 140, 7, N),
        ("finbsmtarea", 147, 7, N), ("condovw", 154, 3, A),
        ("cndcmplx", 157, 30, A), ("cline", 187, 5, N), ("wbfp_o", 192, 3, N),
        ("wbfp_s", 195, 3, N), ("wbfp_pf", 198, 2, N), ("bsmtcar", 200, 2, N),
        ("msc1des", 202, 2, A), ("msc1num", 204, 3, N), ("msc2des", 207, 2, A),
        ("msc2num", 209, 3, N), ("condolvl", 212, 3, N),
        ("condotyp", 215, 4, A), ("mgfa", 219, 7, N), ("cdpct", 226, 4, N),
        ("cdu", 230, 2, A), ("depr", 232, 4, N), ("addnval", 236, 11, N),
        ("addnarea", 247, 7, N), ("adjarea", 254, 7, N),
        ("areafact", 261, 8, N), ("atticval", 269, 9, N),
        ("bgarval", 278, 9, N), ("bsmtval", 287, 9, N),
        ("cnstfact", 296, 7, N), ("cnstval", 303, 9, N),
        ("cndbaseval", 312, 11, N), ("cndadjval", 323, 11, N),
        ("finbsmtval", 334, 9, N), ("grdfact", 343, 5, N),
        ("heatval", 348, 9, N), ("mktadj", 357, 4, N), ("msc1val", 361, 9, N),
        ("msc2val", 370, 9, N), ("plumval", 379, 9, N),
        ("ufeatval", 388, 9, N), ("wbfpval", 397, 9, N),
        ("exmppct", 406, 7, N), ("exmpval", 413, 11, N), ("rcnld", 424, 11, N),
        ("adjrcnld", 435, 11, N), ("adjfact", 446, 8, N),
        ("rcnval", 454, 11, N), ("recval", 465, 9, N), ("sfla", 474, 7, N),
        ("shfact", 481, 7, N), ("subtval", 488, 10, N),
        ("trimval", 498, 9, N), ("unfinval", 507, 9, N),
        ("grmunits", 516, 4, N), ("grmrent", 520, 7, N),
        ("adjgrmfact", 527, 8, N), ("resgrmval", 535, 11, N),
        ("salekey", 546, 9, N), ("note1", 555, 40, A), ("note2", 595, 40, A),
        ("effyr", 635, 5, N), ("pctcomplete", 640, 4, N),
        ("user1", 644, 20, A), ("user2", 664, 20, A), ("user3", 684, 20, A),
        ("user4", 704, 20, A), ("user5", 724, 20, A), ("user6", 744, 20, A),
        ("user7", 764, 20, A), ("user8", 784, 20, A), ("user9", 804, 20, A),
        ("user10", 824, 20, A), ("deactivat", 844, 9, D), ("wen", 853, 9, D),
    ], wrapped=("wen",)),
    "PARDAT": _layout("PARDAT", [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("taxyr", 37, 5, N),
        ("seq", 42, 4, N), ("mappre", 46, 4, A), ("mapsuf", 50, 2, A),
        ("rtepre", 52, 3, A), ("rtesuf", 55, 2, A), ("adrno", 57, 11, N),
        ("adrpre", 68, 2, A), ("adrsuf", 70, 8, A), ("adrsuf2", 78, 8, A),
        ("adrdir", 86, 2, A), ("adrstr", 88, 30, A), ("cityname", 118, 40, A),
        ("unitdesc", 158, 10, A), ("unitno", 168, 10, A), ("loc2", 178, 40, A),
        ("zip1", 218, 5, A), ("zip2", 223, 4, A), ("nbhd", 227, 8, A),
        ("class", 235, 4, A), ("luc", 239, 4, A), ("lucmult", 243, 1, A),
        ("livunit", 244, 4, N), ("tieback", 248, 30, A),
        ("tiebackcd", 278, 2, A), ("tielandpct", 280, 9, N),
        ("tiebldgpct", 289, 9, N), ("landisc", 298, 10, A),
        ("calcacres", 308, 14, N), ("acres", 322, 14, N),
        ("street1", 336, 2, A), ("street2", 338, 2, A), ("traffic", 340, 2, A),
        ("topo1", 342, 1, A), ("topo2", 343, 1, A), ("topo3", 344, 1, A),
        ("location", 345, 2, A), ("fronting", 347, 1, A), ("util1", 348, 2, A),
        ("util2", 350, 2, A), ("util3", 352, 2, A), ("ofcards", 354, 5, N),
        ("partial", 359, 1, A), ("bldgros_d", 360, 21, A),
        ("bldgros_v", 381, 11, N), ("mscbld_n", 392, 3, N),
        ("mscbld_v", 395, 11, N), ("notecd1", 406, 2, A),
        ("notecd2", 408, 2, A), ("note1", 410, 40, A), ("note2", 450, 40, A),
        ("note3", 490, 40, A), ("note4", 530, 40, A), ("rectype", 570, 1, A),
        ("pctown", 571, 9, N), ("chgrsn", 580, 2, A), ("salekey", 582, 9, N),
        ("deactivat", 591, 9, D), ("wen", 600, 9, D),
    ]),
    "LAND": _layout("LAND", [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("lline", 37, 5, N),
        ("taxyr", 42, 5, N), ("seq", 47, 4, N), ("ltype", 51, 1, A),
        ("units", 52, 9, N), ("code", 61, 3, A), ("sf", 64, 11, N),
        ("fronact", 75, 7, N), ("froneff", 82, 5, N), ("depth", 87, 4, N),
        ("class", 91, 4, A), ("agflg", 95, 1, A), ("chgrsn", 96, 2, A),
        ("orate", 98, 11, N), ("brate", 109, 11, N), ("depfact", 120, 5, N),
        ("acres", 125, 15, N), ("exmpval", 140, 11, N), ("infl1", 151, 2, A),
        ("infl2", 153, 2, A), ("influ", 155, 4, N), ("price", 159, 11, N),
        ("exmppct", 170, 7, N), ("salekey", 177, 9, N), ("note1", 186, 40, A),
        ("wen", 226, 9, D),
    ]),
    "OBY": _layout("OBY", [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("seq", 37, 4, N),
        # The PDF swaps these two descriptions; the data has line then card.
        ("lline", 41, 5, N), ("card", 46, 5, N), ("taxyr", 51, 5, N),
        ("code", 56, 3, A), ("yrblt", 59, 5, N), ("effyr", 64, 5, N),
        ("rectype", 69, 1, A), ("yrrem", 70, 5, N), ("area", 75, 9, N),
        ("areasum", 84, 11, N),
        # From grade on, every column sits 8 bytes later than the PDF says.
        ("grade", 95, 3, A), ("class", 98, 4, A), ("chgrsn", 102, 2, A),
        ("obymod1", 104, 4, A), ("obymod2", 108, 4, A),
        ("obymod3", 112, 4, A), ("obymod4", 116, 4, A), ("cond", 120, 1, A),
        ("cndflag", 121, 1, A), ("cndtype", 122, 4, A),
        ("cndcmplx", 126, 30, A), ("funct", 156, 1, A), ("cline", 157, 5, N),
        ("mktadj", 162, 4, N), ("units", 166, 3, N), ("depr", 169, 4, N),
        ("pctcomp", 173, 4, N), ("rate", 177, 14, N), ("rcn", 191, 11, N),
        ("adjfact", 202, 8, N), ("adjrcnld", 210, 11, N),
        ("exmppct", 221, 7, N), ("exmpval", 228, 11, N),
        ("rateovr", 239, 12, N), ("mhmake", 251, 20, A),
        ("mhmodel", 271, 20, A), ("salekey", 291, 9, N), ("meas1", 300, 4, N),
        ("meas2", 304, 5, N), ("vect", 309, 500, A),
        ("deactivat", 809, 9, D), ("wen", 818, 9, D),
    ], wrapped=("wen",)),
    "ADDN": _layout("ADDN", [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("seq", 37, 4, N),
        ("card", 41, 5, N), ("lline", 46, 5, N), ("taxyr", 51, 5, N),
        ("class", 56, 4, A), ("yrblt", 60, 5, N), ("effyr", 65, 5, N),
        ("lower", 70, 3, A), ("first", 73, 3, A), ("second", 76, 3, A),
        ("third", 79, 3, A), ("grade", 82, 3, A), ("grdfact", 85, 5, N),
        ("cdu", 90, 2, A), ("depr", 92, 4, N), ("pctcomp", 96, 4, N),
        ("area", 100, 9, N), ("areasum", 109, 11, N), ("value", 120, 11, N),
        ("mktadj", 131, 4, N), ("rcnld", 135, 11, N), ("exmppct", 146, 7, N),
        ("exmpval", 153, 11, N), ("salekey", 164, 9, N),
        ("chgrsn", 173, 2, A), ("vect", 175, 500, A),
        # The PDF lists wen then deactivat; the data has them the other way round.
        ("deactivat", 675, 9, D), ("wen", 684, 9, D),
    ]),
    "LEGDAT": _layout("LEGDAT", [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("taxyr", 37, 5, N), ("seq", 42, 4, N),
        ("adrpre", 46, 2, A), ("adrno", 48, 11, N), ("adradd", 59, 6, A),
        ("adrsuf", 65, 8, A), ("adrdir", 73, 2, A), ("adrstr", 75, 30, A),
        ("adrsuf2", 105, 8, A), ("cityname", 113, 40, A), ("zip1", 153, 5, A),
        ("zip2", 158, 4, A), ("unitdesc", 162, 10, A), ("unitno", 172, 10, A),
        ("loc2", 182, 40, A), ("taxdist", 222, 5, A), ("acres", 227, 14, N),
        ("compct", 241, 11, N), ("convyn", 252, 10, N), ("xcoord", 262, 11, N),
        ("ycoord", 273, 11, N), ("zcoord", 284, 11, N), ("lotdim", 295, 40, A),
        ("subdiv", 335, 40, A), ("subdnum", 375, 10, A), ("sublot", 385, 8, A),
        ("subblck", 393, 8, A), ("subcode", 401, 1, A), ("condbdg", 402, 8, A),
        ("condunt", 410, 10, A), ("legal1", 420, 60, A), ("legal2", 480, 60, A),
        ("legal3", 540, 60, A), ("note1", 600, 40, A), ("note2", 640, 40, A),
        ("deactivat", 680, 9, D), ("wen", 689, 9, D),
    ]),
    "ASMT": _layout("ASMT", [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("taxyr", 37, 5, N), ("seq", 42, 4, N),
        ("aprland", 46, 11, N), ("aprbldg", 57, 11, N), ("asmtland", 68, 11, N),
        ("asmtbldg", 79, 11, N), ("farmland", 90, 11, N), ("forland", 101, 11, N),
        ("hmsdland", 112, 11, N), ("hmsdbldg", 123, 11, N), ("ppval", 134, 11, N),
        ("abate", 145, 11, N), ("abateland", 156, 11, N), ("noticval", 167, 11, N),
        ("specval", 178, 11, N), ("exmpcode", 189, 6, A), ("noticedate", 195, 9, D),
        ("reascd", 204, 2, A), ("class", 206, 4, A), ("taxclass", 210, 4, A),
        ("luc", 214, 4, A), ("flag2", 218, 6, A), ("note1", 224, 40, A),
        ("note2", 264, 40, A), ("deactivat", 304, 9, D), ("wen", 313, 9, D),
    ]),
    "APRVAL": _layout("APRVAL", [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("taxyr", 37, 5, N), ("seq", 42, 4, N),
        ("reascd", 46, 2, A), ("aprland", 48, 11, N), ("aprbldg", 59, 11, N),
        ("aprtot", 70, 11, N), ("landval", 81, 11, N), ("bldgval", 92, 11, N),
        ("costval", 103, 11, N), ("assmkt", 114, 11, N), ("dwelval", 125, 11, N),
        ("obyval", 136, 11, N), ("revreas", 147, 3, A), ("revland", 150, 11, N),
        ("revbldg", 161, 11, N), ("revtot", 172, 11, N), ("resgrmval", 183, 11, N),
        ("adjbldfact", 194, 8, N), ("adjlandfact", 202, 8, N), ("revwho", 210, 10, A),
        ("revcode", 220, 2, A), ("comval", 222, 11, N), ("comincval", 233, 11, N),
        ("exmpland", 244, 11, N), ("exmpbldg", 255, 11, N), ("exmpval", 266, 11, N),
        ("exmppct", 277, 7, N), ("areasum", 284, 11, N), ("rolltype", 295, 10, A),
        ("note1", 305, 40, A), ("note2", 345, 40, A), ("income", 385, 11, N),
        ("mktval", 396, 11, N), ("mktdt", 407, 9, D), ("lastupd", 416, 9, D),
        ("revdt", 425, 9, D), ("costdt", 434, 9, D), ("deactivat", 443, 9, D),
        ("wen", 452, 9, D),
    ]),
    # NBHD.DAT lines look like 'PARDAT NBHD 98010000 S E WASHINGTON TWP'.
    "NBHD": _layout("NBHD", [
        ("tbl", 1, 7, A), ("label", 8, 5, A), ("nbhd", 13, 9, A), ("describ", 22, 44, A),
    ]),
}

_ENTRY_DATE = re.compile(r"Cama_Files_(\d{8})", re.IGNORECASE)


def _entry(zf: zipfile.ZipFile, table: str) -> str:
    suffix = f"{table.upper()}.DAT"
    for name in zf.namelist():
        # Entry names use backslashes ("Cama_Files_20260831\\DWELL.DAT").
        if re.split(r"[\\/]", name)[-1].upper() == suffix:
            return name
    raise KeyError(f"{table}.DAT not found in CAMA zip")


def snapshot_date(zip_path: Path) -> dt.date:
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            m = _ENTRY_DATE.search(name)
            if m:
                return dt.datetime.strptime(m.group(1), "%Y%m%d").date()
    raise ValueError(f"no snapshot date in {zip_path}")


def table_lines(zip_path: Path, table: str) -> Iterator[str]:
    with zipfile.ZipFile(zip_path) as zf, zf.open(_entry(zf, table)) as fh:
        yield from decode_lines(fh)


def read_table(zip_path: Path, table: str) -> tuple[SpoolReader, Iterator[dict]]:
    """Return the reader (for bad-row stats and ``check()``) and its row iterator.

    Call ``reader.check()`` after consuming the iterator.
    """
    reader = SpoolReader(LAYOUTS[table.upper()])
    return reader, reader.records(table_lines(zip_path, table))


_LOOKUP_LINE = re.compile(r"^DWELDAT (\S+) +(\S.{3})(.*)$")


@dataclass
class Decodes:
    aedit: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)
    grades: dict[str, str] = field(default_factory=dict)
    heats: dict[str, str] = field(default_factory=dict)
    outbuildings: dict[str, str] = field(default_factory=dict)

    def label(self, table: str, field_name: str, code: str | None) -> str | None:
        if code is None:
            return None
        return self.aedit.get((table, field_name), {}).get(code)

    def grade(self, code: str | None) -> str | None:
        return self.grades.get(code) if code else None

    def heat(self, code: str | None) -> str | None:
        # HEAT.DAT has GEOTHERMAL, which the AEDIT list lacks.
        return self.heats.get(code) if code else None

    def outbuilding(self, code: str | None) -> str | None:
        return self.outbuildings.get(code) if code else None


def _read_text(zip_path: Path, table: str) -> list[str]:
    return list(table_lines(zip_path, table))


def _dweldat_lookup(lines: list[str]) -> dict[str, str]:
    out = {}
    for line in lines:
        m = _LOOKUP_LINE.match(line.rstrip())
        if m:
            # Codes carry a leading cost-table digit: "11" is bsmt "1".
            out[m.group(2).strip()[1:]] = m.group(3).strip()
    return out


def load_decodes(zip_path: Path) -> Decodes:
    decodes = Decodes()
    for line in _read_text(zip_path, "AEDIT"):
        if len(line) < 41 or line[0] == " ":
            continue
        key = (line[0:20].strip(), line[20:40].strip())
        decodes.aedit.setdefault(key, {})[line[40:60].strip()] = line[60:100].strip()
    decodes.grades = _dweldat_lookup(_read_text(zip_path, "GRADE"))
    decodes.heats = _dweldat_lookup(_read_text(zip_path, "HEAT"))
    for line in _read_text(zip_path, "RCOBY"):
        if line.strip():
            decodes.outbuildings[line[:3].strip()] = line[3:].strip()
    return decodes


def neighborhood_names(zip_path: Path) -> dict[str, str]:
    """Code to name from NBHD.DAT.

    Codes repeat up to 11 times and 249 carry conflicting names. Prefer a name
    without "NOT USED", then the most frequent, then the longest.
    """
    seen: dict[str, Counter] = defaultdict(Counter)
    reader, rows = read_table(zip_path, "NBHD")
    for row in rows:
        if row["nbhd"] and row["describ"]:
            seen[row["nbhd"]][row["describ"]] += 1
    reader.check()
    out = {}
    for code, counts in seen.items():
        ranked = max(counts.items(), key=lambda kv: ("NOT USED" not in kv[0], kv[1], len(kv[0])))
        out[code] = ranked[0]
    return out
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/county/test_cama.py -v`
Expected: all 12 tests PASS. If `test_neighborhood_names` finds `15007000` missing, the fixture builder's PARDAT `nbhd` slice (bytes 226-234) is wrong; fix the builder, not the test.

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff check src tests scripts
git add src/county/cama.py scripts/build_cama_fixture.py tests/fixtures/county/cama_fixture.zip tests/county/test_cama.py
git commit -m "Add CAMA table layouts, code decodes and a real-data fixture"
```

---

### Task 4: Tax roll reader

**Files:**
- Create: `src/county/taxroll.py`
- Create: `scripts/build_taxroll_fixture.py`
- Create: `tests/fixtures/county/taxroll_fixture.zip` (generated in Step 2)
- Test: `tests/county/test_taxroll.py`

**Interfaces:**
- Consumes: `parse_date` from Task 2.
- Produces:
  - `TaxRollReader` with `rows(zip_path: Path) -> Iterator[dict]`, counters `total`, `bad`, and `check()` (same semantics as `SpoolReader.check`).
  - Each row dict has exactly these keys: `parcel_id: str`, `tax_year: int`, `parcel_class: str`, `land_use_code: str | None`, `tax_district: str | None`, `neighborhood: str | None`, `location: str | None`, `city: str | None`, `zip: str | None`, `census_tract: str | None`, `owner_name: str | None`, `owner_name2: str | None`, `mailing_name: str | None`, `mailing_address1: str | None`, `mailing_address2: str | None`, `mailing_address3: str | None`, `market_value: float | None`, `annual_bill: float`, `gross_rate: float | None`, `effective_rate: float | None`, `owner_occupied: bool`, `homestead: bool`, `rental_registered: bool`, `foreclosure_date: date | None`, `cauv: bool`, `abated: bool`, `net_delinquent: float | None`, `balance_due: float | None`, `living_sqft: int | None`, `year_built: int | None`, `last_sale_date: date | None`, `last_sale_price: float | None`.
  - `annual_bill(raw: dict[str, str]) -> float`.
  - `snapshot_date(zip_path: Path) -> date` from the file name (`TAXROLL_20260923.zip` gives 2026-09-23).

- [ ] **Step 1: Write the fixture builder**

Create `scripts/build_taxroll_fixture.py`:

```python
"""Cut a small tax roll fixture zip out of a full county file.

Usage:
    uv run python scripts/build_taxroll_fixture.py SRC.zip DEST.zip PARID [PARID ...]

Keeps the header line and the raw lines of the listed parcels, byte for byte,
under the original entry name.
"""
import sys
import zipfile


def main(src: str, dest: str, parids: list[str]) -> None:
    wanted = {f'"{p:<14}"'.encode() for p in parids}
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zout:
        (entry,) = [n for n in zin.namelist() if n.lower().endswith(".csv")]
        kept = []
        with zin.open(entry) as fh:
            kept.append(fh.readline())
            for line in fh:
                # Column 2 is the quoted, space-padded parcel id.
                if line.split(b",", 2)[1] in wanted:
                    kept.append(line)
        zout.writestr(entry, b"".join(kept))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
```

- [ ] **Step 2: Download the source file and build the fixture**

```bash
curl -fL -A "Mozilla/5.0" -o /tmp/county/TAXROLL_20260923.zip \
  "https://go.mcohio.org/applications/treasurer/search/data/Taxroll/TAXROLL_20260923.zip"
uv run python scripts/build_taxroll_fixture.py /tmp/county/TAXROLL_20260923.zip \
  tests/fixtures/county/taxroll_fixture.zip \
  "A01 00101 0001" "A01 00102 0069" "N64 00101 0003" "R72 00304 0025"
unzip -p tests/fixtures/county/taxroll_fixture.zip | wc -l
```
Expected: `5` (header plus four parcels).

- [ ] **Step 3: Write the failing tests**

Create `tests/county/test_taxroll.py`:

```python
import datetime as dt
import io
import zipfile
from pathlib import Path

import pytest

from county.taxroll import TaxRollReader, annual_bill, snapshot_date

FIXTURE = Path(__file__).parent.parent / "fixtures" / "county" / "taxroll_fixture.zip"


def read_all():
    reader = TaxRollReader()
    rows = {r["parcel_id"]: r for r in reader.rows(FIXTURE)}
    reader.check()
    return reader, rows


def test_reads_every_fixture_parcel():
    reader, rows = read_all()
    assert set(rows) == {"A01 00101 0001", "A01 00102 0069", "N64 00101 0003", "R72 00304 0025"}
    assert reader.bad == 0


def test_residential_owner_occupied_row():
    _, rows = read_all()
    r = rows["A01 00101 0001"]
    assert r["tax_year"] == 2025
    assert r["parcel_class"] == "R"
    assert r["land_use_code"] == "511"
    assert r["tax_district"] == "A01"
    assert r["neighborhood"] == "48150000"
    assert r["census_tract"] == "39113-110100-1"
    assert r["zip"] == "45377"
    assert r["owner_occupied"] is True
    assert r["homestead"] is False
    assert r["rental_registered"] is False
    assert r["foreclosure_date"] is None
    assert r["year_built"] == 1919
    assert r["living_sqft"] == 2464
    assert r["last_sale_date"] == dt.date(2023, 3, 20)
    assert r["last_sale_price"] == 320000
    assert r["market_value"] == 274320
    assert r["gross_rate"] == pytest.approx(110.55)
    assert r["annual_bill"] == pytest.approx(6066.22)
    assert r["mailing_address3"] == "VANDALIA OH 45377"


def test_annual_bill_sums_both_halves_of_every_component():
    components = ("ADJ", "RLBK", "HMSD", "HMRB", "SPASMTS", "DAYCRDT")
    raw = {f"HLF{h}{c}": "0" for h in (1, 2) for c in components}
    raw.update(HLF1ADJ="000000001000.00", HLF2ADJ="000000001000.00",
               HLF1RLBK="-000000000100.00", HLF2HMSD="-000000000050.50",
               HLF1SPASMTS="000000000012.25", HLF2DAYCRDT="")
    assert annual_bill(raw) == pytest.approx(1861.75)


def test_snapshot_date_from_file_name():
    assert snapshot_date(Path("x/TAXROLL_20260923.zip")) == dt.date(2026, 9, 23)


def test_rows_with_wrong_column_count_are_bad(tmp_path):
    with zipfile.ZipFile(FIXTURE) as zf:
        (entry,) = zf.namelist()
        data = zf.read(entry)
    broken = data + b'"Z99 00000 0001","only two columns"\r\n'
    path = tmp_path / "TAXROLL_20260923.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(entry, broken)
    reader = TaxRollReader()
    ids = [r["parcel_id"] for r in reader.rows(path)]
    assert "Z99 00000 0001" not in ids
    assert (reader.total, reader.bad) == (5, 1)
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run pytest tests/county/test_taxroll.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'county.taxroll'`

- [ ] **Step 5: Implement `src/county/taxroll.py`**

```python
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
            "owner_occupied": _flag(raw.get("OWNOCC")),
            "homestead": _flag(raw.get("HMSDFLAG")),
            "rental_registered": _flag(raw.get("RENTALREG")),
            "foreclosure_date": parse_date(raw["FRCLSR"]),
            "cauv": (_number(raw["AGLAND"]) or 0) > 0,
            "abated": (_number(raw.get("AETASMTTOTAL")) or 0) > 0,
            "net_delinquent": _number(raw["NETDELQ"]),
            "balance_due": _number(raw["FULLYRAMTDUE"]),
            "living_sqft": _int(raw.get("SQ. FT.")),
            "year_built": _int(raw["YRBL"]),
            "last_sale_date": parse_date(raw["SALESDTE"]),
            "last_sale_price": _number(raw["PRICE"]),
        }
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/county/test_taxroll.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff check src tests scripts
git add src/county/taxroll.py scripts/build_taxroll_fixture.py tests/fixtures/county/taxroll_fixture.zip tests/county/test_taxroll.py
git commit -m "Add a tax roll reader with the annual bill calculation"
```

---

### Task 5: County helpers: neighborhood names, coordinates, tax districts, owner names, search text

**Files:**
- Create: `src/county/neighborhood_codes.py`, `src/county/coords.py`, `src/county/tax_districts.py`, `src/county/data/tax_districts.json`, `src/county/owners.py`, `src/county/text.py`
- Test: `tests/county/test_helpers.py`

**Interfaces:**
- Produces:
  - `parse_neighborhood_codes(html: bytes) -> dict[str, str]` (code to name).
  - `neighborhood_display_name(name: str) -> str` strips Dayton priority-board prefixes (`"SE PRIORITY BOARD-LINDEN HEIGHTS"` gives `"LINDEN HEIGHTS"`); casing is left to the frontend.
  - `state_plane_to_wgs84(x_feet: float | None, y_feet: float | None) -> tuple[float, float] | None` returning `(latitude, longitude)`, or `None` for missing or zero input.
  - `district_info(code: str) -> tuple[str, str | None]` returning `(name, school_district)`; `jurisdiction_name(code: str) -> str`.
  - `classify_owner_name(name: str | None) -> str | None` returning `"government"`, `"company"`, `"trust"` or `None`.
  - `mailing_state(line: str | None) -> str | None` (two-letter state from a `CITY ST 12345` line).
  - `normalize_search(text: str | None) -> str`, `parcel_id_key(text: str) -> str`, `prefix_upper_bound(prefix: str) -> str`, `street_key(address: str) -> str` (drops the house number and a leading direction, so "aragon" finds "2301 S ARAGON AVE").

- [ ] **Step 1: Write the failing tests**

Create `tests/county/test_helpers.py`:

```python
import pytest

from county.coords import state_plane_to_wgs84
from county.neighborhood_codes import neighborhood_display_name, parse_neighborhood_codes
from county.owners import classify_owner_name, mailing_state
from county.tax_districts import district_info, jurisdiction_name
from county.text import normalize_search, parcel_id_key, prefix_upper_bound, street_key

HTML = (
    b"<table>\r\n<tr>\r\n<td>\r\n48150000\r\n</td>\r\n<td>\r\nN BUTLER TWP\r\n</td>\r\n</tr>\r\n"
    b"<tr>\r\n<td>\r\n82000ARL\r\n</td>\r\n<td>\r\nSW PRIORITY BOARD-ARLINGTON HEIGHTS\r\n"
    b"</td>\r\n</tr>\r\n<tr>\r\n<td>\r\n66050000\r\n</td>\r\n<td>\r\nBELL &amp; SONS\r\n</td>\r\n"
    b"</tr>\r\n<tr>\r\n<td>\r\n46024000\r\n</td>\r\n<td>\r\n\xa0\r\n</td>\r\n</tr>\r\n</table>"
)


def test_parse_neighborhood_codes():
    assert parse_neighborhood_codes(HTML) == {
        "48150000": "N BUTLER TWP",
        "82000ARL": "SW PRIORITY BOARD-ARLINGTON HEIGHTS",
        "66050000": "BELL & SONS",
    }


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("SE PRIORITY BOARD-LINDEN HEIGHTS", "LINDEN HEIGHTS"),
        ("F.R.O.C. PRIORITY BOARD-NORTH RIVERDALE", "NORTH RIVERDALE"),
        ("DOWNTOWN PRIORITY BOARD-DOWNTOWN", "DOWNTOWN"),
        ("N BUTLER TWP", "N BUTLER TWP"),
    ],
)
def test_neighborhood_display_name(name, expected):
    assert neighborhood_display_name(name) == expected


def test_state_plane_to_wgs84():
    lat, lon = state_plane_to_wgs84(1470869, 704667)
    assert lat == pytest.approx(39.92128, abs=1e-4)
    assert lon == pytest.approx(-84.27433, abs=1e-4)
    assert state_plane_to_wgs84(None, 704667) is None
    assert state_plane_to_wgs84(0, 0) is None


def test_district_info():
    name, school = district_info("C09")
    assert name == "CLAY-TRI COUNTY NORTH LSD"
    assert school == "TRI COUNTY NORTH LSD"
    # Blank names in the lookup fall back to the jurisdiction letter.
    assert district_info("R72") == ("DAYTON", None)
    assert jurisdiction_name("N64") == "KETTERING"
    assert district_info("Z99") == ("Z99", None)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("CITY OF DAYTON", "government"),
        ("MONTGOMERY COUNTY LAND REUTILIZATION CORP", "government"),
        ("SECRETARY OF HOUSING AND URBAN DEVELOPMENT", "government"),
        ("STATE OF OHIO", "government"),
        ("VB ELEVEN LLC", "company"),
        ("NVR INC", "company"),
        ("FEDERAL NATIONAL MORTGAGE ASSOC", "company"),
        ("SMITH FAMILY TRUST", "trust"),
        ("JONES MARY TR", "trust"),
        ("MULLENAX SAMANTHA MARIE", None),
        (None, None),
    ],
)
def test_classify_owner_name(name, expected):
    assert classify_owner_name(name) == expected


def test_mailing_state():
    assert mailing_state("VANDALIA OH 45377") == "OH"
    assert mailing_state("CHARLOTTE NC 28237-0001") == "NC"
    assert mailing_state("P.O. BOX 37996") is None
    assert mailing_state(None) is None


def test_search_text_helpers():
    assert normalize_search("  6617  pheasant-ridge rd. ") == "6617 PHEASANT RIDGE RD"
    assert normalize_search("o'neil") == "ONEIL"
    assert normalize_search(None) == ""
    assert parcel_id_key("r72 00304 0025") == "R72003040025"
    assert prefix_upper_bound("PHEAS") == "PHEAT"
    assert street_key("6617 PHEASANT RIDGE RD") == "PHEASANT RIDGE RD"
    assert street_key("2301 S ARAGON AVE") == "ARAGON AVE"
    assert street_key("S ARAGON") == "ARAGON"
    assert street_key("PHEASANT RIDGE RD") == "PHEASANT RIDGE RD"
    # A street literally named with a direction letter keeps it.
    assert street_key("120 E ST") == "E ST"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/county/test_helpers.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the helpers**

Create `src/county/neighborhood_codes.py`:

```python
"""The county's monthly neighborhood codes page (neighborhood_codes_YYYYMMDD.htm)."""
import html
import re

_ROW = re.compile(r"<tr>\s*<td>\s*(.*?)\s*</td>\s*<td>\s*(.*?)\s*</td>\s*</tr>", re.S | re.I)
_PRIORITY_BOARD = re.compile(r"^.*?PRIORITY BOARD-\s*")


def parse_neighborhood_codes(page: bytes) -> dict[str, str]:
    text = page.decode("cp1252", errors="replace")
    out = {}
    for code, name in _ROW.findall(text):
        code = html.unescape(code).replace("\xa0", " ").strip()
        name = html.unescape(name).replace("\xa0", " ").strip()
        if code and name:
            out[code] = name
    return out


def neighborhood_display_name(name: str) -> str:
    """Drop Dayton's priority-board prefix; the rest names the neighborhood."""
    return _PRIORITY_BOARD.sub("", name).strip() or name
```

Create `src/county/coords.py`:

```python
"""CAMA LEGDAT coordinates are Ohio State Plane South (EPSG:3735), US survey feet."""
from functools import lru_cache

from pyproj import Transformer


@lru_cache(maxsize=1)
def _transformer() -> Transformer:
    return Transformer.from_crs("EPSG:3735", "EPSG:4326", always_xy=True)


def state_plane_to_wgs84(x_feet: float | None, y_feet: float | None) -> tuple[float, float] | None:
    if not x_feet or not y_feet:
        return None
    lon, lat = _transformer().transform(x_feet, y_feet)
    return round(lat, 7), round(lon, 7)
```

Create `src/county/data/tax_districts.json` by copying the scraped lookup:

```bash
mkdir -p src/county/data
cp docs/data-sources/lookups/tax_district_names.json src/county/data/tax_districts.json
```

Create `src/county/tax_districts.py`:

```python
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
```

Create `src/county/owners.py`:

```python
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
```

Create `src/county/text.py`:

```python
"""Search normalization shared by ingest (stored keys) and the API (queries).

Stored keys and queries must normalize identically, and prefix search uses a
[prefix, upper bound) range so a plain btree index serves it on both SQLite
and Postgres (LIKE 'x%' cannot use an index on either without extra setup).
"""
import re

_DROP = re.compile(r"['’.]")
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/county/test_helpers.py -v`
Expected: all tests PASS. If `test_district_info` fails for `C09` because the scraped lookup changed, update the expectation to the value now in `src/county/data/tax_districts.json`, keeping the school-district split behavior.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/county tests/county/test_helpers.py
git commit -m "Add neighborhood, coordinate, tax district, owner-name and search helpers"
```

---

### Task 6: County file listing and download

**Files:**
- Create: `src/county/sources.py`
- Test: `tests/county/test_sources.py`

**Interfaces:**
- Produces:
  - `DATASETS: dict[str, Dataset]` with keys `"cama"`, `"taxroll"`, `"neighborhoods"`; `Dataset(code: str, folder: str, pattern: re.Pattern)`.
  - `async list_files(dataset: str, client: httpx.AsyncClient) -> list[str]` (file names, oldest first by the date in the name).
  - `async latest_file(dataset: str, client: httpx.AsyncClient) -> str | None`.
  - `async download(dataset: str, filename: str, dest_dir: Path, client: httpx.AsyncClient) -> Path` (streams to `dest_dir/<folder>/<filename>`; returns the existing file without downloading when it is already there).
  - `county_client() -> httpx.AsyncClient` (timeouts and User-Agent set).

- [ ] **Step 1: Write the failing tests**

Create `tests/county/test_sources.py`:

```python
import httpx

from county import sources

INDEX = (
    '<a href=data\\Cama\\Cama_Files_20260630.zip>Cama_Files_20260630.zip</a>'
    '<a href=data\\Cama\\Cama_Files_20260831.zip>Cama_Files_20260831.zip</a>'
    '<a href=data\\Cama\\Cama_Files_20260731.zip>Cama_Files_20260731.zip</a>'
)


def client_for(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_list_files_sorted_and_deduplicated():
    def handler(request):
        assert request.url.params["dtype"] == "CC"
        return httpx.Response(200, text=INDEX + INDEX)

    async with client_for(handler) as client:
        files = await sources.list_files("cama", client)
    assert files == [
        "Cama_Files_20260630.zip", "Cama_Files_20260731.zip", "Cama_Files_20260831.zip"
    ]


async def test_latest_file():
    async with client_for(lambda r: httpx.Response(200, text=INDEX)) as client:
        assert await sources.latest_file("cama", client) == "Cama_Files_20260831.zip"


async def test_latest_file_when_index_is_empty():
    async with client_for(lambda r: httpx.Response(200, text="<html></html>")) as client:
        assert await sources.latest_file("taxroll", client) is None


async def test_download_streams_to_dataset_folder(tmp_path):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, content=b"zipbytes")

    async with client_for(handler) as client:
        path = await sources.download("taxroll", "TAXROLL_20260923.zip", tmp_path, client)
        again = await sources.download("taxroll", "TAXROLL_20260923.zip", tmp_path, client)
    assert path == tmp_path / "Taxroll" / "TAXROLL_20260923.zip"
    assert path.read_bytes() == b"zipbytes"
    assert again == path
    assert seen == [
        "https://go.mcohio.org/applications/treasurer/search/data/Taxroll/TAXROLL_20260923.zip"
    ]


async def test_failed_download_leaves_no_partial_file(tmp_path):
    async with client_for(lambda r: httpx.Response(500)) as client:
        try:
            await sources.download("cama", "Cama_Files_20260831.zip", tmp_path, client)
        except httpx.HTTPStatusError:
            pass
    assert not (tmp_path / "Cama" / "Cama_Files_20260831.zip").exists()
    assert list((tmp_path / "Cama").glob("*")) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/county/test_sources.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement `src/county/sources.py`**

```python
"""Listing and downloading files from the county treasurer's download site."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import httpx

INDEX_URL = "https://go.mcohio.org/applications/treasurer/search/fdpopup.cfm"
FILE_URL = "https://go.mcohio.org/applications/treasurer/search/data/{folder}/{filename}"


@dataclass(frozen=True)
class Dataset:
    code: str  # fdpopup.cfm?dtype=
    folder: str  # data/<folder>/
    pattern: re.Pattern  # group(1) is the YYYYMMDD date


DATASETS = {
    "cama": Dataset("CC", "Cama", re.compile(r"Cama_Files_(\d{8})\.zip", re.I)),
    "taxroll": Dataset("TR", "Taxroll", re.compile(r"TAXROLL_(\d{8})\.zip", re.I)),
    "neighborhoods": Dataset(
        "NC", "nbhd_code_monthly", re.compile(r"neighborhood_codes_(\d{8})\.htm", re.I)
    ),
}


def county_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(60.0, read=300.0),
        headers={"User-Agent": "Mozilla/5.0 (real-estate-viewer)"},
        follow_redirects=True,
    )


async def list_files(dataset: str, client: httpx.AsyncClient) -> list[str]:
    spec = DATASETS[dataset]
    response = await client.get(INDEX_URL, params={"dtype": spec.code})
    response.raise_for_status()
    by_name = {m.group(0): m.group(1) for m in spec.pattern.finditer(response.text)}
    return sorted(by_name, key=lambda name: by_name[name])


async def latest_file(dataset: str, client: httpx.AsyncClient) -> str | None:
    files = await list_files(dataset, client)
    return files[-1] if files else None


async def download(
    dataset: str, filename: str, dest_dir: Path, client: httpx.AsyncClient
) -> Path:
    spec = DATASETS[dataset]
    folder = Path(dest_dir) / spec.folder
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / filename
    if target.exists():
        return target
    partial = folder / f".{filename}.part"
    url = FILE_URL.format(folder=spec.folder, filename=filename)
    try:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with partial.open("wb") as out:
                async for chunk in response.aiter_bytes(1 << 20):
                    out.write(chunk)
        partial.rename(target)
    finally:
        partial.unlink(missing_ok=True)
    return target
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/county/test_sources.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/county/sources.py tests/county/test_sources.py
git commit -m "Add county file listing and streaming download"
```

---

### Task 7: Schema for the new county tables

**Files:**
- Modify: `src/db/county_models.py` (replace the Task 1 placeholder)
- Modify: `src/db/models.py` (`ParcelBase`)
- Modify: `src/db/engine.py` (`init_db`)
- Modify: `src/db/maintenance.py`
- Test: `tests/test_county_schema.py`

**Interfaces:**
- Produces (all in `db.county_models` unless noted):
  - `Parcel` (in `db.models`) gains: `neighborhood: str | None` (indexed), `tax_district: str | None`, `land_use_code: str | None`, `zip: str | None`, `census_tract: str | None`, `is_active: bool = True`, `coord_source: str | None` (`"county"` or `"census"`).
  - `ParcelDetail`, `Dwelling`, `ParcelFeature`, `ParcelValue`, `Neighborhood`, `TaxDistrict`, `ParcelTax`, `ParcelSummary`, `NeighborhoodSummary`, `DataVersion` with the columns shown in Step 3. Table names are the snake_case class names (`parcel_detail`, `dwelling`, ...).
  - `OCCUPANCY_CATEGORIES = ("owner_occupied", "company", "trust", "government", "absentee_individual", "unknown")`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_county_schema.py`:

```python
import datetime as dt

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from db.county_models import Dwelling, ParcelSummary
from db.maintenance import repair_schema
from db.models import Parcel, ParcelClass


async def test_new_tables_exist(db_engine):
    async with db_engine.connect() as conn:
        tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
    assert {
        "parcel_detail", "dwelling", "parcel_feature", "parcel_value", "neighborhood",
        "tax_district", "parcel_tax", "parcel_summary", "neighborhood_summary", "data_version",
    } <= tables


async def test_parcel_defaults(session):
    session.add(Parcel(parcel_id="P1", parcel_location="1 MAIN ST",
                       parcel_class=ParcelClass.R, acres=0.1))
    await session.commit()
    parcel = await session.get(Parcel, "P1")
    assert parcel.is_active is True
    assert parcel.neighborhood is None


async def test_dwelling_primary_key_is_parcel_and_card(session):
    for card in (1, 2):
        session.add(Dwelling(parcel_id="P1", card=card, living_sqft=1000,
                             snapshot_date=dt.date(2026, 8, 31)))
    await session.commit()
    assert await session.get(Dwelling, ("P1", 2)) is not None


async def test_summary_defaults(session):
    session.add(ParcelSummary(parcel_id="P1", parcel_class="R", is_active=True,
                              occupancy="unknown"))
    await session.commit()
    row = await session.get(ParcelSummary, "P1")
    assert (row.distress_score, row.distress_flags, row.permit_count_5y) == (0, 0, 0)


async def test_repair_adds_new_parcel_columns_to_an_old_database(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/old.db")
    async with engine.begin() as conn:
        await conn.execute(text(
            "CREATE TABLE parcel (parcel_id VARCHAR PRIMARY KEY, parcel_location VARCHAR NOT NULL,"
            " parcel_class VARCHAR(1) NOT NULL, acres FLOAT NOT NULL, latitude FLOAT,"
            " longitude FLOAT)"
        ))
        await conn.execute(text(
            "INSERT INTO parcel VALUES ('P1', '1 MAIN ST', 'R', 0.1, NULL, NULL)"
        ))
        await conn.run_sync(repair_schema)
        await conn.run_sync(repair_schema)  # idempotent
        columns = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("parcel")}
        )
        active = (await conn.execute(text("SELECT is_active FROM parcel"))).scalar_one()
    await engine.dispose()
    assert {"neighborhood", "tax_district", "land_use_code", "zip", "census_tract",
            "is_active", "coord_source"} <= columns
    assert bool(active) is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_county_schema.py -v`
Expected: FAIL with `ImportError: cannot import name 'Dwelling'`

- [ ] **Step 3: Add the models**

In `src/db/models.py`, add to `ParcelBase` after `longitude` (and add `import sqlalchemy as sa` at the top):

```python
    neighborhood: str | None = Field(default=None, index=True, description="CAMA neighborhood code")
    tax_district: str | None = Field(default=None, description="Tax district code")
    land_use_code: str | None = Field(default=None, description="Ohio DTE land use code")
    zip: str | None = Field(default=None, description="Situs ZIP code")
    census_tract: str | None = Field(default=None, description="Census block group")
    is_active: bool = Field(
        default=True,
        sa_column_kwargs={"server_default": sa.true()},
        description="False once the parcel disappears from CAMA (retired or combined)",
    )
    coord_source: str | None = Field(default=None, description="county or census")
```

Replace `src/db/county_models.py`:

```python
"""Tables loaded from the county's CAMA and tax roll files, plus derived tables.

Snapshot tables are fully replaced on each ingest (see ingest/bulk.py).
"""
from datetime import date, datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

OCCUPANCY_CATEGORIES = (
    "owner_occupied", "company", "trust", "government", "absentee_individual", "unknown",
)


class ParcelDetail(SQLModel, table=True):
    __tablename__ = "parcel_detail"
    parcel_id: str = Field(primary_key=True)
    land_use_code: str | None = None
    land_use: str | None = None
    living_units: int | None = None
    house_number: int | None = None
    street_direction: str | None = None
    street_name: str | None = None
    street_suffix: str | None = None
    unit: str | None = None
    city: str | None = None
    zip: str | None = None
    lot_sqft: int | None = None
    lot_acres: float | None = None
    frontage_ft: float | None = None
    depth_ft: float | None = None
    snapshot_date: date


class Dwelling(SQLModel, table=True):
    __tablename__ = "dwelling"
    parcel_id: str = Field(primary_key=True)
    card: int = Field(primary_key=True)
    living_sqft: int | None = None
    first_floor_sqft: int | None = None
    finished_basement_sqft: int | None = None
    beds: int | None = None
    full_baths: int | None = None
    half_baths: int | None = None
    stories: float | None = None
    style_code: str | None = None
    style: str | None = None
    year_built: int | None = None
    year_built_is_placeholder: bool = False
    grade: str | None = None
    grade_label: str | None = None
    condition: str | None = None
    exterior: str | None = None
    basement: str | None = None
    heating: str | None = None
    fuel: str | None = None
    has_central_air: bool = False
    fireplaces: int = 0
    attached_garage_sqft: int = 0
    basement_garage_cars: int = 0
    sketch: str | None = Field(default=None, sa_column=sa.Column(sa.Text))
    snapshot_date: date


class ParcelFeature(SQLModel, table=True):
    __tablename__ = "parcel_feature"
    id: int | None = Field(default=None, primary_key=True)
    parcel_id: str = Field(index=True)
    card: int | None = None
    line: int | None = None
    code: str
    description: str | None = None
    year_built: int | None = None
    area_sqft: int | None = None
    width_ft: int | None = None
    length_ft: int | None = None
    condition: str | None = None
    snapshot_date: date


class ParcelValue(SQLModel, table=True):
    __tablename__ = "parcel_value"
    parcel_id: str = Field(primary_key=True)
    land_2025: int | None = None
    building_2025: int | None = None
    total_2025: int | None = None
    land_2026: int | None = None
    building_2026: int | None = None
    total_2026: int | None = None
    change_pct: float | None = None
    value_method: str | None = None
    appeal_year: int | None = None
    tif: bool = False
    abated: bool = False
    reappraisal_reason: str | None = None
    snapshot_date: date


class Neighborhood(SQLModel, table=True):
    __tablename__ = "neighborhood"
    code: str = Field(primary_key=True)
    name: str
    display_name: str
    tax_district: str | None = None


class TaxDistrict(SQLModel, table=True):
    __tablename__ = "tax_district"
    code: str = Field(primary_key=True)
    name: str
    jurisdiction: str
    school_district: str | None = None


class ParcelTax(SQLModel, table=True):
    __tablename__ = "parcel_tax"
    parcel_id: str = Field(primary_key=True)
    tax_year: int
    snapshot_date: date
    annual_bill: float
    gross_rate: float | None = None
    effective_rate: float | None = None
    market_value: float | None = None
    owner_occupied: bool = False
    homestead: bool = False
    rental_registered: bool = False
    foreclosure_date: date | None = None
    cauv: bool = False
    abated: bool = False
    net_delinquent: float | None = None
    balance_due: float | None = None
    census_tract: str | None = None
    zip: str | None = None
    city: str | None = None
    owner_name: str | None = None
    owner_name2: str | None = None
    mailing_name: str | None = None
    mailing_address: str | None = None
    mailing_state: str | None = None
    out_of_state: bool = False
    occupancy: str = "unknown"
    occupancy_reason: str | None = None


class ParcelSummary(SQLModel, table=True):
    """One denormalized row per parcel for the map, search and filters."""

    __tablename__ = "parcel_summary"
    parcel_id: str = Field(primary_key=True)
    parcel_id_search: str | None = Field(default=None, index=True)
    latitude: float | None = None
    longitude: float | None = None
    parcel_class: str
    land_use_code: str | None = None
    neighborhood: str | None = Field(default=None, index=True)
    tax_district: str | None = None
    is_active: bool = True
    address: str | None = None
    address_search: str | None = Field(default=None, index=True)
    street_search: str | None = Field(default=None, index=True)
    owner_name: str | None = None
    owner_search: str | None = Field(default=None, index=True)
    last_sale_date: date | None = Field(default=None, index=True)
    last_sale_price: float | None = None
    price_per_sqft: float | None = None
    living_sqft: int | None = None
    beds: int | None = None
    baths: float | None = None
    year_built: int | None = None
    year_built_is_placeholder: bool = False
    market_value: float | None = None
    value_change_pct: float | None = None
    occupancy: str = "unknown"
    out_of_state_owner: bool = False
    distress_score: int = 0
    distress_flags: int = 0
    permit_count_5y: int = 0
    last_permit_date: date | None = None
    annual_tax: float | None = None


class NeighborhoodSummary(SQLModel, table=True):
    __tablename__ = "neighborhood_summary"
    code: str = Field(primary_key=True)
    parcel_count: int = 0
    residential_count: int = 0
    sales_24m: int = 0
    median_sale_price_24m: float | None = None
    median_price_per_sqft_24m: float | None = None
    owner_occupied_share: float | None = None
    median_year_built: int | None = None
    median_value_change_pct: float | None = None


class DataVersion(SQLModel, table=True):
    """Single row (id=1). Bumped by the derived step; keys every cache."""

    __tablename__ = "data_version"
    id: int = Field(default=1, primary_key=True)
    version: int = 0
    updated_at: datetime
```

In `src/db/engine.py`, make `init_db` register the new tables before `create_all`:

```python
async def init_db():
    """create our database models in the database"""
    import db.county_models  # noqa: F401  (registers the county tables)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
```

- [ ] **Step 4: Add the idempotent repair for existing databases**

In `src/db/maintenance.py`:

1. Add module constant after `RETIRED_INDEXES`:

```python
# Columns added to parcel for the county data platform. DDL is portable:
# SQLite and Postgres both accept BOOLEAN ... DEFAULT TRUE.
PARCEL_COLUMNS = {
    "neighborhood": "neighborhood VARCHAR",
    "tax_district": "tax_district VARCHAR",
    "land_use_code": "land_use_code VARCHAR",
    "zip": "zip VARCHAR",
    "census_tract": "census_tract VARCHAR",
    "is_active": "is_active BOOLEAN NOT NULL DEFAULT TRUE",
    "coord_source": "coord_source VARCHAR",
}
```

2. Add this function after `_add_missing_columns`:

```python
def _add_parcel_columns(sync_conn) -> None:
    existing = {c["name"] for c in inspect(sync_conn).get_columns("parcel")}
    for name, ddl in PARCEL_COLUMNS.items():
        if name not in existing:
            logger.info("Adding parcel.%s.", name)
            sync_conn.execute(text(f"ALTER TABLE parcel ADD COLUMN {ddl}"))
    if not _has_index(sync_conn, "ix_parcel_neighborhood"):
        sync_conn.execute(text("CREATE INDEX ix_parcel_neighborhood ON parcel (neighborhood)"))


def repair_schema(sync_conn) -> None:
    """Every idempotent repair, in order. Safe to run on any database."""
    _add_parcel_columns(sync_conn)
    if inspect(sync_conn).has_table("transaction"):
        _repair(sync_conn)
```

3. Make `ensure_schema` call `repair_schema` instead of `_repair`:

```python
async def ensure_schema() -> None:
    """Bring a database created by older code up to the current schema."""
    async with engine.begin() as conn:
        await conn.run_sync(repair_schema)
```

- [ ] **Step 5: Run the new tests and the whole suite**

Run: `uv run pytest -q`
Expected: all tests PASS (the new schema tests plus every existing test).

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check src tests
git add src/db tests/test_county_schema.py
git commit -m "Add tables for CAMA, tax roll and derived data, with a parcel column repair"
```

---

### Task 8: Bulk load helpers and CAMA parcel ingest

**Files:**
- Create: `src/ingest/__init__.py`, `src/ingest/bulk.py`, `src/ingest/cama_ingest.py`
- Test: `tests/ingest/__init__.py`, `tests/ingest/test_bulk.py`, `tests/ingest/test_cama_parcels.py`

**Interfaces:**
- Consumes: `read_table`, `load_decodes`, `snapshot_date`, `Decodes` (Task 3); `state_plane_to_wgs84` (Task 5); `TooManyBadRows` (Task 2); models from Task 7.
- Produces:
  - `bulk.insert_rows(conn: AsyncConnection, table: sa.Table, rows: Iterable[dict]) -> int` (chunked by bind-parameter budget).
  - `bulk.replace_rows(conn: AsyncConnection, table: sa.Table, rows: Iterable[dict]) -> int` (delete all, then insert; caller owns the transaction).
  - `bulk.in_thread_chunks(rows: Iterator[dict], size: int = 5000) -> AsyncIterator[list[dict]]` (parses in a worker thread so the API stays responsive during ingest).
  - `bulk.upsert()`: dialect-specific `insert` for `ON CONFLICT`.
  - `cama_ingest.CamaContext` holding `zip_path`, `snapshot: date`, `decodes: Decodes`, `land: dict[str, LandTotals]`, `legdat: dict[str, LegalInfo]`.
  - `cama_ingest.load_context(zip_path: Path) -> CamaContext` (sync; run it in a thread).
  - `cama_ingest.compose_address(house_number, direction, street, suffix, unit) -> str`.
  - `async cama_ingest.load_parcels(conn, ctx) -> int` and `async cama_ingest.load_parcel_details(conn, ctx) -> int`.
  - `async cama_ingest.ingest_cama(zip_path: Path, engine: AsyncEngine | None = None) -> dict[str, int]` (row counts per table). This task wires only parcels and details; Tasks 9 and 10 add their loaders to the same transaction.

- [ ] **Step 1: Write the failing bulk tests**

Create `tests/ingest/__init__.py` (empty) and `tests/ingest/test_bulk.py`:

```python
import pytest
from sqlalchemy import func, select

from db.county_models import Neighborhood
from ingest.bulk import in_thread_chunks, replace_rows

TABLE = Neighborhood.__table__


def rows(n, prefix="N"):
    return ({"code": f"{prefix}{i:05d}", "name": "X", "display_name": "X"} for i in range(n))


async def count(conn):
    return (await conn.execute(select(func.count()).select_from(TABLE))).scalar_one()


async def test_replace_rows_replaces_everything(db_engine):
    async with db_engine.begin() as conn:
        await replace_rows(conn, TABLE, rows(10, "A"))
    async with db_engine.begin() as conn:
        written = await replace_rows(conn, TABLE, rows(2500, "B"))
    async with db_engine.connect() as conn:
        assert written == 2500
        assert await count(conn) == 2500


async def test_failed_ingest_leaves_previous_rows(db_engine):
    async with db_engine.begin() as conn:
        await replace_rows(conn, TABLE, rows(10, "A"))

    def exploding():
        yield from rows(3000, "B")
        raise RuntimeError("layout changed")

    with pytest.raises(RuntimeError):
        async with db_engine.begin() as conn:
            await replace_rows(conn, TABLE, exploding())

    async with db_engine.connect() as conn:
        assert await count(conn) == 10


async def test_in_thread_chunks():
    chunks = [c async for c in in_thread_chunks(iter(range(12)), size=5)]
    assert chunks == [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9], [10, 11]]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/ingest/test_bulk.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ingest'`

- [ ] **Step 3: Implement `src/ingest/bulk.py`**

Create `src/ingest/__init__.py` with `"""Loaders that turn county files into database rows."""` and `src/ingest/bulk.py`:

```python
"""Bulk write helpers for snapshot tables.

Snapshot tables are replaced wholesale inside the caller's transaction, so a
failure anywhere (a parse error, a bad-row rejection, a lost connection)
rolls back to the previous snapshot.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable, Iterator
from itertools import islice

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncConnection

# Both SQLite (>= 3.32) and asyncpg allow 32,766 bind parameters per statement.
_PARAM_BUDGET = 30_000


def upsert(conn: AsyncConnection):
    """The dialect's INSERT construct that supports ON CONFLICT."""
    return pg_insert if conn.dialect.name == "postgresql" else sqlite_insert


def _chunk_size(table: sa.Table) -> int:
    return max(1, _PARAM_BUDGET // len(table.columns))


async def insert_rows(conn: AsyncConnection, table: sa.Table, rows: Iterable[dict]) -> int:
    size = _chunk_size(table)
    iterator = iter(rows)
    written = 0
    while chunk := list(islice(iterator, size)):
        await conn.execute(sa.insert(table), chunk)
        written += len(chunk)
    return written


async def replace_rows(conn: AsyncConnection, table: sa.Table, rows: Iterable[dict]) -> int:
    await conn.execute(sa.delete(table))
    return await insert_rows(conn, table, rows)


async def in_thread_chunks(rows: Iterator, size: int = 5000) -> AsyncIterator[list]:
    """Pull rows from a CPU-bound generator in a worker thread, a chunk at a time.

    The generator is only ever advanced by one thread at a time, so ordinary
    (non-thread-safe) generators are fine.
    """
    while True:
        chunk = await asyncio.to_thread(lambda: list(islice(rows, size)))
        if not chunk:
            return
        yield chunk
```

- [ ] **Step 4: Run the bulk tests**

Run: `uv run pytest tests/ingest/test_bulk.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Write the failing CAMA parcel tests**

Create `tests/ingest/test_cama_parcels.py`:

```python
import zipfile
from pathlib import Path

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from county.fixedwidth import TooManyBadRows
from db.county_models import ParcelDetail
from db.models import Parcel, ParcelClass
from ingest.cama_ingest import compose_address, ingest_cama

FIXTURE = Path(__file__).parent.parent / "fixtures" / "county" / "cama_fixture.zip"


async def seed(db_engine):
    async with AsyncSession(db_engine) as s:
        s.add(Parcel(parcel_id="A01 00102 0069", parcel_location="920 ANTIOCH SCHOOL RD",
                     parcel_class=ParcelClass.R, acres=0.0, latitude=0.0))
        s.add(Parcel(parcel_id="R72 00304 0025", parcel_location="208 W MONUMENT AVE",
                     parcel_class=ParcelClass.R, acres=0.343,
                     latitude=39.763072, longitude=-84.196600))
        s.add(Parcel(parcel_id="Z99 99999 9999", parcel_location="1 GONE ST",
                     parcel_class=ParcelClass.R, acres=0.1,
                     latitude=39.7, longitude=-84.2))
        await s.commit()


async def get(db_engine, model, key):
    async with AsyncSession(db_engine) as s:
        return await s.get(model, key)


def test_compose_address():
    assert compose_address(2301, "S", "ARAGON", "AVE", None) == "2301 S ARAGON AVE"
    assert compose_address(None, None, "GLENDALE", "AVE", None) == "GLENDALE AVE"
    assert compose_address(0, None, "MAIN", "ST", "APT 4") == "MAIN ST APT 4"


async def test_new_parcels_are_inserted_with_county_data(db_engine):
    await seed(db_engine)
    counts = await ingest_cama(FIXTURE, engine=db_engine)
    assert counts["parcel"] == 4
    p = await get(db_engine, Parcel, "A01 00101 0001")
    assert p.parcel_location == "11974 FREDERICK PIKE"
    assert p.parcel_class == ParcelClass.R
    assert p.acres == pytest.approx(2.0)
    assert (p.neighborhood, p.tax_district, p.land_use_code, p.zip) == (
        "48150000", "A01", "511", "45377"
    )
    assert p.latitude == pytest.approx(39.92128, abs=1e-4)
    assert p.longitude == pytest.approx(-84.27433, abs=1e-4)
    assert (p.coord_source, p.is_active) == ("county", True)


async def test_county_coordinates_replace_the_failed_geocode_sentinel(db_engine):
    await seed(db_engine)
    await ingest_cama(FIXTURE, engine=db_engine)
    p = await get(db_engine, Parcel, "A01 00102 0069")
    assert p.latitude != 0.0
    assert p.coord_source == "county"
    # Existing parcels keep the location string that sales history uses.
    assert p.parcel_location == "920 ANTIOCH SCHOOL RD"


async def test_parcels_missing_from_cama_are_marked_inactive(db_engine):
    await seed(db_engine)
    await ingest_cama(FIXTURE, engine=db_engine)
    gone = await get(db_engine, Parcel, "Z99 99999 9999")
    assert gone.is_active is False
    assert gone.coord_source == "census"  # it kept its geocoded location


async def test_parcel_details(db_engine):
    await ingest_cama(FIXTURE, engine=db_engine)
    d = await get(db_engine, ParcelDetail, "N64 00101 0003")
    assert (d.house_number, d.street_direction, d.street_name, d.street_suffix) == (
        2301, "S", "ARAGON", "AVE"
    )
    assert d.land_use.startswith("R - ")
    assert (d.city, d.zip, d.living_units) == ("DAYTON", "45420", 1)
    rural = await get(db_engine, ParcelDetail, "A01 00101 0001")
    assert rural.lot_acres == pytest.approx(2.0)
    assert rural.lot_sqft == 12632 + 30928 + 43560


async def test_ingest_is_idempotent(db_engine):
    await ingest_cama(FIXTURE, engine=db_engine)
    await ingest_cama(FIXTURE, engine=db_engine)
    async with AsyncSession(db_engine) as s:
        parcels = (await s.exec(select(Parcel))).all()
        details = (await s.exec(select(ParcelDetail))).all()
    assert len(parcels) == 4
    assert len(details) == 4


async def test_corrupt_file_is_rejected_and_nothing_changes(db_engine, tmp_path):
    await seed(db_engine)
    corrupt = tmp_path / "Cama_Files_20260831.zip"
    with zipfile.ZipFile(FIXTURE) as zin, zipfile.ZipFile(corrupt, "w") as zout:
        for name in zin.namelist():
            data = zin.read(name)
            if name.upper().endswith("PARDAT.DAT"):
                # Letters in every record's numeric taxyr column (bytes 37-41).
                data = b"\n".join(
                    line[:36] + b"ZZZZZ" + line[41:] if len(line) > 41 else line
                    for line in data.split(b"\n")
                )
            zout.writestr(name, data)
    with pytest.raises(TooManyBadRows):
        await ingest_cama(corrupt, engine=db_engine)
    gone = await get(db_engine, Parcel, "Z99 99999 9999")
    assert gone.is_active is True
    assert await get(db_engine, Parcel, "A01 00101 0001") is None
```

- [ ] **Step 6: Run them to verify they fail**

Run: `uv run pytest tests/ingest/test_cama_parcels.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ingest.cama_ingest'`

- [ ] **Step 7: Implement the parcel and detail loaders in `src/ingest/cama_ingest.py`**

```python
"""Load a CAMA export into parcel, parcel_detail, dwelling, parcel_feature,
parcel_value and neighborhood, all in one transaction.

Runs in the background population loop. Parsing happens in worker threads
(bulk.in_thread_chunks) so the API keeps serving while a 2 GB export loads.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from county import cama
from county.coords import state_plane_to_wgs84
from db.county_models import ParcelDetail
from db.models import Parcel, ParcelClass
from ingest.bulk import in_thread_chunks, replace_rows, upsert
from logging_config import get_logger

logger = get_logger(__name__)

# ON CONFLICT upserts are single multi-row statements, so size them to stay
# under the 32,766 bind-parameter limit (12 columns x 2,000 rows).
_UPSERT_CHUNK = 2000


@dataclass
class LandTotals:
    acres: float = 0.0
    sqft: int = 0
    frontage: float | None = None
    depth: float | None = None


@dataclass
class LegalInfo:
    latitude: float | None
    longitude: float | None
    tax_district: str | None
    zip: str | None


@dataclass
class CamaContext:
    zip_path: Path
    snapshot: date
    decodes: cama.Decodes
    land: dict[str, LandTotals]
    legdat: dict[str, LegalInfo]


def _checked_rows(zip_path: Path, table: str):
    """Yield a table's rows, then fail if too many were unparseable."""
    reader, rows = cama.read_table(zip_path, table)
    yield from rows
    reader.check()


def load_context(zip_path: Path) -> CamaContext:
    land: dict[str, LandTotals] = {}
    for row in _checked_rows(zip_path, "LAND"):
        totals = land.setdefault(row["parid"], LandTotals())
        totals.acres += row["acres"] or 0.0
        totals.sqft += row["sf"] or 0
        if row["fronact"]:
            totals.frontage = max(totals.frontage or 0.0, row["fronact"])
        if row["depth"]:
            totals.depth = max(totals.depth or 0.0, row["depth"])
    legdat: dict[str, LegalInfo] = {}
    for row in _checked_rows(zip_path, "LEGDAT"):
        coords = state_plane_to_wgs84(row["xcoord"], row["ycoord"])
        legdat[row["parid"]] = LegalInfo(
            latitude=coords[0] if coords else None,
            longitude=coords[1] if coords else None,
            tax_district=row["taxdist"],
            zip=row["zip1"],
        )
    return CamaContext(
        zip_path=zip_path,
        snapshot=cama.snapshot_date(zip_path),
        decodes=cama.load_decodes(zip_path),
        land=land,
        legdat=legdat,
    )


def compose_address(house_number, direction, street, suffix, unit) -> str:
    parts = [str(house_number) if house_number else None, direction, street, suffix, unit]
    return " ".join(p for p in parts if p)


def _unit(row: dict) -> str | None:
    return " ".join(p for p in (row["unitdesc"], row["unitno"]) if p) or None


def _parcel_row(row: dict, ctx: CamaContext) -> dict:
    land = ctx.land.get(row["parid"], LandTotals())
    legal = ctx.legdat.get(row["parid"])
    acres = land.acres or row["acres"] or 0.0
    return {
        "parcel_id": row["parid"],
        "parcel_location": compose_address(
            row["adrno"], row["adrdir"], row["adrstr"], row["adrsuf"], _unit(row)
        ),
        "parcel_class": ParcelClass.__members__.get((row["class"] or "")[:1], ParcelClass.R),
        "acres": round(acres, 4),
        "latitude": legal.latitude if legal else None,
        "longitude": legal.longitude if legal else None,
        "coord_source": "county" if legal and legal.latitude is not None else None,
        "neighborhood": row["nbhd"],
        "tax_district": (legal.tax_district if legal else None) or row["parid"][:3],
        "land_use_code": row["luc"],
        "zip": row["zip1"] or (legal.zip if legal else None),
        "is_active": True,
    }


async def load_parcels(conn: AsyncConnection, ctx: CamaContext) -> int:
    table = Parcel.__table__
    # Everything starts inactive; parcels present in this export flip back.
    await conn.execute(sa.update(table).values(is_active=False))
    written = 0
    async for chunk in in_thread_chunks(
        (_parcel_row(r, ctx) for r in _checked_rows(ctx.zip_path, "PARDAT")), size=_UPSERT_CHUNK
    ):
        stmt = upsert(conn)(table).values(chunk)
        excluded = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=["parcel_id"],
            set_={
                # Keep the sales-history location string, class and acres of
                # parcels we already know; refresh the county-owned columns.
                "neighborhood": excluded.neighborhood,
                "tax_district": excluded.tax_district,
                "land_use_code": excluded.land_use_code,
                "zip": excluded.zip,
                "is_active": excluded.is_active,
                "latitude": sa.func.coalesce(excluded.latitude, table.c.latitude),
                "longitude": sa.func.coalesce(excluded.longitude, table.c.longitude),
                "coord_source": sa.func.coalesce(excluded.coord_source, table.c.coord_source),
            },
        )
        await conn.execute(stmt)
        written += len(chunk)
    # Parcels still located only by the Census geocoder (0.0 marks a failure).
    await conn.execute(
        sa.update(table)
        .where(table.c.coord_source.is_(None), table.c.latitude.isnot(None),
               table.c.latitude != 0)
        .values(coord_source="census")
    )
    return written


def _detail_row(row: dict, ctx: CamaContext) -> dict:
    land = ctx.land.get(row["parid"], LandTotals())
    return {
        "parcel_id": row["parid"],
        "land_use_code": row["luc"],
        "land_use": ctx.decodes.label("ASMT", "LUC", row["luc"]),
        "living_units": row["livunit"],
        "house_number": row["adrno"] or None,
        "street_direction": row["adrdir"],
        "street_name": row["adrstr"],
        "street_suffix": row["adrsuf"],
        "unit": _unit(row),
        "city": row["cityname"],
        "zip": row["zip1"],
        "lot_sqft": land.sqft or None,
        "lot_acres": round(land.acres, 4) if land.acres else row["acres"],
        "frontage_ft": land.frontage,
        "depth_ft": land.depth,
        "snapshot_date": ctx.snapshot,
    }


async def load_parcel_details(conn: AsyncConnection, ctx: CamaContext) -> int:
    await conn.execute(sa.delete(ParcelDetail.__table__))
    written = 0
    async for chunk in in_thread_chunks(
        (_detail_row(r, ctx) for r in _checked_rows(ctx.zip_path, "PARDAT"))
    ):
        await conn.execute(sa.insert(ParcelDetail.__table__), chunk)
        written += len(chunk)
    return written


async def ingest_cama(zip_path: Path, engine: AsyncEngine | None = None) -> dict[str, int]:
    if engine is None:
        from db.engine import engine as default_engine

        engine = default_engine
    ctx = await asyncio.to_thread(load_context, Path(zip_path))
    counts: dict[str, int] = {}
    async with engine.begin() as conn:
        counts["parcel"] = await load_parcels(conn, ctx)
        counts["parcel_detail"] = await load_parcel_details(conn, ctx)
    logger.info("CAMA %s ingested: %s", ctx.snapshot, counts)
    return counts
```

`replace_rows` is imported for Tasks 9 and 10, which add loaders here; ruff flags it as unused until then, so add it to the import in Task 9 instead if lint complains now.

- [ ] **Step 8: Run the tests**

Run: `uv run pytest tests/ingest -v`
Expected: all tests PASS. `test_corrupt_file_is_rejected_and_nothing_changes` passes because `_checked_rows` raises `TooManyBadRows` inside the `engine.begin()` block, which rolls back the `is_active` reset and every upsert.

- [ ] **Step 9: Lint and commit**

```bash
uv run ruff check src tests
git add src/ingest tests/ingest
git commit -m "Load CAMA parcels, details and county coordinates in one transaction"
```

---

### Task 9: CAMA dwellings, floor-plan sketches and outbuildings

**Files:**
- Modify: `src/ingest/cama_ingest.py`
- Test: `tests/ingest/test_cama_buildings.py`

**Interfaces:**
- Consumes: `CamaContext`, `_checked_rows`, `in_thread_chunks`, `replace_rows` (Task 8).
- Produces:
  - `ATTACHED_GARAGE_CODES = {"13", "23"}` and `PLACEHOLDER_YEARS = {1900, 1919}`.
  - `sketch_lines(addn_rows: list[dict]) -> list[dict]` returning `[{"line": int, "codes": list[str], "area": int | None, "vector": str | None}, ...]` sorted by line.
  - `async load_dwellings(conn, ctx) -> int`, `async load_features(conn, ctx) -> int`, both called by `ingest_cama`, which now also returns counts for `"dwelling"` and `"parcel_feature"`.
  - `Dwelling.sketch` holds `json.dumps(sketch_lines(...))`. Plan 1B draws the floor plan from it; vector moves are `U`/`D`/`L`/`R` plus a distance in feet, `C` marks the start of the outline, `X` a diagonal, `V` a hidden (non-drawn) move, `N` means no sketch.

- [ ] **Step 1: Write the failing tests**

Create `tests/ingest/test_cama_buildings.py`:

```python
import json
from pathlib import Path

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from db.county_models import Dwelling, ParcelFeature
from ingest.cama_ingest import ingest_cama, sketch_lines

FIXTURE = Path(__file__).parent.parent / "fixtures" / "county" / "cama_fixture.zip"


async def dwelling(db_engine, parcel_id, card=1):
    async with AsyncSession(db_engine) as s:
        return await s.get(Dwelling, (parcel_id, card))


async def test_dwelling_decoded(db_engine):
    counts = await ingest_cama(FIXTURE, engine=db_engine)
    assert counts["dwelling"] == 5
    d = await dwelling(db_engine, "A01 00101 0001")
    assert (d.living_sqft, d.first_floor_sqft, d.beds, d.full_baths, d.half_baths) == (
        2464, 900, 3, 1, 0
    )
    assert (d.style_code, d.style, d.stories) == ("05", "OLD STYLE", 2.0)
    assert (d.year_built, d.year_built_is_placeholder) == (1919, True)
    assert (d.grade, d.grade_label, d.condition) == ("C+", "AVERAGE +", "VERY GOOD")
    assert (d.exterior, d.basement, d.heating, d.fuel) == ("FRAME", "PART", "CENTRAL HEAT", "OIL")
    assert d.has_central_air is False
    assert (d.attached_garage_sqft, d.basement_garage_cars) == (0, 1)


async def test_attached_garage_and_air(db_engine):
    await ingest_cama(FIXTURE, engine=db_engine)
    ranch = await dwelling(db_engine, "N64 00101 0003")
    assert (ranch.attached_garage_sqft, ranch.has_central_air, ranch.style) == (384, True, "RANCH")
    second = await dwelling(db_engine, "A01 00102 0069", card=2)
    assert (second.living_sqft, second.attached_garage_sqft) == (720, 552)


async def test_sketch_json(db_engine):
    await ingest_cama(FIXTURE, engine=db_engine)
    ranch = await dwelling(db_engine, "N64 00101 0003")
    lines = json.loads(ranch.sketch)
    assert [line["line"] for line in lines] == [0, 1, 2]
    assert lines[0] == {"line": 0, "codes": [], "area": 1008, "vector": "A0CU24R42D24L42"}
    assert lines[1]["codes"] == ["13"]
    assert lines[2]["codes"] == ["33", "32"]


def test_sketch_lines_sorts_and_drops_blank_codes():
    rows = [
        {"lline": 1, "lower": None, "first": "13", "second": None, "third": None,
         "area": 384, "vect": "A1R42"},
        {"lline": 0, "lower": None, "first": None, "second": None, "third": None,
         "area": 1008, "vect": "A0CU24"},
    ]
    assert [line["line"] for line in sketch_lines(rows)] == [0, 1]
    assert sketch_lines(rows)[0]["codes"] == []


async def test_features(db_engine):
    counts = await ingest_cama(FIXTURE, engine=db_engine)
    assert counts["parcel_feature"] == 6
    async with AsyncSession(db_engine) as s:
        items = (await s.exec(
            select(ParcelFeature).where(ParcelFeature.parcel_id == "R72 00304 0025")
        )).all()
    garage = next(i for i in items if i.code == "RG1")
    assert garage.description == "FRAME OR CB DETACHED GARAGE"
    assert (garage.area_sqft, garage.width_ft, garage.length_ft, garage.year_built) == (
        960, 40, 24, 2000
    )
    assert garage.condition == "AVERAGE"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/ingest/test_cama_buildings.py -v`
Expected: FAIL with `ImportError: cannot import name 'sketch_lines'`

- [ ] **Step 3: Implement the loaders**

Add to `src/ingest/cama_ingest.py` (imports: `import json`, `from collections import defaultdict`, and `Dwelling`, `ParcelFeature` from `db.county_models`):

```python
ATTACHED_GARAGE_CODES = {"13", "23"}
# 1919 means "built before 1920" (4,096 dwellings vs ~500 for neighboring
# years); 1900 is similarly inflated. Shown as approximate in the UI.
PLACEHOLDER_YEARS = {1900, 1919}
_ADDN_CODE_FIELDS = ("lower", "first", "second", "third")


def sketch_lines(addn_rows: list[dict]) -> list[dict]:
    return [
        {
            "line": row["lline"],
            "codes": [row[f] for f in _ADDN_CODE_FIELDS if row[f]],
            "area": row["area"],
            "vector": row["vect"],
        }
        for row in sorted(addn_rows, key=lambda r: r["lline"])
    ]


def _addn_by_card(zip_path: Path) -> dict[tuple[str, int], list[dict]]:
    """ADDN lines grouped per dwelling card, keeping only the fields we use."""
    grouped: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in _checked_rows(zip_path, "ADDN"):
        grouped[(row["parid"], row["card"])].append(
            {k: row[k] for k in ("lline", "area", "vect", *_ADDN_CODE_FIELDS)}
        )
    return grouped


def _dwelling_row(row: dict, addn: list[dict], ctx: CamaContext) -> dict:
    label = ctx.decodes.label
    garage = sum(
        line["area"] or 0
        for line in addn
        if ATTACHED_GARAGE_CODES & {line[f] for f in _ADDN_CODE_FIELDS}
    )
    return {
        "parcel_id": row["parid"],
        "card": row["card"],
        "living_sqft": row["sfla"],
        "first_floor_sqft": row["flr1area"],
        "finished_basement_sqft": row["finbsmtarea"] or None,
        "beds": row["rmbed"],
        "full_baths": row["fixbath"],
        "half_baths": row["fixhalf"],
        "stories": row["stories"],
        "style_code": row["style"],
        "style": label("DWELDAT", "STYLE", row["style"]),
        "year_built": row["yrblt"] or None,
        "year_built_is_placeholder": row["yrblt"] in PLACEHOLDER_YEARS,
        "grade": row["grade"],
        "grade_label": ctx.decodes.grade(row["grade"]),
        "condition": label("DWELDAT", "CDU", row["cdu"]),
        "exterior": label("DWELDAT", "EXTWALL", row["extwall"]),
        "basement": label("DWELDAT", "BSMT", row["bsmt"]),
        "heating": ctx.decodes.heat(row["heat"]),
        "fuel": label("DWELDAT", "FUEL", row["fuel"]),
        "has_central_air": row["heat"] == "4",
        "fireplaces": (row["wbfp_o"] or 0) + (row["wbfp_s"] or 0) + (row["wbfp_pf"] or 0),
        "attached_garage_sqft": garage,
        "basement_garage_cars": row["bsmtcar"] or 0,
        "sketch": json.dumps(sketch_lines(addn)) if addn else None,
        "snapshot_date": ctx.snapshot,
    }


async def load_dwellings(conn: AsyncConnection, ctx: CamaContext) -> int:
    addn = await asyncio.to_thread(_addn_by_card, ctx.zip_path)
    await conn.execute(sa.delete(Dwelling.__table__))
    written = 0
    rows = (
        _dwelling_row(r, addn.get((r["parid"], r["card"]), []), ctx)
        for r in _checked_rows(ctx.zip_path, "DWELL")
    )
    async for chunk in in_thread_chunks(rows):
        await conn.execute(sa.insert(Dwelling.__table__), chunk)
        written += len(chunk)
    return written


def _feature_row(row: dict, ctx: CamaContext) -> dict:
    return {
        "parcel_id": row["parid"],
        "card": row["card"],
        "line": row["lline"],
        "code": row["code"],
        "description": ctx.decodes.outbuilding(row["code"]),
        "year_built": row["yrblt"] or None,
        "area_sqft": row["area"],
        "width_ft": row["meas1"],
        "length_ft": row["meas2"],
        "condition": ctx.decodes.label("OBY", "COND", row["cond"]),
        "snapshot_date": ctx.snapshot,
    }


async def load_features(conn: AsyncConnection, ctx: CamaContext) -> int:
    await conn.execute(sa.delete(ParcelFeature.__table__))
    written = 0
    rows = (_feature_row(r, ctx) for r in _checked_rows(ctx.zip_path, "OBY") if r["code"])
    async for chunk in in_thread_chunks(rows):
        await conn.execute(sa.insert(ParcelFeature.__table__), chunk)
        written += len(chunk)
    return written
```

In `ingest_cama`, after the details line add:

```python
        counts["dwelling"] = await load_dwellings(conn, ctx)
        counts["parcel_feature"] = await load_features(conn, ctx)
```

Remove the unused `replace_rows` import if ruff flags it.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/ingest -v`
Expected: all tests PASS. The fixture has 5 dwelling cards (A01 00101 0001, two for A01 00102 0069, N64 00101 0003, R72 00304 0025 card 2) and 6 outbuildings.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/ingest/cama_ingest.py tests/ingest/test_cama_buildings.py
git commit -m "Load CAMA dwellings with floor-plan sketches, and outbuildings"
```

---

### Task 10: CAMA values, neighborhoods and tax districts

**Files:**
- Modify: `src/ingest/cama_ingest.py`
- Create: `src/ingest/neighborhood_ingest.py`
- Test: `tests/ingest/test_cama_values.py`, `tests/ingest/test_neighborhood_ingest.py`

**Interfaces:**
- Consumes: Task 8 helpers; `neighborhood_names`, `load_decodes` (Task 3); `parse_neighborhood_codes`, `neighborhood_display_name`, `district_info`, `jurisdiction_name` (Task 5).
- Produces:
  - `value_method(revcode: str | None) -> str | None`, `appeal_year(revreas: str | None) -> int | None`.
  - `async load_values(conn, ctx) -> int`; `ingest_cama` returns a `"parcel_value"` count.
  - `async load_neighborhoods_from_cama(conn, ctx) -> int`: inserts codes that are missing (never overwrites names), then sets each neighborhood's `tax_district` to the most common tax district among its parcels. `ingest_cama` returns a `"neighborhood"` count.
  - `async load_tax_districts(conn) -> int`: rebuilds `tax_district` from the distinct `parcel.tax_district` codes. Called at the end of `ingest_cama`; count `"tax_district"`.
  - `neighborhood_ingest.ingest_neighborhood_names(html_path: Path, engine: AsyncEngine | None = None) -> int`: upserts official names from the county page (overwrites name and display name).

- [ ] **Step 1: Write the failing tests**

Create `tests/ingest/test_cama_values.py`:

```python
from pathlib import Path

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from db.county_models import Neighborhood, ParcelValue, TaxDistrict
from ingest.cama_ingest import appeal_year, ingest_cama, value_method

FIXTURE = Path(__file__).parent.parent / "fixtures" / "county" / "cama_fixture.zip"


def test_value_method_and_appeal_year():
    assert value_method("1") == "cost"
    assert value_method("3") == "override"
    assert value_method("4") == "income"
    assert value_method(None) is None
    assert appeal_year("B20") == 2020
    assert appeal_year("B96") == 1996
    assert appeal_year("TIF") is None
    assert appeal_year(None) is None


async def test_values(db_engine):
    counts = await ingest_cama(FIXTURE, engine=db_engine)
    assert counts["parcel_value"] == 4
    async with AsyncSession(db_engine) as s:
        rural = await s.get(ParcelValue, "A01 00101 0001")
        dayton = await s.get(ParcelValue, "R72 00304 0025")
        ranch = await s.get(ParcelValue, "N64 00101 0003")
    assert (rural.land_2025, rural.building_2025, rural.total_2025) == (73980, 200340, 274320)
    assert (rural.land_2026, rural.building_2026, rural.total_2026) == (85370, 182190, 267560)
    assert rural.change_pct == pytest.approx(-2.464, abs=1e-3)
    assert rural.reappraisal_reason == "REAPPRAISAL"
    assert (rural.value_method, rural.tif) == ("cost", False)
    assert (dayton.tif, dayton.value_method) == (True, "override")
    assert ranch.change_pct == pytest.approx(18.699, abs=1e-3)


async def test_neighborhoods_and_districts(db_engine):
    await ingest_cama(FIXTURE, engine=db_engine)
    async with AsyncSession(db_engine) as s:
        butler = await s.get(Neighborhood, "48150000")
        districts = {d.code: d for d in (await s.exec(select(TaxDistrict))).all()}
    assert (butler.name, butler.display_name, butler.tax_district) == (
        "N BUTLER TWP", "N BUTLER TWP", "A01"
    )
    assert set(districts) == {"A01", "N64", "R72"}
    assert districts["R72"].jurisdiction == "DAYTON"
```

Create `tests/ingest/test_neighborhood_ingest.py`:

```python
from pathlib import Path

from sqlmodel.ext.asyncio.session import AsyncSession

from db.county_models import Neighborhood
from ingest.cama_ingest import ingest_cama
from ingest.neighborhood_ingest import ingest_neighborhood_names

FIXTURE = Path(__file__).parent.parent / "fixtures" / "county" / "cama_fixture.zip"
PAGE = (
    b"<tr>\r\n<td>\r\n48150000\r\n</td>\r\n<td>\r\nNORTH BUTLER TOWNSHIP\r\n</td>\r\n</tr>\r\n"
    b"<tr>\r\n<td>\r\n82000ARL\r\n</td>\r\n<td>\r\nSW PRIORITY BOARD-ARLINGTON HEIGHTS\r\n"
    b"</td>\r\n</tr>"
)


async def test_official_names_win_over_cama_names_in_either_order(db_engine, tmp_path):
    page = tmp_path / "neighborhood_codes_20260901.htm"
    page.write_bytes(PAGE)
    assert await ingest_neighborhood_names(page, engine=db_engine) == 2
    await ingest_cama(FIXTURE, engine=db_engine)
    async with AsyncSession(db_engine) as s:
        butler = await s.get(Neighborhood, "48150000")
        arlington = await s.get(Neighborhood, "82000ARL")
    assert butler.name == "NORTH BUTLER TOWNSHIP"
    assert butler.tax_district == "A01"
    assert (arlington.name, arlington.display_name) == (
        "SW PRIORITY BOARD-ARLINGTON HEIGHTS", "ARLINGTON HEIGHTS"
    )
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/ingest/test_cama_values.py tests/ingest/test_neighborhood_ingest.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement values, neighborhoods and districts**

Add to `src/ingest/cama_ingest.py` (imports: `from collections import Counter`; `ParcelValue`, `Neighborhood`, `TaxDistrict` from `db.county_models`; `from county.neighborhood_codes import neighborhood_display_name`; `from county.tax_districts import district_info, jurisdiction_name`):

```python
_VALUE_METHODS = {"1": "cost", "3": "override", "4": "income", "5": "cost (income suppressed)"}


def value_method(revcode: str | None) -> str | None:
    return _VALUE_METHODS.get(revcode) if revcode else None


def appeal_year(revreas: str | None) -> int | None:
    """Board of Revision appeals are coded B + 2-digit year (B96, B20)."""
    if not revreas or len(revreas) != 3 or revreas[0] != "B" or not revreas[1:].isdigit():
        return None
    yy = int(revreas[1:])
    return 2000 + yy if yy <= 40 else 1900 + yy


def _values_2026(zip_path: Path) -> dict[str, dict]:
    """2026 reappraisal values. Three parcels have two rows (split class): sum them."""
    out: dict[str, dict] = {}
    for row in _checked_rows(zip_path, "ASMT"):
        entry = out.setdefault(row["parid"], {"land": 0, "building": 0, "reascd": row["reascd"]})
        entry["land"] += row["aprland"] or 0
        entry["building"] += row["aprbldg"] or 0
    return out


def _value_row(row: dict, v2026: dict | None, ctx: CamaContext) -> dict:
    total_2025 = row["aprtot"]
    total_2026 = (v2026["land"] + v2026["building"]) if v2026 else None
    change = None
    if total_2025 and total_2026 is not None:
        change = round((total_2026 - total_2025) / total_2025 * 100, 3)
    return {
        "parcel_id": row["parid"],
        "land_2025": row["aprland"],
        "building_2025": row["aprbldg"],
        "total_2025": total_2025,
        "land_2026": v2026["land"] if v2026 else None,
        "building_2026": v2026["building"] if v2026 else None,
        "total_2026": total_2026,
        "change_pct": change,
        "value_method": value_method(row["revcode"]),
        "appeal_year": appeal_year(row["revreas"]),
        "tif": row["revreas"] == "TIF",
        "abated": row["revreas"] == "ABA",
        "reappraisal_reason": ctx.decodes.label("ASMT", "REASCD", v2026["reascd"])
        if v2026 else None,
        "snapshot_date": ctx.snapshot,
    }


async def load_values(conn: AsyncConnection, ctx: CamaContext) -> int:
    v2026 = await asyncio.to_thread(_values_2026, ctx.zip_path)
    await conn.execute(sa.delete(ParcelValue.__table__))
    written = 0
    rows = (
        _value_row(r, v2026.get(r["parid"]), ctx)
        for r in _checked_rows(ctx.zip_path, "APRVAL")
    )
    async for chunk in in_thread_chunks(rows):
        await conn.execute(sa.insert(ParcelValue.__table__), chunk)
        written += len(chunk)
    return written


async def load_neighborhoods_from_cama(conn: AsyncConnection, ctx: CamaContext) -> int:
    names = await asyncio.to_thread(cama.neighborhood_names, ctx.zip_path)
    table = Neighborhood.__table__
    rows = [
        {"code": code, "name": name, "display_name": neighborhood_display_name(name)}
        for code, name in names.items()
    ]
    for i in range(0, len(rows), 1000):
        stmt = upsert(conn)(table).values(rows[i : i + 1000])
        await conn.execute(stmt.on_conflict_do_nothing(index_elements=["code"]))
    parcel = Parcel.__table__
    pairs = await conn.execute(
        sa.select(parcel.c.neighborhood, parcel.c.tax_district, sa.func.count())
        .where(parcel.c.neighborhood.isnot(None), parcel.c.is_active.is_(True))
        .group_by(parcel.c.neighborhood, parcel.c.tax_district)
    )
    tallies: dict[str, Counter] = {}
    for code, district, n in pairs:
        tallies.setdefault(code, Counter())[district] += n
    for code, counter in tallies.items():
        await conn.execute(
            sa.update(table).where(table.c.code == code)
            .values(tax_district=counter.most_common(1)[0][0])
        )
    return len(rows)


async def load_tax_districts(conn: AsyncConnection) -> int:
    parcel = Parcel.__table__
    codes = (await conn.execute(
        sa.select(parcel.c.tax_district).where(parcel.c.tax_district.isnot(None)).distinct()
    )).scalars().all()
    rows = []
    for code in codes:
        name, school = district_info(code)
        rows.append({"code": code, "name": name, "jurisdiction": jurisdiction_name(code),
                     "school_district": school})
    return await replace_rows(conn, TaxDistrict.__table__, rows)
```

In `ingest_cama`, append inside the transaction:

```python
        counts["parcel_value"] = await load_values(conn, ctx)
        counts["neighborhood"] = await load_neighborhoods_from_cama(conn, ctx)
        counts["tax_district"] = await load_tax_districts(conn)
```

Create `src/ingest/neighborhood_ingest.py`:

```python
"""Official neighborhood names from the county's monthly codes page."""
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine

from county.neighborhood_codes import neighborhood_display_name, parse_neighborhood_codes
from db.county_models import Neighborhood
from ingest.bulk import upsert


async def ingest_neighborhood_names(html_path: Path, engine: AsyncEngine | None = None) -> int:
    if engine is None:
        from db.engine import engine as default_engine

        engine = default_engine
    names = parse_neighborhood_codes(Path(html_path).read_bytes())
    rows = [
        {"code": code, "name": name, "display_name": neighborhood_display_name(name)}
        for code, name in names.items()
    ]
    table = Neighborhood.__table__
    async with engine.begin() as conn:
        for i in range(0, len(rows), 1000):
            stmt = upsert(conn)(table).values(rows[i : i + 1000])
            await conn.execute(stmt.on_conflict_do_update(
                index_elements=["code"],
                set_={"name": stmt.excluded.name, "display_name": stmt.excluded.display_name},
            ))
    return len(rows)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/ingest -v`
Expected: all tests PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/ingest tests/ingest
git commit -m "Load CAMA values, neighborhood names and tax districts"
```

---

### Task 11: Tax roll ingest and occupancy classification

**Files:**
- Create: `src/ingest/taxroll_ingest.py`
- Test: `tests/ingest/test_taxroll_ingest.py`

**Interfaces:**
- Consumes: `TaxRollReader`, `snapshot_date` (Task 4); `classify_owner_name`, `mailing_state` (Task 5); `normalize_search` (Task 5); `replace_rows`, `in_thread_chunks` (Task 8).
- Produces:
  - `classify_occupancy(*, owner_occupied: bool, homestead: bool, owner_name: str | None, mailing_address1: str | None, situs: str | None) -> tuple[str, str]` returning `(category, reason)` where category is one of `OCCUPANCY_CATEGORIES`.
  - `async ingest_taxroll(zip_path: Path, engine: AsyncEngine | None = None) -> int` replaces `parcel_tax` and copies `census_tract` onto `parcel`.
  - `parcel_tax.owner_search` is not a column; search keys live on `parcel_summary` (Task 12), built from `parcel_tax.owner_name`.

Classification rules (spec 6.4, with one refinement): owner-occupied if the owner-occupancy credit or homestead is present; otherwise government, company or trust by owner name; otherwise an individual mailing somewhere other than the property is an absentee individual; an individual who mails to the property but has no credit is `unknown` (usually a recent buyer whose credit has not been applied yet, per the CAMA findings).

- [ ] **Step 1: Write the failing tests**

Create `tests/ingest/test_taxroll_ingest.py`:

```python
from pathlib import Path

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from db.county_models import ParcelTax
from db.models import Parcel, ParcelClass
from ingest.taxroll_ingest import classify_occupancy, ingest_taxroll

FIXTURE = Path(__file__).parent.parent / "fixtures" / "county" / "taxroll_fixture.zip"


@pytest.mark.parametrize(
    ("kwargs", "category"),
    [
        (dict(owner_occupied=True, homestead=False, owner_name="VB ELEVEN LLC"), "owner_occupied"),
        (dict(owner_occupied=False, homestead=True, owner_name="SMITH JOHN"), "owner_occupied"),
        (dict(owner_occupied=False, homestead=False, owner_name="CITY OF DAYTON"), "government"),
        (dict(owner_occupied=False, homestead=False, owner_name="VB ELEVEN LLC"), "company"),
        (dict(owner_occupied=False, homestead=False, owner_name="SMITH FAMILY TRUST"), "trust"),
        (dict(owner_occupied=False, homestead=False, owner_name="SMITH JOHN",
              mailing_address1="PO BOX 12", situs="10 ELM ST"), "absentee_individual"),
        (dict(owner_occupied=False, homestead=False, owner_name="SMITH JOHN",
              mailing_address1="10 elm st.", situs="10 ELM ST"), "unknown"),
    ],
)
def test_classify_occupancy(kwargs, category):
    kwargs = {"mailing_address1": None, "situs": None, **kwargs}
    got, reason = classify_occupancy(**kwargs)
    assert got == category
    assert reason


async def test_ingest_taxroll(db_engine):
    async with AsyncSession(db_engine) as s:
        s.add(Parcel(parcel_id="A01 00101 0001", parcel_location="11974 FREDERICK PIKE",
                     parcel_class=ParcelClass.R, acres=2.0))
        await s.commit()
    assert await ingest_taxroll(FIXTURE, engine=db_engine) == 4
    async with AsyncSession(db_engine) as s:
        row = await s.get(ParcelTax, "A01 00101 0001")
        parcel = await s.get(Parcel, "A01 00101 0001")
        count = len((await s.exec(select(ParcelTax))).all())
    assert count == 4
    assert row.annual_bill == pytest.approx(6066.22)
    assert (row.tax_year, row.owner_occupied, row.occupancy) == (2025, True, "owner_occupied")
    assert row.owner_name == "MULLENAX SAMANTHA MARIE"
    assert row.mailing_state == "OH"
    assert row.out_of_state is False
    assert row.mailing_address == "11974 FREDERICK PIKE, VANDALIA OH 45377"
    assert parcel.census_tract == "39113-110100-1"


async def test_reingest_replaces_rows(db_engine):
    await ingest_taxroll(FIXTURE, engine=db_engine)
    await ingest_taxroll(FIXTURE, engine=db_engine)
    async with AsyncSession(db_engine) as s:
        assert len((await s.exec(select(ParcelTax))).all()) == 4
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/ingest/test_taxroll_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/ingest/taxroll_ingest.py`**

```python
"""Load the daily tax roll into parcel_tax (current tax year, one row per parcel)."""
from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from county.owners import classify_owner_name, mailing_state
from county.taxroll import TaxRollReader, snapshot_date
from county.text import normalize_search
from db.county_models import ParcelTax
from db.models import Parcel
from ingest.bulk import in_thread_chunks
from logging_config import get_logger

logger = get_logger(__name__)


def classify_occupancy(
    *,
    owner_occupied: bool,
    homestead: bool,
    owner_name: str | None,
    mailing_address1: str | None,
    situs: str | None,
) -> tuple[str, str]:
    if owner_occupied:
        return "owner_occupied", "Receives the owner-occupancy tax credit"
    if homestead:
        return "owner_occupied", "Has a homestead exemption"
    kind = classify_owner_name(owner_name)
    if kind:
        return kind, f"Owner name indicates a {kind}"
    mailing = normalize_search(mailing_address1)
    if mailing and mailing == normalize_search(situs):
        return "unknown", "Mails to the property but has no owner-occupancy credit yet"
    return "absentee_individual", "Individual owner with a mailing address elsewhere"


def _tax_row(row: dict, snapshot) -> dict:
    category, reason = classify_occupancy(
        owner_occupied=row["owner_occupied"],
        homestead=row["homestead"],
        owner_name=row["owner_name"],
        mailing_address1=row["mailing_address1"],
        situs=row["location"],
    )
    state = mailing_state(row["mailing_address3"]) or mailing_state(row["mailing_address2"])
    address = ", ".join(
        a for a in (row["mailing_address1"], row["mailing_address2"], row["mailing_address3"]) if a
    )
    return {
        "parcel_id": row["parcel_id"],
        "tax_year": row["tax_year"],
        "snapshot_date": snapshot,
        "annual_bill": row["annual_bill"],
        "gross_rate": row["gross_rate"],
        "effective_rate": row["effective_rate"],
        "market_value": row["market_value"],
        "owner_occupied": row["owner_occupied"],
        "homestead": row["homestead"],
        "rental_registered": row["rental_registered"],
        "foreclosure_date": row["foreclosure_date"],
        "cauv": row["cauv"],
        "abated": row["abated"],
        "net_delinquent": row["net_delinquent"],
        "balance_due": row["balance_due"],
        "census_tract": row["census_tract"],
        "zip": row["zip"],
        "city": row["city"],
        "owner_name": row["owner_name"],
        "owner_name2": row["owner_name2"],
        "mailing_name": row["mailing_name"],
        "mailing_address": address or None,
        "mailing_state": state,
        "out_of_state": state is not None and state != "OH",
        "occupancy": category,
        "occupancy_reason": reason,
    }


_COPY_TRACT = sa.text(
    """
    UPDATE parcel SET census_tract = (
        SELECT t.census_tract FROM parcel_tax t WHERE t.parcel_id = parcel.parcel_id
    )
    WHERE EXISTS (
        SELECT 1 FROM parcel_tax t WHERE t.parcel_id = parcel.parcel_id
          AND t.census_tract IS NOT NULL
    )
    """
)


async def ingest_taxroll(zip_path: Path, engine: AsyncEngine | None = None) -> int:
    if engine is None:
        from db.engine import engine as default_engine

        engine = default_engine
    snapshot = snapshot_date(zip_path)
    reader = TaxRollReader()

    def rows():
        seen = set()
        for row in reader.rows(Path(zip_path)):
            # Parcel ids are unique in practice; guard so one duplicate cannot
            # abort the whole load on the primary key.
            if row["parcel_id"] not in seen:
                seen.add(row["parcel_id"])
                yield _tax_row(row, snapshot)
        reader.check()

    table = ParcelTax.__table__
    written = 0
    async with engine.begin() as conn:
        await conn.execute(sa.delete(table))
        async for chunk in in_thread_chunks(rows()):
            await conn.execute(sa.insert(table), chunk)
            written += len(chunk)
        await conn.execute(_COPY_TRACT)
    logger.info("Tax roll %s ingested: %d parcels", snapshot, written)
    return written
```

Remove the unused `Parcel` import if ruff flags it.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/ingest/test_taxroll_ingest.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/ingest/taxroll_ingest.py tests/ingest/test_taxroll_ingest.py
git commit -m "Load the tax roll with occupancy classification"
```

---

### Task 12: Parcel summary, neighborhood summary and data version

**Files:**
- Create: `src/derived/__init__.py`, `src/derived/summary.py`
- Test: `tests/derived/__init__.py`, `tests/derived/test_summary.py`

**Interfaces:**
- Consumes: all tables from Tasks 7-11; `market_sale_criteria` (`src/db/criteria.py`); `normalize_search`, `street_key` (Task 5).
- Produces:
  - `async build_parcel_summary(conn) -> int`: rebuilds `parcel_summary` for every parcel.
  - `async build_neighborhood_summary(conn, anchor: date) -> int`.
  - `async latest_sale_date(conn) -> date | None` (newest market sale in the DB; the anchor for every "last N months" window).
  - `async bump_data_version(conn) -> int` (returns the new version).
  - `async current_data_version(conn) -> int` (0 when never built).
  - `async rebuild_derived(engine: AsyncEngine | None = None) -> int`: runs the three builders in one transaction and returns the new version. Task 13 extends it to write the map binary.
  - Last-sale rule: the newest transaction that passes `market_sale_criteria()` and is not part of a multi-parcel deal (same date, buyer and price on more than one row), matching the existing market-stats rule.
  - Dwelling aggregation: `living_sqft`, `beds` and `baths` (full + 0.5 x half) sum across cards; `year_built` and its placeholder flag come from the card with the largest living area.

- [ ] **Step 1: Write the failing tests**

Create `tests/derived/__init__.py` (empty) and `tests/derived/test_summary.py`:

```python
import datetime as dt
from pathlib import Path

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from db.county_models import NeighborhoodSummary, ParcelSummary
from db.models import Parcel, ParcelClass, Transaction
from derived.summary import current_data_version, rebuild_derived
from ingest.cama_ingest import ingest_cama
from ingest.taxroll_ingest import ingest_taxroll

FIXTURES = Path(__file__).parent.parent / "fixtures" / "county"


def sale(parcel_id, day, price, buyer="BUYER A", seller="SELLER B", validity="VALID SALE"):
    return Transaction(
        parcel_id=parcel_id, sale_date=day, sale_price=price, old_owner=seller, new_owner=buyer,
        parcel_location="X", mailing_name=buyer, mailing_address="X",
        parcel_class=ParcelClass.R, acres=0.1, taxable_land=0, taxable_building=0,
        taxable_total=0, sale_validity=validity,
    )


@pytest.fixture
async def loaded(db_engine):
    async with AsyncSession(db_engine) as s:
        s.add(Parcel(parcel_id="Z99 99999 9999", parcel_location="1 GONE ST",
                     parcel_class=ParcelClass.R, acres=0.1))
        await s.commit()
    await ingest_cama(FIXTURES / "cama_fixture.zip", engine=db_engine)
    await ingest_taxroll(FIXTURES / "taxroll_fixture.zip", engine=db_engine)
    async with AsyncSession(db_engine) as s:
        s.add_all([
            sale("N64 00101 0003", dt.date(2019, 5, 1), 90_000),
            sale("N64 00101 0003", dt.date(2025, 6, 1), 150_000),
            # A later nominal transfer is not a market sale.
            sale("N64 00101 0003", dt.date(2025, 9, 1), 1, buyer="HEIR C"),
            # One deal covering two parcels: not a per-parcel price.
            sale("A01 00101 0001", dt.date(2025, 7, 1), 900_000, buyer="FUND LLC"),
            sale("A01 00102 0069", dt.date(2025, 7, 1), 900_000, buyer="FUND LLC"),
            sale("Z99 99999 9999", dt.date(2010, 1, 1), 50_000),
        ])
        await s.commit()
    return db_engine


async def summary(engine, parcel_id):
    async with AsyncSession(engine) as s:
        return await s.get(ParcelSummary, parcel_id)


async def test_last_market_sale_and_price_per_sqft(loaded):
    await rebuild_derived(engine=loaded)
    ranch = await summary(loaded, "N64 00101 0003")
    assert (ranch.last_sale_date, ranch.last_sale_price) == (dt.date(2025, 6, 1), 150_000)
    assert ranch.price_per_sqft == pytest.approx(150_000 / 1008)
    assert (ranch.living_sqft, ranch.beds, ranch.baths, ranch.year_built) == (1008, 3, 1.0, 1955)
    assert ranch.value_change_pct == pytest.approx(18.699, abs=1e-3)
    assert ranch.market_value == 148_670


async def test_multi_parcel_deal_is_not_a_last_sale(loaded):
    await rebuild_derived(engine=loaded)
    rural = await summary(loaded, "A01 00101 0001")
    assert rural.last_sale_price is None
    assert rural.price_per_sqft is None


async def test_summary_sums_multiple_dwellings(loaded):
    await rebuild_derived(engine=loaded)
    two = await summary(loaded, "A01 00102 0069")
    assert (two.living_sqft, two.beds, two.baths) == (2490, 5, 2.5)
    assert two.year_built == 1985  # from the larger card


async def test_search_keys_owner_and_tax(loaded):
    await rebuild_derived(engine=loaded)
    rural = await summary(loaded, "A01 00101 0001")
    assert rural.address == "11974 FREDERICK PIKE"
    assert (rural.address_search, rural.street_search) == ("11974 FREDERICK PIKE", "FREDERICK PIKE")
    assert rural.parcel_id_search == "A01001010001"
    assert (rural.owner_name, rural.owner_search) == (
        "MULLENAX SAMANTHA MARIE", "MULLENAX SAMANTHA MARIE"
    )
    assert (rural.occupancy, rural.annual_tax) == ("owner_occupied", pytest.approx(6066.22))
    assert rural.year_built_is_placeholder is True
    assert rural.latitude == pytest.approx(39.92128, abs=1e-4)


async def test_inactive_parcel_without_cama_data_still_summarized(loaded):
    await rebuild_derived(engine=loaded)
    gone = await summary(loaded, "Z99 99999 9999")
    assert gone.is_active is False
    assert gone.last_sale_price == 50_000
    assert gone.living_sqft is None


async def test_neighborhood_summary(loaded):
    await rebuild_derived(engine=loaded)
    async with AsyncSession(loaded) as s:
        butler = await s.get(NeighborhoodSummary, "48150000")
    assert (butler.parcel_count, butler.residential_count) == (2, 2)
    assert butler.median_year_built == pytest.approx((1919 + 1985) / 2)


async def test_data_version_increments(loaded):
    async with loaded.connect() as conn:
        assert await current_data_version(conn) == 0
    assert await rebuild_derived(engine=loaded) == 1
    assert await rebuild_derived(engine=loaded) == 2
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/derived/test_summary.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'derived'`

- [ ] **Step 3: Implement `src/derived/summary.py`**

Create `src/derived/__init__.py` with `"""Tables and files rebuilt from ingested data."""` and `src/derived/summary.py`:

```python
"""parcel_summary, neighborhood_summary and data_version.

Everything is rebuilt from scratch in one transaction after each population
run, so readers always see one consistent version.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from county.text import normalize_search, street_key
from db.county_models import (
    DataVersion,
    Dwelling,
    NeighborhoodSummary,
    ParcelSummary,
    ParcelTax,
    ParcelValue,
)
from db.criteria import market_sale_criteria
from db.models import Parcel, Transaction
from ingest.bulk import insert_rows
from logging_config import get_logger

logger = get_logger(__name__)


def _last_market_sales():
    """Newest single-parcel market sale per parcel (parcel_id, sale_date, sale_price)."""
    t = Transaction.__table__
    deals = (
        sa.select(
            t.c.parcel_id, t.c.sale_date, t.c.sale_price, t.c.id,
            sa.func.count().over(
                partition_by=[t.c.sale_date, t.c.new_owner, t.c.sale_price]
            ).label("deal_size"),
        )
        .where(market_sale_criteria())
        .subquery()
    )
    ranked = (
        sa.select(
            deals.c.parcel_id, deals.c.sale_date, deals.c.sale_price,
            sa.func.row_number().over(
                partition_by=deals.c.parcel_id,
                order_by=[deals.c.sale_date.desc(), deals.c.id.desc()],
            ).label("rn"),
        )
        .where(deals.c.deal_size == 1)
        .subquery()
    )
    return sa.select(ranked.c.parcel_id, ranked.c.sale_date, ranked.c.sale_price).where(
        ranked.c.rn == 1
    ).subquery("last_sale")


def _dwelling_totals():
    d = Dwelling.__table__
    ranked = sa.select(
        d.c.parcel_id, d.c.living_sqft, d.c.beds, d.c.full_baths, d.c.half_baths,
        d.c.year_built, d.c.year_built_is_placeholder,
        sa.func.row_number().over(
            partition_by=d.c.parcel_id,
            order_by=[sa.func.coalesce(d.c.living_sqft, 0).desc(), d.c.card],
        ).label("rn"),
    ).subquery()
    primary = ranked.c.rn == 1
    return sa.select(
        ranked.c.parcel_id,
        sa.func.sum(ranked.c.living_sqft).label("living_sqft"),
        sa.func.sum(ranked.c.beds).label("beds"),
        (sa.func.sum(sa.func.coalesce(ranked.c.full_baths, 0))
         + 0.5 * sa.func.sum(sa.func.coalesce(ranked.c.half_baths, 0))).label("baths"),
        sa.func.max(sa.case((primary, ranked.c.year_built))).label("year_built"),
        sa.func.max(sa.case((primary, sa.cast(ranked.c.year_built_is_placeholder, sa.Integer))))
        .label("year_built_is_placeholder"),
    ).group_by(ranked.c.parcel_id).subquery("dw")


async def build_parcel_summary(conn: AsyncConnection) -> int:
    p, v, tx = Parcel.__table__, ParcelValue.__table__, ParcelTax.__table__
    last, dw = _last_market_sales(), _dwelling_totals()
    ppsf = sa.case(
        (sa.and_(dw.c.living_sqft > 0, last.c.sale_price > 0),
         last.c.sale_price * 1.0 / dw.c.living_sqft),
    )
    query = (
        sa.select(
            p.c.parcel_id, p.c.latitude, p.c.longitude, p.c.parcel_class, p.c.land_use_code,
            p.c.neighborhood, p.c.tax_district, p.c.is_active,
            p.c.parcel_location.label("address"),
            tx.c.owner_name, tx.c.occupancy, tx.c.out_of_state, tx.c.annual_bill,
            last.c.sale_date, last.c.sale_price, ppsf.label("ppsf"),
            dw.c.living_sqft, dw.c.beds, dw.c.baths, dw.c.year_built,
            dw.c.year_built_is_placeholder,
            v.c.total_2026, v.c.change_pct,
        )
        .select_from(p)
        .outerjoin(tx, tx.c.parcel_id == p.c.parcel_id)
        .outerjoin(last, last.c.parcel_id == p.c.parcel_id)
        .outerjoin(dw, dw.c.parcel_id == p.c.parcel_id)
        .outerjoin(v, v.c.parcel_id == p.c.parcel_id)
    )
    rows = (await conn.execute(query)).mappings().all()

    def summary_rows():
        for r in rows:
            address = r["address"] or ""
            latitude = r["latitude"] if r["latitude"] else None  # 0.0 = failed geocode
            yield {
                "parcel_id": r["parcel_id"],
                "parcel_id_search": r["parcel_id"].replace(" ", "").upper(),
                "latitude": latitude,
                "longitude": r["longitude"] if latitude is not None else None,
                "parcel_class": r["parcel_class"].name if hasattr(r["parcel_class"], "name")
                else r["parcel_class"],
                "land_use_code": r["land_use_code"],
                "neighborhood": r["neighborhood"],
                "tax_district": r["tax_district"],
                "is_active": bool(r["is_active"]),
                "address": address or None,
                "address_search": normalize_search(address) or None,
                "street_search": street_key(normalize_search(address)) or None,
                "owner_name": r["owner_name"],
                "owner_search": normalize_search(r["owner_name"]) or None,
                "last_sale_date": r["sale_date"],
                "last_sale_price": r["sale_price"],
                "price_per_sqft": r["ppsf"],
                "living_sqft": r["living_sqft"],
                "beds": r["beds"],
                "baths": float(r["baths"]) if r["living_sqft"] is not None else None,
                "year_built": r["year_built"],
                "year_built_is_placeholder": bool(r["year_built_is_placeholder"]),
                "market_value": r["total_2026"],
                "value_change_pct": r["change_pct"],
                "occupancy": r["occupancy"] or "unknown",
                "out_of_state_owner": bool(r["out_of_state"]),
                "annual_tax": r["annual_bill"],
            }

    await conn.execute(sa.delete(ParcelSummary.__table__))
    return await insert_rows(conn, ParcelSummary.__table__, summary_rows())


async def latest_sale_date(conn: AsyncConnection) -> date | None:
    t = Transaction.__table__
    return (await conn.execute(
        sa.select(sa.func.max(t.c.sale_date)).where(market_sale_criteria())
    )).scalar_one_or_none()


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


async def build_neighborhood_summary(conn: AsyncConnection, anchor: date | None) -> int:
    s = ParcelSummary.__table__
    rows = (await conn.execute(
        sa.select(
            s.c.neighborhood, s.c.parcel_class, s.c.last_sale_date, s.c.last_sale_price,
            s.c.price_per_sqft, s.c.occupancy, s.c.year_built, s.c.value_change_pct,
        ).where(s.c.is_active.is_(True), s.c.neighborhood.isnot(None))
    )).all()
    since = (anchor - timedelta(days=730)) if anchor else None
    groups: dict[str, list] = defaultdict(list)
    for row in rows:
        groups[row.neighborhood].append(row)

    def out():
        for code, members in groups.items():
            residential = [m for m in members if m.parcel_class == "R"]
            recent = [
                m for m in members
                if since and m.last_sale_date and m.last_sale_date >= since
                and m.last_sale_price
            ]
            known = [m for m in residential if m.occupancy != "unknown"]
            yield {
                "code": code,
                "parcel_count": len(members),
                "residential_count": len(residential),
                "sales_24m": len(recent),
                "median_sale_price_24m": _median([m.last_sale_price for m in recent]),
                "median_price_per_sqft_24m": _median(
                    [m.price_per_sqft for m in recent if m.price_per_sqft]
                ),
                "owner_occupied_share": (
                    sum(m.occupancy == "owner_occupied" for m in known) / len(known)
                    if known else None
                ),
                "median_year_built": _median([m.year_built for m in residential if m.year_built]),
                "median_value_change_pct": _median(
                    [m.value_change_pct for m in members if m.value_change_pct is not None]
                ),
            }

    await conn.execute(sa.delete(NeighborhoodSummary.__table__))
    return await insert_rows(conn, NeighborhoodSummary.__table__, out())


async def current_data_version(conn: AsyncConnection) -> int:
    t = DataVersion.__table__
    version = (await conn.execute(sa.select(t.c.version).where(t.c.id == 1))).scalar_one_or_none()
    return version or 0


async def bump_data_version(conn: AsyncConnection) -> int:
    t = DataVersion.__table__
    new = await current_data_version(conn) + 1
    await conn.execute(sa.delete(t))
    await conn.execute(sa.insert(t).values(id=1, version=new, updated_at=datetime.now()))
    return new


async def rebuild_derived(engine: AsyncEngine | None = None) -> int:
    if engine is None:
        from db.engine import engine as default_engine

        engine = default_engine
    async with engine.begin() as conn:
        parcels = await build_parcel_summary(conn)
        anchor = await latest_sale_date(conn)
        neighborhoods = await build_neighborhood_summary(conn, anchor)
        version = await bump_data_version(conn)
    logger.info("Derived data v%d: %d parcels, %d neighborhoods", version, parcels, neighborhoods)
    return version
```

`median_year_built` is declared `int` on the model; store it rounded: change the model field to `float | None` in `src/db/county_models.py` (`median_year_built: float | None = None`), since a median of two years can be fractional.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/derived -v`
Expected: all 7 tests PASS.

If `parcel_class` comes back from the join as a `ParcelClass` enum on one dialect and a string on the other, the `hasattr(..., "name")` branch in `summary_rows` already handles both.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/derived src/db/county_models.py tests/derived
git commit -m "Build parcel and neighborhood summaries with a data version"
```

---

### Task 13: Map binary

**Files:**
- Create: `src/derived/mapbinary.py`
- Modify: `src/derived/summary.py` (`rebuild_derived` writes the binary)
- Test: `tests/derived/test_mapbinary.py`

**Interfaces:**
- Consumes: `parcel_summary` (Task 12), `current_data_version`.
- Produces:
  - Format (little-endian): bytes `b"RPB1"`, `uint32` header length, UTF-8 JSON header padded with spaces to a multiple of 4, then column buffers, each starting at a multiple of 4. Header: `{"version": int, "rows": int, "columns": [{"name", "type", "offset", "byteLength", "labels"?}], "ids": {"offset", "byteLength"}}`. Offsets are from the start of the file. `type` is `"float32"`, `"uint16"` or `"uint8"`.
  - Columns, in order:

    | name | type | meaning; missing value |
    |---|---|---|
    | `lng`, `lat` | float32 | coordinates |
    | `last_sale_price`, `price_per_sqft`, `market_value`, `value_change_pct`, `annual_tax` | float32 | NaN when missing |
    | `last_sale_day` | uint16 | days since 1970-01-01; 0 when missing |
    | `living_sqft` | uint16 | clamped to 65535; 0 when missing |
    | `year_built` | uint16 | 0 when missing |
    | `beds` | uint8 | 255 when missing |
    | `baths_x2` | uint8 | baths times 2; 255 when missing |
    | `parcel_class` | uint8 | index into `labels` (`A C E I R U`) |
    | `occupancy` | uint8 | index into `labels` (`OCCUPANCY_CATEGORIES`) |
    | `neighborhood` | uint16 | index into `labels` (sorted codes); 65535 when missing |
    | `distress_score`, `permit_count_5y` | uint8 | clamped to 255 |
    | `flags` | uint8 | bit 0 placeholder year built, bit 1 out-of-state owner |

  - `ids`: parcel ids joined with `\n`, UTF-8, in row order.
  - Rows: active parcels with coordinates, ordered by `parcel_id`.
  - `encode_map_binary(rows: list[dict], version: int) -> bytes`; `decode_map_binary(data: bytes) -> dict` (used by tests and `scripts/verify_real_data.py`).
  - `async build_map_binary(conn, version: int) -> bytes`.
  - `map_binary_path(version: int) -> Path` under `DATA_DIR/derived/`; `write_map_binary(data: bytes, version: int) -> Path` writes atomically and deletes older versions; `latest_map_binary() -> tuple[int, Path] | None`.
  - `rebuild_derived` writes the file after its transaction commits.

- [ ] **Step 1: Write the failing tests**

Create `tests/derived/test_mapbinary.py`:

```python
import datetime as dt
import math
import struct

import pytest

import derived.mapbinary as mb

ROWS = [
    {
        "parcel_id": "A01 00101 0001", "longitude": -84.27433, "latitude": 39.92128,
        "last_sale_price": 320000.0, "price_per_sqft": 129.87, "market_value": 267560.0,
        "value_change_pct": -2.464, "annual_tax": 6066.22,
        "last_sale_date": dt.date(2023, 3, 20), "living_sqft": 2464, "year_built": 1919,
        "beds": 3, "baths": 1.0, "parcel_class": "R", "occupancy": "owner_occupied",
        "neighborhood": "48150000", "distress_score": 0, "permit_count_5y": 0,
        "year_built_is_placeholder": True, "out_of_state_owner": False,
    },
    {
        "parcel_id": "R72 00304 0025", "longitude": -84.19654, "latitude": 39.76272,
        "last_sale_price": None, "price_per_sqft": None, "market_value": None,
        "value_change_pct": None, "annual_tax": None, "last_sale_date": None,
        "living_sqft": 90000, "year_built": None, "beds": None, "baths": 2.5,
        "parcel_class": "C", "occupancy": "company", "neighborhood": None,
        "distress_score": 300, "permit_count_5y": 2,
        "year_built_is_placeholder": False, "out_of_state_owner": True,
    },
]


def test_round_trip():
    data = mb.encode_map_binary(ROWS, version=7)
    assert data[:4] == b"RPB1"
    decoded = mb.decode_map_binary(data)
    assert decoded["version"] == 7
    assert decoded["ids"] == ["A01 00101 0001", "R72 00304 0025"]
    cols = decoded["columns"]
    assert cols["lat"][0] == pytest.approx(39.92128, abs=1e-5)
    assert cols["lng"][1] == pytest.approx(-84.19654, abs=1e-5)
    assert cols["last_sale_price"][0] == 320000.0
    assert math.isnan(cols["last_sale_price"][1])
    assert cols["last_sale_day"][0] == (dt.date(2023, 3, 20) - dt.date(1970, 1, 1)).days
    assert cols["last_sale_day"][1] == 0
    assert cols["living_sqft"][1] == 65535  # clamped
    assert (cols["beds"][1], cols["baths_x2"][1]) == (255, 5)
    assert decoded["labels"]["parcel_class"][cols["parcel_class"][1]] == "C"
    assert decoded["labels"]["occupancy"][cols["occupancy"][0]] == "owner_occupied"
    assert decoded["labels"]["neighborhood"][cols["neighborhood"][0]] == "48150000"
    assert cols["neighborhood"][1] == 65535
    assert cols["distress_score"][1] == 255
    assert (cols["flags"][0], cols["flags"][1]) == (1, 2)


def test_buffers_are_four_byte_aligned():
    data = mb.encode_map_binary(ROWS, version=1)
    (header_len,) = struct.unpack_from("<I", data, 4)
    assert header_len % 4 == 0
    decoded = mb.decode_map_binary(data)
    assert all(c["offset"] % 4 == 0 for c in decoded["header"]["columns"])


def test_write_keeps_only_the_latest(tmp_path, monkeypatch):
    monkeypatch.setattr(mb, "DERIVED_DIR", tmp_path)
    mb.write_map_binary(b"one", 1)
    mb.write_map_binary(b"two", 2)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["parcels-v2.bin"]
    assert mb.latest_map_binary() == (2, tmp_path / "parcels-v2.bin")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/derived/test_mapbinary.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/derived/mapbinary.py`**

```python
"""Columnar binary of every mapped parcel, decoded by the frontend's Web Worker.

See the Task 13 table in docs/superpowers/plans/2026-09-24-phase-1a-data-platform-and-api.md
for the column list; the frontend decoder must match it.
"""
from __future__ import annotations

import json
import math
import os
import re
import struct
import sys
from array import array
from datetime import date
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from db.county_models import OCCUPANCY_CATEGORIES, ParcelSummary

MAGIC = b"RPB1"
EPOCH = date(1970, 1, 1)
CLASS_LABELS = ["A", "C", "E", "I", "R", "U"]
DERIVED_DIR = Path(os.getenv("DATA_DIR", "data")) / "derived"
_NAME = re.compile(r"parcels-v(\d+)\.bin$")
_TYPECODES = {"float32": "f", "uint16": "H", "uint8": "B"}

if sys.byteorder != "little":  # array() writes native byte order
    raise RuntimeError("map binary encoding assumes a little-endian host")

FLOAT_COLUMNS = ("last_sale_price", "price_per_sqft", "market_value", "value_change_pct",
                 "annual_tax")


def _pad4(data: bytes, fill: bytes = b"\0") -> bytes:
    return data + fill * (-len(data) % 4)


def _clamp(value, top: int, missing: int) -> int:
    if value is None:
        return missing
    return max(0, min(int(round(value)), top))


def encode_map_binary(rows: list[dict], version: int) -> bytes:
    neighborhoods = sorted({r["neighborhood"] for r in rows if r["neighborhood"]})
    nbhd_index = {code: i for i, code in enumerate(neighborhoods)}
    columns: list[tuple[str, str, array, list | None]] = [
        ("lng", "float32", array("f", (r["longitude"] for r in rows)), None),
        ("lat", "float32", array("f", (r["latitude"] for r in rows)), None),
    ]
    for name in FLOAT_COLUMNS:
        columns.append((name, "float32", array(
            "f", (math.nan if r[name] is None else r[name] for r in rows)), None))
    columns += [
        ("last_sale_day", "uint16", array("H", (
            (r["last_sale_date"] - EPOCH).days if r["last_sale_date"] else 0 for r in rows)), None),
        ("living_sqft", "uint16", array("H", (_clamp(r["living_sqft"], 65535, 0) for r in rows)),
         None),
        ("year_built", "uint16", array("H", (_clamp(r["year_built"], 65535, 0) for r in rows)),
         None),
        ("beds", "uint8", array("B", (_clamp(r["beds"], 254, 255) for r in rows)), None),
        ("baths_x2", "uint8", array("B", (
            _clamp(None if r["baths"] is None else r["baths"] * 2, 254, 255) for r in rows)), None),
        ("parcel_class", "uint8", array("B", (
            CLASS_LABELS.index(r["parcel_class"]) if r["parcel_class"] in CLASS_LABELS
            else CLASS_LABELS.index("R") for r in rows)), CLASS_LABELS),
        ("occupancy", "uint8", array("B", (
            OCCUPANCY_CATEGORIES.index(r["occupancy"]) for r in rows)), list(OCCUPANCY_CATEGORIES)),
        ("neighborhood", "uint16", array("H", (
            nbhd_index.get(r["neighborhood"], 65535) for r in rows)), neighborhoods),
        ("distress_score", "uint8", array("B", (
            _clamp(r["distress_score"], 255, 0) for r in rows)), None),
        ("permit_count_5y", "uint8", array("B", (
            _clamp(r["permit_count_5y"], 255, 0) for r in rows)), None),
        ("flags", "uint8", array("B", (
            (1 if r["year_built_is_placeholder"] else 0) | (2 if r["out_of_state_owner"] else 0)
            for r in rows)), None),
    ]
    ids = "\n".join(r["parcel_id"] for r in rows).encode()
    buffers = [_pad4(col[2].tobytes()) for col in columns] + [_pad4(ids)]

    def header_bytes(base: int) -> bytes:
        offset = base
        meta = []
        for (name, kind, values, labels), buf in zip(columns, buffers, strict=False):
            entry = {"name": name, "type": kind, "offset": offset,
                     "byteLength": len(values) * values.itemsize}
            if labels is not None:
                entry["labels"] = labels
            meta.append(entry)
            offset += len(buf)
        header = {"version": version, "rows": len(rows), "columns": meta,
                  "ids": {"offset": offset, "byteLength": len(ids)}}
        return _pad4(json.dumps(header, separators=(",", ":")).encode(), b" ")

    # The header's length depends on the offsets it contains; iterate until stable.
    header = header_bytes(8)
    while len(header_bytes(8 + len(header))) != len(header):
        header = header_bytes(8 + len(header))
    header = header_bytes(8 + len(header))
    return MAGIC + struct.pack("<I", len(header)) + header + b"".join(buffers)


def decode_map_binary(data: bytes) -> dict:
    if data[:4] != MAGIC:
        raise ValueError("not a parcel map binary")
    (header_len,) = struct.unpack_from("<I", data, 4)
    header = json.loads(data[8 : 8 + header_len])
    columns, labels = {}, {}
    for col in header["columns"]:
        values = array(_TYPECODES[col["type"]])
        values.frombytes(data[col["offset"] : col["offset"] + col["byteLength"]])
        columns[col["name"]] = values
        if "labels" in col:
            labels[col["name"]] = col["labels"]
    ids_meta = header["ids"]
    ids_raw = data[ids_meta["offset"] : ids_meta["offset"] + ids_meta["byteLength"]]
    return {"version": header["version"], "header": header, "columns": columns,
            "labels": labels, "ids": ids_raw.decode().split("\n") if ids_raw else []}


async def build_map_binary(conn: AsyncConnection, version: int) -> bytes:
    s = ParcelSummary.__table__
    result = await conn.execute(
        sa.select(s)
        .where(s.c.is_active.is_(True), s.c.latitude.isnot(None), s.c.longitude.isnot(None))
        .order_by(s.c.parcel_id)
    )
    rows = [dict(r) for r in result.mappings()]
    return encode_map_binary(rows, version)


def map_binary_path(version: int) -> Path:
    return DERIVED_DIR / f"parcels-v{version}.bin"


def write_map_binary(data: bytes, version: int) -> Path:
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    target = map_binary_path(version)
    partial = target.with_suffix(".part")
    partial.write_bytes(data)
    partial.replace(target)
    for old in DERIVED_DIR.glob("parcels-v*.bin"):
        if old != target:
            old.unlink(missing_ok=True)
    return target


def latest_map_binary() -> tuple[int, Path] | None:
    found = [
        (int(m.group(1)), p)
        for p in DERIVED_DIR.glob("parcels-v*.bin")
        if (m := _NAME.search(p.name))
    ]
    return max(found) if found else None
```

`write_map_binary` and `latest_map_binary` read the module-level `DERIVED_DIR` at call time, which is what lets the test monkeypatch it; keep `map_binary_path` reading it at call time too.

In `src/derived/summary.py`, extend `rebuild_derived` after the transaction:

```python
    from derived.mapbinary import build_map_binary, write_map_binary

    async with engine.connect() as conn:
        data = await build_map_binary(conn, version)
    path = write_map_binary(data, version)
    logger.info("Wrote map binary %s (%d KB)", path, len(data) // 1024)
    return version
```

In `tests/derived/test_summary.py`, add an autouse fixture so tests do not write into the repo's `data/`:

```python
@pytest.fixture(autouse=True)
def derived_dir(tmp_path, monkeypatch):
    import derived.mapbinary as mb

    monkeypatch.setattr(mb, "DERIVED_DIR", tmp_path / "derived")
```

and add this test:

```python
async def test_rebuild_writes_map_binary(loaded, tmp_path):
    import derived.mapbinary as mb

    version = await rebuild_derived(engine=loaded)
    latest_version, path = mb.latest_map_binary()
    decoded = mb.decode_map_binary(path.read_bytes())
    assert latest_version == version
    # Active parcels with coordinates only: the four CAMA parcels.
    assert decoded["ids"] == [
        "A01 00101 0001", "A01 00102 0069", "N64 00101 0003", "R72 00304 0025"
    ]
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/derived -v`
Expected: all tests PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/derived tests/derived
git commit -m "Encode every mapped parcel into a compact columnar binary"
```

---

### Task 14: Population pipeline wiring

**Files:**
- Create: `src/services/county_sync.py`
- Modify: `src/services/populate.py`
- Modify: `tests/test_populate.py`
- Test: `tests/test_county_sync.py`

**Interfaces:**
- Consumes: `sources` (Task 6), `ingest_cama` (Tasks 8-10), `ingest_taxroll` (Task 11), `ingest_neighborhood_names` (Task 10), `rebuild_derived` (Task 13), `DataFile` (existing).
- Produces:
  - `async sync_dataset(dataset: str, ingest, *, data_dir: Path, engine=None, client=None, min_age_days: int = 0) -> bool`: downloads and ingests the newest file for a dataset unless it was already ingested (by `DataFile.filename`) or, when `min_age_days > 0`, the last ingested file of that dataset is less than that many days older than the newest one. Records the file in `DataFile`, deletes older downloads of the dataset, returns `True` when it ingested something.
  - `populate_once` order: yearly sales, weekly sales, CAMA, neighborhood names, tax roll (weekly cadence: `min_age_days=7`), geocode, derived. The county steps run when `COUNTY_INGEST` is true (default true). Derived always runs last.
  - `COUNTY_DATA_DIR = DATA_DIR / "county"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_county_sync.py`:

```python
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

import services.county_sync as sync
from db.models import DataFile


def fake_sources(monkeypatch, files: list[str], downloaded: list[str]):
    async def list_files(dataset, client):
        return files

    async def download(dataset, filename, dest_dir, client):
        downloaded.append(filename)
        path = dest_dir / "Taxroll" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
        return path

    monkeypatch.setattr(sync.sources, "list_files", list_files)
    monkeypatch.setattr(sync.sources, "download", download)


async def test_ingests_new_file_once(db_engine, tmp_path, monkeypatch):
    downloaded, ingested = [], []
    fake_sources(monkeypatch, ["TAXROLL_20260922.zip", "TAXROLL_20260923.zip"], downloaded)

    async def ingest(path, engine):
        ingested.append(path.name)
        return 1

    kwargs = dict(data_dir=tmp_path, engine=db_engine, client=object())
    assert await sync.sync_dataset("taxroll", ingest, **kwargs) is True
    assert await sync.sync_dataset("taxroll", ingest, **kwargs) is False
    assert ingested == ["TAXROLL_20260923.zip"]
    async with AsyncSession(db_engine) as s:
        names = [f.filename for f in (await s.exec(select(DataFile))).all()]
    assert names == ["TAXROLL_20260923.zip"]


async def test_min_age_skips_files_newer_by_less_than_a_week(db_engine, tmp_path, monkeypatch):
    downloaded = []
    ingested = []

    async def ingest(path, engine):
        ingested.append(path.name)
        return 1

    kwargs = dict(data_dir=tmp_path, engine=db_engine, client=object(), min_age_days=7)
    fake_sources(monkeypatch, ["TAXROLL_20260916.zip"], downloaded)
    await sync.sync_dataset("taxroll", ingest, **kwargs)
    fake_sources(monkeypatch, ["TAXROLL_20260916.zip", "TAXROLL_20260920.zip"], downloaded)
    assert await sync.sync_dataset("taxroll", ingest, **kwargs) is False
    fake_sources(monkeypatch, ["TAXROLL_20260916.zip", "TAXROLL_20260923.zip"], downloaded)
    assert await sync.sync_dataset("taxroll", ingest, **kwargs) is True
    assert ingested == ["TAXROLL_20260916.zip", "TAXROLL_20260923.zip"]


async def test_older_downloads_are_deleted(db_engine, tmp_path, monkeypatch):
    old = tmp_path / "Taxroll" / "TAXROLL_20260901.zip"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old")
    fake_sources(monkeypatch, ["TAXROLL_20260923.zip"], [])

    async def ingest(path, engine):
        return 1

    await sync.sync_dataset("taxroll", ingest, data_dir=tmp_path, engine=db_engine,
                            client=object())
    assert [p.name for p in (tmp_path / "Taxroll").iterdir()] == ["TAXROLL_20260923.zip"]


async def test_failed_ingest_is_not_recorded(db_engine, tmp_path, monkeypatch):
    fake_sources(monkeypatch, ["TAXROLL_20260923.zip"], [])

    async def ingest(path, engine):
        raise RuntimeError("bad file")

    try:
        await sync.sync_dataset("taxroll", ingest, data_dir=tmp_path, engine=db_engine,
                                client=object())
    except RuntimeError:
        pass
    async with AsyncSession(db_engine) as s:
        assert (await s.exec(select(DataFile))).all() == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_county_sync.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.county_sync'`

- [ ] **Step 3: Implement `src/services/county_sync.py`**

```python
"""Download-and-ingest for the county's non-sales datasets.

A dataset's newest file is ingested once (tracked by DataFile.filename, since
these files never change once published). Older downloads are deleted to keep
the data volume small; CAMA alone is 125 MB a month.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Awaitable, Callable
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from county import sources
from db.models import DataFile
from logging_config import get_logger

logger = get_logger(__name__)

Ingest = Callable[[Path, AsyncEngine], Awaitable[object]]


def _file_date(dataset: str, filename: str) -> dt.date:
    match = sources.DATASETS[dataset].pattern.search(filename)
    return dt.datetime.strptime(match.group(1), "%Y%m%d").date()


async def _ingested_names(engine: AsyncEngine, dataset: str) -> list[str]:
    pattern = sources.DATASETS[dataset].pattern
    async with AsyncSession(engine) as s:
        names = (await s.exec(select(DataFile.filename))).all()
    return [n for n in names if pattern.fullmatch(n)]


async def sync_dataset(
    dataset: str,
    ingest: Ingest,
    *,
    data_dir: Path,
    engine: AsyncEngine | None = None,
    client=None,
    min_age_days: int = 0,
) -> bool:
    if engine is None:
        from db.engine import engine as default_engine

        engine = default_engine
    own_client = client is None
    client = client or sources.county_client()
    try:
        files = await sources.list_files(dataset, client)
        if not files:
            logger.warning("No %s files listed on the county site.", dataset)
            return False
        newest = files[-1]
        done = await _ingested_names(engine, dataset)
        if newest in done:
            return False
        if min_age_days and done:
            last = max(_file_date(dataset, n) for n in done)
            if (_file_date(dataset, newest) - last).days < min_age_days:
                return False
        path = await sources.download(dataset, newest, data_dir, client)
    finally:
        if own_client:
            await client.aclose()

    logger.info("Ingesting %s...", path.name)
    await ingest(path, engine)
    async with AsyncSession(engine) as s:
        s.add(DataFile(filename=newest, ingested_at=dt.datetime.now()))
        await s.commit()
    for old in path.parent.iterdir():
        if old != path and sources.DATASETS[dataset].pattern.fullmatch(old.name):
            old.unlink(missing_ok=True)
    return True
```

- [ ] **Step 4: Wire the steps into `src/services/populate.py`**

Add imports:

```python
from pathlib import Path

from derived.summary import rebuild_derived
from ingest.cama_ingest import ingest_cama
from ingest.neighborhood_ingest import ingest_neighborhood_names
from ingest.taxroll_ingest import ingest_taxroll
from services.county_sync import sync_dataset
```

Add below `_geocode`:

```python
COUNTY_DATA_DIR = Path(DATA_DIR) / "county"


async def _cama() -> None:
    await sync_dataset("cama", lambda path, engine: ingest_cama(path, engine=engine),
                       data_dir=COUNTY_DATA_DIR)


async def _neighborhood_names() -> None:
    await sync_dataset(
        "neighborhoods",
        lambda path, engine: ingest_neighborhood_names(path, engine=engine),
        data_dir=COUNTY_DATA_DIR,
    )


async def _taxroll() -> None:
    # Published daily; a weekly refresh is plenty for bills and occupancy.
    await sync_dataset("taxroll", lambda path, engine: ingest_taxroll(path, engine=engine),
                       data_dir=COUNTY_DATA_DIR, min_age_days=7)


async def _derived() -> None:
    await rebuild_derived()
```

Replace `populate_once` with:

```python
async def populate_once() -> None:
    """Run one full download -> ingest -> geocode -> derive pass."""
    logger.info("Population run starting (DATA_DIR=%s)...", DATA_DIR)
    await _run_step("yearly", _yearly)
    await _run_step("weekly", _weekly)
    if _env_flag("COUNTY_INGEST", True):
        await _run_step("cama", _cama)
        await _run_step("neighborhood_names", _neighborhood_names)
        await _run_step("taxroll", _taxroll)
    # After CAMA, so the Census geocoder only handles parcels the county lacks.
    if _env_flag("GEOCODE", True):
        await _run_step("geocode", _geocode)
    await _run_step("derived", _derived)
    logger.info("Population run complete.")
```

- [ ] **Step 5: Update the existing populate tests**

In `tests/test_populate.py`, extend the `steps` fixture so the county and derived steps are recorded instead of hitting the network:

```python
    async def cama():
        calls.append("cama")

    async def neighborhood_names():
        calls.append("neighborhood_names")

    async def taxroll():
        calls.append("taxroll")

    async def derived():
        calls.append("derived")

    monkeypatch.setattr(populate, "_cama", cama)
    monkeypatch.setattr(populate, "_neighborhood_names", neighborhood_names)
    monkeypatch.setattr(populate, "_taxroll", taxroll)
    monkeypatch.setattr(populate, "_derived", derived)
```

and update the expected call lists:

```python
async def test_all_steps_run(steps):
    await populate.populate_once()
    assert steps == ["retrieve_yearly", "ingest_yearly", "ingest_weekly", "cama",
                     "neighborhood_names", "taxroll", "geocode", "derived"]
```

In `test_yearly_failure_does_not_block_weekly_or_geocode` expect
`["ingest_weekly", "cama", "neighborhood_names", "taxroll", "geocode", "derived"]`, and in `test_weekly_failure_does_not_block_geocode` expect
`["retrieve_yearly", "ingest_yearly", "cama", "neighborhood_names", "taxroll", "geocode", "derived"]`. Add:

```python
async def test_county_steps_can_be_disabled(steps, monkeypatch):
    monkeypatch.setenv("COUNTY_INGEST", "false")
    await populate.populate_once()
    assert "cama" not in steps and "taxroll" not in steps
    assert steps[-1] == "derived"
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_county_sync.py tests/test_populate.py -v`
Expected: all tests PASS.

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff check src tests
git add src/services tests/test_county_sync.py tests/test_populate.py
git commit -m "Run CAMA, tax roll and neighborhood ingest plus the derived rebuild in the population loop"
```

---

### Task 15: /v2 skeleton: errors, filters, cache, meta and map endpoints

**Files:**
- Create: `src/api/__init__.py`, `src/api/errors.py`, `src/api/filters.py`, `src/api/cache.py`, `src/api/routers/__init__.py`, `src/api/routers/meta.py`, `src/api/routers/map.py`
- Create: `src/county/data/neighborhoods.geojson` (copied from `frontend/public/neighborhoods.geojson`)
- Modify: `src/main.py` (mount router, error handlers, gzip)
- Test: `tests/api/__init__.py`, `tests/api/conftest.py`, `tests/api/test_filters.py`, `tests/api/test_meta_and_map.py`

**Interfaces:**
- Produces:
  - `api.router`: `APIRouter(prefix="/v2")` that later tasks extend with `router.include_router(...)` in `src/api/__init__.py`.
  - `ApiError(status: int, code: str, message: str)`, `not_found(what: str) -> ApiError`, `register_error_handlers(app)`.
  - `Filters` (pydantic) with fields `date_from`, `date_to`, `price_min`, `price_max`, `classes`, `beds_min`, `sqft_min`, `sqft_max`, `year_built_min`, `year_built_max`, `occupancy`, `distress_min`, `neighborhood`; `Filters.active() -> list[str]`.
  - `get_filters(...) -> Filters` FastAPI dependency (raises `ApiError(422, "invalid_filters", ...)`).
  - `honored(filters: Filters, names: Iterable[str]) -> list[str]` (the active filters an endpoint actually applied, for `applied_filters`).
  - `SUMMARY_FILTERS` tuple, `summary_conditions(f, ps) -> list`, `sale_conditions(f, t, ps) -> list`, `parcel_conditions(f, ps) -> list`, `needs_summary(f) -> bool`.
  - `cache.cache: VersionedCache` with `get_or_compute(key: tuple, version: int, compute: Callable[[], Awaitable]) -> Any` and `clear()`; `async data_version(session) -> int`.
  - Endpoints: `GET /v2/meta` (`Meta` model), `GET /v2/map/parcels.bin`, `GET /v2/map/neighborhoods`.
  - Test fixtures in `tests/api/conftest.py`: `county_db` (fixtures loaded, sales seeded, derived rebuilt) and `api` (an `httpx.AsyncClient` against the app using `county_db`).

- [ ] **Step 1: Write the shared API test fixtures**

Create `tests/api/__init__.py` (empty) and `tests/api/conftest.py`:

```python
import datetime as dt
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from api.cache import cache
from db.engine import get_session
from db.models import Parcel, ParcelClass, Transaction
from derived.summary import rebuild_derived
from ingest.cama_ingest import ingest_cama
from ingest.taxroll_ingest import ingest_taxroll
from main import app

FIXTURES = Path(__file__).parent.parent / "fixtures" / "county"


def sale(parcel_id, day, price, buyer="BUYER A", seller="SELLER B", validity="VALID SALE",
         cls=ParcelClass.R):
    return Transaction(
        parcel_id=parcel_id, sale_date=day, sale_price=price, old_owner=seller, new_owner=buyer,
        parcel_location="X", mailing_name=buyer, mailing_address="X", parcel_class=cls,
        acres=0.1, taxable_land=0, taxable_building=0, taxable_total=0, sale_validity=validity,
    )


SALES = [
    ("N64 00101 0003", dt.date(2019, 5, 1), 90_000, "SMITH JOHN", "OLD OWNER"),
    ("N64 00101 0003", dt.date(2025, 6, 1), 150_000, "JONES MARY", "SMITH JOHN"),
    ("N64 00101 0003", dt.date(2025, 9, 1), 1, "JONES HEIR", "JONES MARY"),
    ("R72 00304 0025", dt.date(2024, 3, 15), 300_000, "BUYER R", "SELLER R"),
    ("R72 00304 0025", dt.date(2025, 8, 20), 330_000, "BUYER S", "BUYER R"),
    ("A01 00101 0001", dt.date(2023, 3, 20), 320_000, "MULLENAX SAMANTHA MARIE", "PRIOR OWNER"),
    ("A01 00101 0001", dt.date(2025, 7, 1), 900_000, "FUND LLC", "MULLENAX SAMANTHA MARIE"),
    ("A01 00102 0069", dt.date(2025, 7, 1), 900_000, "FUND LLC", "SELLER C"),
    ("Z99 99999 9999", dt.date(2010, 1, 1), 50_000, "GONE OWNER", "OLDER OWNER"),
]


@pytest.fixture
async def county_db(db_engine, tmp_path, monkeypatch):
    import derived.mapbinary as mb

    monkeypatch.setattr(mb, "DERIVED_DIR", tmp_path / "derived")
    cache.clear()
    async with AsyncSession(db_engine) as s:
        s.add(Parcel(parcel_id="Z99 99999 9999", parcel_location="1 GONE ST",
                     parcel_class=ParcelClass.R, acres=0.1))
        await s.commit()
    await ingest_cama(FIXTURES / "cama_fixture.zip", engine=db_engine)
    await ingest_taxroll(FIXTURES / "taxroll_fixture.zip", engine=db_engine)
    async with AsyncSession(db_engine) as s:
        s.add_all([sale(*row) for row in SALES])
        await s.commit()
    await rebuild_derived(engine=db_engine)
    return db_engine


@pytest.fixture
async def api(county_db):
    async def override():
        async with AsyncSession(county_db, expire_on_commit=False) as s:
            yield s

    app.dependency_overrides[get_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    cache.clear()
```

- [ ] **Step 2: Write the failing filter tests**

Create `tests/api/test_filters.py`:

```python
import datetime as dt

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from api.errors import register_error_handlers
from api.filters import Filters, get_filters, honored

echo = FastAPI()
register_error_handlers(echo)


@echo.get("/v2/echo")
async def echo_filters(f: Filters = Depends(get_filters)):
    return {"active": f.active(), "classes": f.classes}


async def call(query: str):
    async with AsyncClient(transport=ASGITransport(app=echo), base_url="http://t") as c:
        return await c.get(f"/v2/echo?{query}")


async def test_active_filters_and_lists():
    r = await call("price_min=100000&classes=R&classes=C&neighborhood=48150000")
    assert r.status_code == 200
    assert r.json() == {"active": ["price_min", "classes", "neighborhood"], "classes": ["R", "C"]}


async def test_no_filters():
    assert (await call("")).json()["active"] == []


async def test_contradictory_filters_return_422():
    r = await call("price_min=500000&price_max=100000")
    assert r.status_code == 422
    assert r.json() == {"error": {
        "code": "invalid_filters", "message": "price_min must not be greater than price_max"
    }}


async def test_future_year_built_is_rejected():
    r = await call(f"year_built_min={dt.date.today().year + 5}")
    assert r.status_code == 422
    assert "year_built_min cannot be after" in r.json()["error"]["message"]


async def test_bad_types_use_the_v2_error_shape():
    r = await call("price_min=lots")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"
    assert "price_min" in r.json()["error"]["message"]


async def test_unknown_class_is_rejected():
    r = await call("classes=Z")
    assert r.status_code == 422


def test_honored_intersects_active_filters():
    f = Filters(price_min=1, neighborhood="X")
    assert honored(f, ["price_min", "date_from"]) == ["price_min"]
```

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run pytest tests/api/test_filters.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api'`

- [ ] **Step 4: Implement errors, filters and cache**

Create `src/api/errors.py`:

```python
"""One error shape for /v2: {"error": {"code": str, "message": str}}."""
from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def not_found(what: str) -> ApiError:
    return ApiError(404, "not_found", f"{what} not found")


def _body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(_body(exc.code, exc.message), status_code=exc.status)


def _readable(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors():
        where = ".".join(str(p) for p in err["loc"] if p not in ("query", "path", "body"))
        parts.append(f"{where}: {err['msg']}" if where else err["msg"])
    return "; ".join(parts)


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    if request.url.path.startswith("/v2"):
        return JSONResponse(_body("invalid_request", _readable(exc)), status_code=422)
    return await request_validation_exception_handler(request, exc)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
```

Create `src/api/filters.py`:

```python
"""The one filter contract every /v2 list and aggregate endpoint accepts.

Each response reports ``applied_filters``: the active filters the endpoint
actually honored, so the UI can say "not filtered by price" instead of
silently ignoring a filter.
"""
from collections.abc import Iterable
from datetime import date
from typing import Annotated, Literal

import sqlalchemy as sa
from fastapi import Query
from pydantic import BaseModel, Field, ValidationError, model_validator

from api.errors import ApiError
from db.models import ParcelClass

ClassCode = Literal["A", "C", "E", "I", "R", "U"]
OccupancyCode = Literal[
    "owner_occupied", "company", "trust", "government", "absentee_individual", "unknown"
]
SUMMARY_FILTERS = (
    "beds_min", "sqft_min", "sqft_max", "year_built_min", "year_built_max", "occupancy",
    "distress_min", "neighborhood",
)
_RANGES = (
    ("date_from", "date_to"), ("price_min", "price_max"), ("sqft_min", "sqft_max"),
    ("year_built_min", "year_built_max"),
)


class Filters(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    price_min: float | None = Field(None, ge=0)
    price_max: float | None = Field(None, ge=0)
    classes: list[ClassCode] | None = None
    beds_min: int | None = Field(None, ge=0, le=20)
    sqft_min: int | None = Field(None, ge=0)
    sqft_max: int | None = Field(None, ge=0)
    year_built_min: int | None = Field(None, ge=1700)
    year_built_max: int | None = Field(None, ge=1700)
    occupancy: list[OccupancyCode] | None = None
    distress_min: int | None = Field(None, ge=0, le=100)
    neighborhood: str | None = None

    @model_validator(mode="after")
    def _check_ranges(self):
        for low, high in _RANGES:
            a, b = getattr(self, low), getattr(self, high)
            if a is not None and b is not None and a > b:
                raise ValueError(f"{low} must not be greater than {high}")
        latest = date.today().year + 1
        for name in ("year_built_min", "year_built_max"):
            value = getattr(self, name)
            if value is not None and value > latest:
                raise ValueError(f"{name} cannot be after {latest}")
        return self

    def active(self) -> list[str]:
        return [name for name, value in self if value not in (None, [])]


def get_filters(
    date_from: date | None = None,
    date_to: date | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    classes: Annotated[list[str] | None, Query()] = None,
    beds_min: int | None = None,
    sqft_min: int | None = None,
    sqft_max: int | None = None,
    year_built_min: int | None = None,
    year_built_max: int | None = None,
    occupancy: Annotated[list[str] | None, Query()] = None,
    distress_min: int | None = None,
    neighborhood: str | None = None,
) -> Filters:
    try:
        return Filters(
            date_from=date_from, date_to=date_to, price_min=price_min, price_max=price_max,
            classes=classes, beds_min=beds_min, sqft_min=sqft_min, sqft_max=sqft_max,
            year_built_min=year_built_min, year_built_max=year_built_max,
            occupancy=occupancy, distress_min=distress_min, neighborhood=neighborhood,
        )
    except ValidationError as exc:
        message = "; ".join(
            e["msg"].removeprefix("Value error, ")
            if not e["loc"] else f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
            for e in exc.errors()
        )
        raise ApiError(422, "invalid_filters", message) from None


def honored(filters: Filters, names: Iterable[str]) -> list[str]:
    allowed = set(names)
    return [name for name in filters.active() if name in allowed]


def needs_summary(f: Filters) -> bool:
    return any(getattr(f, name) not in (None, []) for name in SUMMARY_FILTERS)


def summary_conditions(f: Filters, ps: sa.Table) -> list:
    c = []
    if f.beds_min is not None:
        c.append(ps.c.beds >= f.beds_min)
    if f.sqft_min is not None:
        c.append(ps.c.living_sqft >= f.sqft_min)
    if f.sqft_max is not None:
        c.append(ps.c.living_sqft <= f.sqft_max)
    if f.year_built_min is not None:
        c.append(ps.c.year_built >= f.year_built_min)
    if f.year_built_max is not None:
        c.append(ps.c.year_built <= f.year_built_max)
    if f.occupancy:
        c.append(ps.c.occupancy.in_(f.occupancy))
    if f.distress_min is not None:
        c.append(ps.c.distress_score >= f.distress_min)
    if f.neighborhood:
        c.append(ps.c.neighborhood == f.neighborhood)
    return c


def sale_conditions(f: Filters, t: sa.Table, ps: sa.Table) -> list:
    """Filters on a transaction row; summary filters need ps joined to t."""
    c = []
    if f.date_from:
        c.append(t.c.sale_date >= f.date_from)
    if f.date_to:
        c.append(t.c.sale_date <= f.date_to)
    if f.price_min is not None:
        c.append(t.c.sale_price >= f.price_min)
    if f.price_max is not None:
        c.append(t.c.sale_price <= f.price_max)
    if f.classes:
        c.append(t.c.parcel_class.in_([ParcelClass[code] for code in f.classes]))
    return c + summary_conditions(f, ps)


def parcel_conditions(f: Filters, ps: sa.Table) -> list:
    """Filters on a parcel_summary row: dates and prices refer to its last sale."""
    c = []
    if f.date_from:
        c.append(ps.c.last_sale_date >= f.date_from)
    if f.date_to:
        c.append(ps.c.last_sale_date <= f.date_to)
    if f.price_min is not None:
        c.append(ps.c.last_sale_price >= f.price_min)
    if f.price_max is not None:
        c.append(ps.c.last_sale_price <= f.price_max)
    if f.classes:
        c.append(ps.c.parcel_class.in_(f.classes))
    return c + summary_conditions(f, ps)
```

Create `src/api/cache.py`:

```python
"""In-process cache for aggregate responses, keyed by data_version.

A new ingest bumps data_version, so stale entries are never served; they
simply age out of the LRU.
"""
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

import sqlalchemy as sa

from db.county_models import DataVersion


class VersionedCache:
    def __init__(self, maxsize: int = 1024):
        self.maxsize = maxsize
        self._data: OrderedDict[tuple, Any] = OrderedDict()

    async def get_or_compute(
        self, key: tuple, version: int, compute: Callable[[], Awaitable[Any]]
    ) -> Any:
        full_key = (version, *key)
        if full_key in self._data:
            self._data.move_to_end(full_key)
            return self._data[full_key]
        value = await compute()
        self._data[full_key] = value
        while len(self._data) > self.maxsize:
            self._data.popitem(last=False)
        return value

    def clear(self) -> None:
        self._data.clear()


cache = VersionedCache()


async def data_version(session) -> int:
    t = DataVersion.__table__
    result = await session.execute(sa.select(t.c.version).where(t.c.id == 1))
    return result.scalar_one_or_none() or 0
```

- [ ] **Step 5: Run the filter tests**

Run: `uv run pytest tests/api/test_filters.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 6: Write the failing meta and map tests**

Create `tests/api/test_meta_and_map.py`:

```python
import datetime as dt

import derived.mapbinary as mb


async def test_meta(api):
    r = await api.get("/v2/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["data_version"] == 1
    assert body["latest_sale_date"] == "2025-08-20"
    assert body["parcel_count"] == 5
    assert body["mapped_parcel_count"] == 4
    sales = next(s for s in body["sources"] if s["name"] == "sales")
    assert sales["as_of"] == "2025-08-20"
    assert sales["stale"] is True  # older than 14 days
    assert {"price", "living_sqft", "year_built"} <= set(body["ranges"])


async def test_map_binary_with_etag(api):
    r = await api.get("/v2/map/parcels.bin")
    assert r.status_code == 200
    assert r.headers["etag"] == '"v1"'
    decoded = mb.decode_map_binary(r.content)
    assert len(decoded["ids"]) == 4
    again = await api.get("/v2/map/parcels.bin", headers={"If-None-Match": '"v1"'})
    assert again.status_code == 304


async def test_map_binary_not_ready(api, tmp_path, monkeypatch):
    monkeypatch.setattr(mb, "DERIVED_DIR", tmp_path / "empty")
    r = await api.get("/v2/map/parcels.bin")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "map_not_ready"


async def test_neighborhood_geojson_has_stats(api):
    r = await api.get("/v2/map/neighborhoods")
    assert r.status_code == 200
    features = {f["properties"]["code"]: f for f in r.json()["features"]}
    butler = features["48150000"]["properties"]
    assert butler["name"] == "N BUTLER TWP"
    assert butler["parcel_count"] == 2
    assert features["48150000"]["geometry"]["type"] in ("Polygon", "MultiPolygon")


def test_today_is_after_fixture_data():
    # The staleness assertion above assumes the fixtures are in the past.
    assert dt.date.today() > dt.date(2025, 9, 3)
```

- [ ] **Step 7: Run them to verify they fail**

Run: `uv run pytest tests/api/test_meta_and_map.py -v`
Expected: FAIL with 404 responses (routes do not exist yet).

- [ ] **Step 8: Implement the routers and mount them**

Copy the boundaries so the backend can serve them (the old frontend keeps its copy until plan 1B):

```bash
cp frontend/public/neighborhoods.geojson src/county/data/neighborhoods.geojson
```

Create `src/api/routers/__init__.py` (empty) and `src/api/routers/meta.py`:

```python
import datetime as dt
import re

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from api.cache import cache, data_version
from db.county_models import DataVersion, ParcelSummary
from db.engine import get_session
from db.models import DataFile
from derived.summary import latest_sale_date

router = APIRouter(tags=["meta"])

# name, label, DataFile pattern, days until stale (None = never flagged)
_SOURCES = (
    ("cama", "County appraisal (CAMA)", re.compile(r"Cama_Files_(\d{8})\.zip"), 45),
    ("taxroll", "Tax roll", re.compile(r"TAXROLL_(\d{8})\.zip"), 21),
    ("neighborhoods", "Neighborhood names", re.compile(r"neighborhood_codes_(\d{8})\.htm"), None),
)
SALES_STALE_DAYS = 14


class SourceStatus(BaseModel):
    name: str
    label: str
    file: str | None
    ingested_at: dt.datetime | None
    as_of: dt.date | None
    stale: bool


class Meta(BaseModel):
    data_version: int
    updated_at: dt.datetime | None
    latest_sale_date: dt.date | None
    parcel_count: int
    mapped_parcel_count: int
    sources: list[SourceStatus]
    ranges: dict[str, list[float]]


def _percentile(sorted_values: list[float], p: float) -> float:
    return sorted_values[min(len(sorted_values) - 1, int(len(sorted_values) * p))]


async def _ranges(session: AsyncSession) -> dict[str, list[float]]:
    s = ParcelSummary.__table__
    out = {}
    for name, column in (("price", s.c.last_sale_price), ("living_sqft", s.c.living_sqft),
                         ("year_built", s.c.year_built)):
        values = sorted(
            v for (v,) in (await session.execute(
                sa.select(column).where(column.isnot(None), column > 0)
            )).all()
        )
        out[name] = [_percentile(values, 0.01), _percentile(values, 0.99)] if values else [0, 0]
    return out


@router.get("/meta", response_model=Meta)
async def meta(session: AsyncSession = Depends(get_session)) -> Meta:
    version = await data_version(session)
    today = dt.date.today()
    conn = await session.connection()
    latest = await latest_sale_date(conn)
    s = ParcelSummary.__table__
    parcel_count = (await session.execute(sa.select(sa.func.count()).select_from(s))).scalar_one()
    mapped = (await session.execute(
        sa.select(sa.func.count()).select_from(s)
        .where(s.c.is_active.is_(True), s.c.latitude.isnot(None))
    )).scalar_one()
    files = (await session.execute(sa.select(DataFile.filename, DataFile.ingested_at))).all()
    sources = [SourceStatus(
        name="sales", label="Sales", file=None, ingested_at=None, as_of=latest,
        stale=latest is None or (today - latest).days > SALES_STALE_DAYS,
    )]
    for name, label, pattern, stale_days in _SOURCES:
        matches = sorted(
            ((m.group(1), f, at) for f, at in files if (m := pattern.fullmatch(f))),
        )
        if matches:
            stamp, file, at = matches[-1]
            as_of = dt.datetime.strptime(stamp, "%Y%m%d").date()
        else:
            file, at, as_of = None, None, None
        stale = stale_days is not None and (as_of is None or (today - as_of).days > stale_days)
        sources.append(SourceStatus(name=name, label=label, file=file, ingested_at=at,
                                    as_of=as_of, stale=stale))
    updated = (await session.execute(
        sa.select(DataVersion.updated_at).where(DataVersion.id == 1)
    )).scalar_one_or_none()
    ranges = await cache.get_or_compute(("ranges",), version, lambda: _ranges(session))
    return Meta(data_version=version, updated_at=updated, latest_sale_date=latest,
                parcel_count=parcel_count, mapped_parcel_count=mapped, sources=sources,
                ranges=ranges)
```

Create `src/api/routers/map.py`:

```python
import json
from functools import lru_cache
from pathlib import Path

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, Response
from sqlmodel.ext.asyncio.session import AsyncSession

from api.cache import cache, data_version
from api.errors import ApiError
from db.county_models import Neighborhood, NeighborhoodSummary
from db.engine import get_session
from derived import mapbinary

router = APIRouter(prefix="/map", tags=["map"])
_GEOJSON = Path(__file__).parent.parent.parent / "county" / "data" / "neighborhoods.geojson"
_STATS = ("parcel_count", "residential_count", "sales_24m", "median_sale_price_24m",
          "median_price_per_sqft_24m", "owner_occupied_share", "median_year_built",
          "median_value_change_pct")


@router.get("/parcels.bin", response_class=FileResponse)
async def parcels_bin(request: Request):
    found = mapbinary.latest_map_binary()
    if not found:
        raise ApiError(503, "map_not_ready", "The parcel map is still being built")
    version, path = found
    etag = f'"v{version}"'
    headers = {"ETag": etag, "Cache-Control": "public, max-age=0, must-revalidate"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return FileResponse(path, media_type="application/octet-stream", headers=headers)


@lru_cache(maxsize=1)
def _boundaries() -> dict:
    return json.loads(_GEOJSON.read_text())


async def _neighborhood_features(session: AsyncSession) -> dict:
    n, ns = Neighborhood.__table__, NeighborhoodSummary.__table__
    rows = (await session.execute(
        sa.select(n, *[ns.c[c] for c in _STATS]).select_from(n)
        .outerjoin(ns, ns.c.code == n.c.code)
    )).mappings().all()
    by_code = {r["code"]: dict(r) for r in rows}
    features = []
    for feature in _boundaries()["features"]:
        code = feature["properties"].get("code")
        props = {"code": code, **(by_code.get(code) or {"name": feature["properties"].get("name")})}
        features.append({"type": "Feature", "geometry": feature["geometry"], "properties": props})
    return {"type": "FeatureCollection", "features": features}


@router.get("/neighborhoods")
async def neighborhoods(session: AsyncSession = Depends(get_session)) -> dict:
    version = await data_version(session)
    return await cache.get_or_compute(
        ("neighborhood-geojson",), version, lambda: _neighborhood_features(session)
    )
```

Create `src/api/__init__.py`:

```python
"""The /v2 API used by the redesigned frontend."""
from fastapi import APIRouter

from api.routers import map as map_router
from api.routers import meta

router = APIRouter(prefix="/v2")
router.include_router(meta.router)
router.include_router(map_router.router)
```

In `src/main.py`, after `app = FastAPI(...)` and the CORS middleware:

```python
from fastapi.middleware.gzip import GZipMiddleware

from api import router as v2_router
from api.errors import register_error_handlers

app.add_middleware(GZipMiddleware, minimum_size=1024)
register_error_handlers(app)
app.include_router(v2_router)
```

(Move the imports to the top of the file with the others so ruff's import sorting passes.)

- [ ] **Step 9: Run the API tests and the whole suite**

Run: `uv run pytest -q`
Expected: all tests PASS, including the existing `/analytics` tests (the validation handler keeps FastAPI's default shape outside `/v2`).

- [ ] **Step 10: Lint and commit**

```bash
uv run ruff check src tests
git add src/api src/main.py src/county/data/neighborhoods.geojson tests/api
git commit -m "Add the /v2 API skeleton: error shape, shared filters, cache, meta and map endpoints"
```

---

### Task 16: Search

**Files:**
- Create: `src/services/analytics/__init__.py`, `src/services/analytics/search.py`, `src/api/routers/search.py`
- Modify: `src/api/__init__.py`
- Test: `tests/api/test_search.py`

**Interfaces:**
- Consumes: `normalize_search`, `parcel_id_key`, `prefix_upper_bound` (Task 5); `parcel_summary`, `neighborhood`, `transaction`.
- Produces: `GET /v2/search?q=&limit=8` returning `SearchResults`:

  ```
  {query: str,
   addresses: [{parcel_id, address, neighborhood, neighborhood_name, last_sale_price}],
   parcels:   [{parcel_id, address}],
   owners:    [{name, parcel_count}],   # parcel_count 0 = past buyer, owns nothing now
   neighborhoods: [{code, name, display_name}]}
  ```

  Queries shorter than 2 normalized characters return empty groups. `services.analytics.search.search(session, q: str, limit: int) -> SearchResults`.

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_search.py`:

```python
async def search(api, q):
    r = await api.get("/v2/search", params={"q": q})
    assert r.status_code == 200
    return r.json()


async def test_address_prefix(api):
    body = await search(api, "11974 frederick")
    assert [a["parcel_id"] for a in body["addresses"]] == ["A01 00101 0001"]
    assert body["addresses"][0]["neighborhood_name"] == "N BUTLER TWP"


async def test_street_without_house_number(api):
    body = await search(api, "aragon")
    assert [a["address"] for a in body["addresses"]] == ["2301 S ARAGON AVE"]


async def test_parcel_id_with_or_without_spaces(api):
    for q in ("r72 00304", "R7200304"):
        body = await search(api, q)
        assert [p["parcel_id"] for p in body["parcels"]] == ["R72 00304 0025"]


async def test_current_and_past_owners(api):
    body = await search(api, "mullenax")
    assert body["owners"] == [{"name": "MULLENAX SAMANTHA MARIE", "parcel_count": 1}]
    past = await search(api, "fund")
    assert {"name": "FUND LLC", "parcel_count": 0} in past["owners"]


async def test_neighborhoods(api):
    body = await search(api, "butler")
    assert {"code": "48150000", "name": "N BUTLER TWP", "display_name": "N BUTLER TWP"} in (
        body["neighborhoods"]
    )


async def test_search_normalizes_messy_input(api):
    body = await search(api, "  11974   FREDERICK-pike. ")
    assert [a["parcel_id"] for a in body["addresses"]] == ["A01 00101 0001"]
    body = await search(api, "o'neil")
    assert body["owners"] == [] and body["addresses"] == []
    body = await search(api, "%_\\")
    assert body == {"query": "", "addresses": [], "parcels": [], "owners": [],
                    "neighborhoods": []}


async def test_too_short(api):
    body = await search(api, "a")
    assert body["addresses"] == [] and body["owners"] == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/api/test_search.py -v`
Expected: FAIL (404 from the missing route).

- [ ] **Step 3: Implement search**

Create `src/services/analytics/__init__.py` with `"""Query logic shared by the old /analytics routes and the /v2 API."""` and `src/services/analytics/search.py`:

```python
"""Grouped prefix search over addresses, parcel ids, owners and neighborhoods.

Prefix matching uses [prefix, upper bound) ranges on normalized, indexed
columns so a plain btree index serves it on SQLite and Postgres alike.
"""
import sqlalchemy as sa
from pydantic import BaseModel

from county.text import normalize_search, parcel_id_key, prefix_upper_bound, street_key
from db.county_models import Neighborhood, ParcelSummary
from db.models import Transaction


class AddressHit(BaseModel):
    parcel_id: str
    address: str | None
    neighborhood: str | None
    neighborhood_name: str | None
    last_sale_price: float | None


class ParcelHit(BaseModel):
    parcel_id: str
    address: str | None


class OwnerHit(BaseModel):
    name: str
    parcel_count: int


class NeighborhoodHit(BaseModel):
    code: str
    name: str
    display_name: str


class SearchResults(BaseModel):
    query: str
    addresses: list[AddressHit] = []
    parcels: list[ParcelHit] = []
    owners: list[OwnerHit] = []
    neighborhoods: list[NeighborhoodHit] = []


def _in_prefix(column, prefix: str):
    return sa.and_(column >= prefix, column < prefix_upper_bound(prefix))


async def search(session, q: str, limit: int = 8) -> SearchResults:
    query = normalize_search(q)
    results = SearchResults(query=query)
    if len(query) < 2:
        return results
    ps, n, t = ParcelSummary.__table__, Neighborhood.__table__, Transaction.__table__

    address_rows = (await session.execute(
        sa.select(ps.c.parcel_id, ps.c.address, ps.c.neighborhood, ps.c.last_sale_price,
                  n.c.name.label("neighborhood_name"))
        .select_from(ps).outerjoin(n, n.c.code == ps.c.neighborhood)
        .where(sa.or_(_in_prefix(ps.c.address_search, query),
                      _in_prefix(ps.c.street_search, street_key(query))))
        .order_by(ps.c.is_active.desc(), ps.c.address_search)
        .limit(limit)
    )).mappings().all()
    results.addresses = [AddressHit(**r) for r in address_rows]

    key = parcel_id_key(query)
    parcel_rows = (await session.execute(
        sa.select(ps.c.parcel_id, ps.c.address)
        .where(_in_prefix(ps.c.parcel_id_search, key))
        .order_by(ps.c.parcel_id_search).limit(limit)
    )).mappings().all()
    results.parcels = [ParcelHit(**r) for r in parcel_rows]

    current = (await session.execute(
        sa.select(ps.c.owner_name, sa.func.count().label("n"))
        .where(_in_prefix(ps.c.owner_search, query), ps.c.owner_name.isnot(None))
        .group_by(ps.c.owner_name).order_by(sa.func.count().desc(), ps.c.owner_name)
        .limit(limit)
    )).all()
    owners = [OwnerHit(name=name, parcel_count=count) for name, count in current]
    if len(owners) < limit:
        known = {o.name for o in owners}
        past = (await session.execute(
            sa.select(t.c.new_owner).where(_in_prefix(t.c.new_owner, query))
            .distinct().order_by(t.c.new_owner).limit(limit)
        )).scalars().all()
        owners += [OwnerHit(name=name, parcel_count=0) for name in past if name not in known]
    results.owners = owners[:limit]

    hood_rows = (await session.execute(
        sa.select(n.c.code, n.c.name, n.c.display_name)
        .where(sa.func.upper(n.c.name).contains(query, autoescape=True))
        .order_by(n.c.display_name).limit(limit)
    )).mappings().all()
    results.neighborhoods = [NeighborhoodHit(**r) for r in hood_rows]
    return results
```

Create `src/api/routers/search.py`:

```python
from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from db.engine import get_session
from services.analytics.search import SearchResults, search

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResults)
async def search_everything(
    q: str = Query("", max_length=200),
    limit: int = Query(8, ge=1, le=25),
    session: AsyncSession = Depends(get_session),
) -> SearchResults:
    return await search(session, q, limit)
```

Register it in `src/api/__init__.py`: `from api.routers import search` and `router.include_router(search.router)`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/api/test_search.py -v`
Expected: all 7 tests PASS. `"%_\\"` normalizes to an empty query, so it can never reach SQL as a wildcard.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/services/analytics src/api tests/api/test_search.py
git commit -m "Add grouped prefix search for addresses, parcel ids, owners and neighborhoods"
```

---

### Task 17: Property profile and timeline

**Files:**
- Create: `src/services/analytics/parcels.py`, `src/api/routers/parcels.py`
- Modify: `src/api/__init__.py`
- Test: `tests/api/test_parcels.py`

**Interfaces:**
- Consumes: every table from Tasks 7-12; `market_sale_criteria`; `cache`, `data_version`, `not_found` (Task 15).
- Produces:
  - `GET /v2/parcels/{parcel_id}` returning `ParcelProfile` (fields below); 404 `not_found` for unknown ids.
  - `GET /v2/parcels/{parcel_id}/timeline` returning `list[TimelineEvent]`, newest first.
  - Badge codes: `owner_occupied`, `company_owned`, `trust_owned`, `government_owned`, `absentee_owner`, `out_of_state_owner`, `tax_delinquent`, `foreclosure_filed`, `tif`, `retired_parcel`.
  - Timeline kinds: `sale` (title `"Sold"` for market sales, `"Transferred"` otherwise), `built`, `reappraisal`.

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_parcels.py`:

```python
import pytest


async def test_full_profile(api):
    r = await api.get("/v2/parcels/A01 00101 0001")
    assert r.status_code == 200
    p = r.json()
    assert (p["address"], p["is_active"], p["parcel_class"]) == ("11974 FREDERICK PIKE", True, "R")
    assert p["neighborhood"] == {"code": "48150000", "name": "N BUTLER TWP",
                                 "display_name": "N BUTLER TWP"}
    assert p["tax_district"]["code"] == "A01"
    facts = p["facts"]
    assert (facts["living_sqft"], facts["beds"], facts["baths"]) == (2464, 3, 1.0)
    assert (facts["style"], facts["year_built"], facts["year_built_is_placeholder"]) == (
        "OLD STYLE", 1919, True
    )
    assert (facts["detached_garage_sqft"], facts["basement_garage_cars"]) == (768, 1)
    assert p["lot"]["lot_acres"] == pytest.approx(2.0)
    assert p["dwellings"][0]["sketch"][0]["vector"] == "A0CU20R45D20L45"
    assert {f["code"] for f in p["features"]} == {"RG1", "AL1"}
    value = p["value"]
    assert (value["market_value_2025"], value["market_value_2026"]) == (274320, 267560)
    # The 2025 two-parcel deal is not a per-parcel price, so the 2023 sale is the last sale.
    assert (value["last_sale_date"], value["last_sale_price"]) == ("2023-03-20", 320_000)
    tax = p["tax"]
    assert tax["annual_bill"] == pytest.approx(6066.22)
    assert tax["effective_rate_pct"] == pytest.approx(6066.22 / 274320 * 100, abs=1e-3)
    assert p["owner"]["name"] == "MULLENAX SAMANTHA MARIE"
    assert p["owner"]["occupancy"] == "owner_occupied"
    assert "owner_occupied" in p["badges"]


async def test_price_per_sqft_vs_neighborhood(api):
    p = (await api.get("/v2/parcels/N64 00101 0003")).json()
    assert p["value"]["last_sale_price"] == 150_000
    assert p["value"]["price_per_sqft"] == pytest.approx(150_000 / 1008)
    assert p["value"]["ratio_to_last_sale"] == pytest.approx(148_670 / 150_000)


async def test_profile_of_inactive_parcel_without_cama_data(api):
    r = await api.get("/v2/parcels/Z99 99999 9999")
    assert r.status_code == 200
    p = r.json()
    assert p["is_active"] is False
    assert p["facts"] is None and p["dwellings"] == [] and p["tax"] is None
    assert "retired_parcel" in p["badges"]
    assert p["value"]["last_sale_price"] == 50_000


async def test_unknown_parcel_is_404(api):
    r = await api.get("/v2/parcels/NOPE")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "not_found", "message": "Parcel NOPE not found"}}


async def test_timeline(api):
    events = (await api.get("/v2/parcels/N64 00101 0003/timeline")).json()
    kinds = [(e["date"], e["kind"], e["title"]) for e in events]
    assert kinds == [
        ("2026-01-01", "reappraisal", "2026 reappraisal"),
        ("2025-09-01", "sale", "Transferred"),
        ("2025-06-01", "sale", "Sold"),
        ("2019-05-01", "sale", "Sold"),
        ("1955-01-01", "built", "Built"),
    ]
    sold = events[2]
    assert (sold["amount"], sold["detail"]["buyer"], sold["detail"]["is_market_sale"]) == (
        150_000, "JONES MARY", True
    )
    assert events[0]["detail"]["change_pct"] == pytest.approx(18.699, abs=1e-3)


async def test_placeholder_year_is_labeled(api):
    events = (await api.get("/v2/parcels/A01 00101 0001/timeline")).json()
    built = next(e for e in events if e["kind"] == "built")
    assert built["title"] == "Built before 1920"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/api/test_parcels.py -v`
Expected: FAIL (404 from the missing routes).

- [ ] **Step 3: Implement `src/services/analytics/parcels.py`**

```python
"""Property profile and timeline for one parcel."""
from __future__ import annotations

import datetime as dt
import json
import statistics
from datetime import date
from typing import Literal

import sqlalchemy as sa
from pydantic import BaseModel

from api.cache import cache, data_version
from api.errors import not_found
from db.county_models import (
    Dwelling,
    Neighborhood,
    NeighborhoodSummary,
    ParcelDetail,
    ParcelFeature,
    ParcelSummary,
    ParcelTax,
    ParcelValue,
    TaxDistrict,
)
from db.criteria import market_sale_criteria
from db.models import Parcel, Transaction

REAPPRAISAL_DATE = date(2026, 1, 1)


class NeighborhoodRef(BaseModel):
    code: str
    name: str | None = None
    display_name: str | None = None


class DistrictRef(BaseModel):
    code: str
    name: str | None = None
    school_district: str | None = None


class Facts(BaseModel):
    living_sqft: int | None
    beds: int | None
    baths: float | None
    full_baths: int | None
    half_baths: int | None
    stories: float | None
    style: str | None
    year_built: int | None
    year_built_is_placeholder: bool
    grade: str | None
    grade_label: str | None
    condition: str | None
    exterior: str | None
    basement: str | None
    finished_basement_sqft: int | None
    heating: str | None
    fuel: str | None
    has_central_air: bool
    fireplaces: int
    attached_garage_sqft: int
    detached_garage_sqft: int
    basement_garage_cars: int
    has_pool: bool


class Lot(BaseModel):
    land_use: str | None
    living_units: int | None
    lot_sqft: int | None
    lot_acres: float | None
    frontage_ft: float | None
    depth_ft: float | None


class SketchLine(BaseModel):
    line: int
    codes: list[str]
    area: int | None
    vector: str | None


class DwellingOut(BaseModel):
    card: int
    living_sqft: int | None
    year_built: int | None
    style: str | None
    sketch: list[SketchLine]


class FeatureOut(BaseModel):
    code: str
    description: str | None
    year_built: int | None
    area_sqft: int | None
    width_ft: int | None
    length_ft: int | None
    condition: str | None


class ValueOut(BaseModel):
    last_sale_date: date | None = None
    last_sale_price: float | None = None
    price_per_sqft: float | None = None
    neighborhood_median_price_per_sqft: float | None = None
    market_value_2025: int | None = None
    market_value_2026: int | None = None
    change_pct: float | None = None
    ratio_to_last_sale: float | None = None
    value_method: str | None = None
    appeal_year: int | None = None
    tif: bool = False
    abated: bool = False


class TaxOut(BaseModel):
    tax_year: int
    annual_bill: float
    effective_rate_pct: float | None
    district_median_effective_rate_pct: float | None
    gross_rate: float | None
    owner_occupied: bool
    homestead: bool
    rental_registered: bool
    foreclosure_date: date | None
    net_delinquent: float | None
    balance_due: float | None
    cauv: bool
    abated: bool


class OwnerOut(BaseModel):
    name: str | None
    name2: str | None
    mailing_address: str | None
    out_of_state: bool
    occupancy: str
    occupancy_reason: str | None


class ParcelProfile(BaseModel):
    parcel_id: str
    address: str | None
    is_active: bool
    parcel_class: str
    latitude: float | None
    longitude: float | None
    neighborhood: NeighborhoodRef | None
    tax_district: DistrictRef | None
    facts: Facts | None
    lot: Lot | None
    dwellings: list[DwellingOut]
    features: list[FeatureOut]
    value: ValueOut
    tax: TaxOut | None
    owner: OwnerOut | None
    badges: list[str]


class TimelineEvent(BaseModel):
    date: dt.date  # a field named "date" needs the module-qualified type
    kind: Literal["sale", "built", "reappraisal"]
    title: str
    amount: float | None = None
    detail: dict[str, object] = {}


_OCCUPANCY_BADGES = {
    "owner_occupied": "owner_occupied", "company": "company_owned", "trust": "trust_owned",
    "government": "government_owned", "absentee_individual": "absentee_owner",
}


async def _one(session, table, **where):
    stmt = sa.select(table).where(*[table.c[k] == v for k, v in where.items()])
    return (await session.execute(stmt)).mappings().first()


async def _district_median_rate(session, district: str) -> float | None:
    s = ParcelSummary.__table__

    async def compute():
        rows = (await session.execute(
            sa.select(s.c.annual_tax, s.c.market_value).where(
                s.c.tax_district == district, s.c.parcel_class == "R",
                s.c.annual_tax > 0, s.c.market_value > 0,
            )
        )).all()
        rates = [tax / value * 100 for tax, value in rows]
        return statistics.median(rates) if rates else None

    version = await data_version(session)
    return await cache.get_or_compute(("district-rate", district), version, compute)


def _facts(dwellings: list, features: list) -> Facts | None:
    if not dwellings:
        return None
    primary = max(dwellings, key=lambda d: (d["living_sqft"] or 0, -d["card"]))
    total = lambda key: sum(d[key] or 0 for d in dwellings)  # noqa: E731
    return Facts(
        living_sqft=total("living_sqft") or None,
        beds=total("beds") or None,
        baths=total("full_baths") + 0.5 * total("half_baths"),
        full_baths=total("full_baths"),
        half_baths=total("half_baths"),
        stories=primary["stories"],
        style=primary["style"],
        year_built=primary["year_built"],
        year_built_is_placeholder=primary["year_built_is_placeholder"],
        grade=primary["grade"],
        grade_label=primary["grade_label"],
        condition=primary["condition"],
        exterior=primary["exterior"],
        basement=primary["basement"],
        finished_basement_sqft=primary["finished_basement_sqft"],
        heating=primary["heating"],
        fuel=primary["fuel"],
        has_central_air=any(d["has_central_air"] for d in dwellings),
        fireplaces=total("fireplaces"),
        attached_garage_sqft=total("attached_garage_sqft"),
        detached_garage_sqft=sum(
            f["area_sqft"] or 0 for f in features if (f["code"] or "").startswith("RG")
        ),
        basement_garage_cars=total("basement_garage_cars"),
        has_pool=any((f["code"] or "").startswith("RP") for f in features),
    )


async def get_profile(session, parcel_id: str) -> ParcelProfile:
    parcel = await _one(session, Parcel.__table__, parcel_id=parcel_id)
    if parcel is None:
        raise not_found(f"Parcel {parcel_id}")
    summary = await _one(session, ParcelSummary.__table__, parcel_id=parcel_id)
    detail = await _one(session, ParcelDetail.__table__, parcel_id=parcel_id)
    value = await _one(session, ParcelValue.__table__, parcel_id=parcel_id)
    tax = await _one(session, ParcelTax.__table__, parcel_id=parcel_id)
    dw, ft = Dwelling.__table__, ParcelFeature.__table__
    dwellings = (await session.execute(
        sa.select(dw).where(dw.c.parcel_id == parcel_id).order_by(dw.c.card)
    )).mappings().all()
    features = (await session.execute(
        sa.select(ft).where(ft.c.parcel_id == parcel_id).order_by(ft.c.card, ft.c.line)
    )).mappings().all()

    neighborhood = None
    if parcel["neighborhood"]:
        hood = await _one(session, Neighborhood.__table__, code=parcel["neighborhood"])
        neighborhood = NeighborhoodRef(code=parcel["neighborhood"], **(
            {"name": hood["name"], "display_name": hood["display_name"]} if hood else {}))
    district = None
    if parcel["tax_district"]:
        row = await _one(session, TaxDistrict.__table__, code=parcel["tax_district"])
        district = DistrictRef(code=parcel["tax_district"], **(
            {"name": row["name"], "school_district": row["school_district"]} if row else {}))

    hood_summary = None
    if parcel["neighborhood"]:
        hood_summary = await _one(session, NeighborhoodSummary.__table__,
                                  code=parcel["neighborhood"])
    last_price = summary["last_sale_price"] if summary else None
    total_2026 = value["total_2026"] if value else None
    value_out = ValueOut(
        last_sale_date=summary["last_sale_date"] if summary else None,
        last_sale_price=last_price,
        price_per_sqft=summary["price_per_sqft"] if summary else None,
        neighborhood_median_price_per_sqft=(
            hood_summary["median_price_per_sqft_24m"] if hood_summary else None),
        market_value_2025=value["total_2025"] if value else None,
        market_value_2026=total_2026,
        change_pct=value["change_pct"] if value else None,
        ratio_to_last_sale=(total_2026 / last_price) if total_2026 and last_price else None,
        value_method=value["value_method"] if value else None,
        appeal_year=value["appeal_year"] if value else None,
        tif=bool(value["tif"]) if value else False,
        abated=bool(value["abated"]) if value else False,
    )

    tax_out = owner_out = None
    badges: list[str] = []
    if tax:
        rate = (tax["annual_bill"] / tax["market_value"] * 100) if tax["market_value"] else None
        tax_out = TaxOut(
            tax_year=tax["tax_year"], annual_bill=tax["annual_bill"], effective_rate_pct=rate,
            district_median_effective_rate_pct=(
                await _district_median_rate(session, parcel["tax_district"])
                if parcel["tax_district"] else None),
            gross_rate=tax["gross_rate"], owner_occupied=tax["owner_occupied"],
            homestead=tax["homestead"], rental_registered=tax["rental_registered"],
            foreclosure_date=tax["foreclosure_date"], net_delinquent=tax["net_delinquent"],
            balance_due=tax["balance_due"], cauv=tax["cauv"], abated=tax["abated"],
        )
        owner_out = OwnerOut(
            name=tax["owner_name"], name2=tax["owner_name2"],
            mailing_address=tax["mailing_address"], out_of_state=tax["out_of_state"],
            occupancy=tax["occupancy"], occupancy_reason=tax["occupancy_reason"],
        )
        if tax["occupancy"] in _OCCUPANCY_BADGES:
            badges.append(_OCCUPANCY_BADGES[tax["occupancy"]])
        if tax["out_of_state"]:
            badges.append("out_of_state_owner")
        if (tax["net_delinquent"] or 0) > 0:
            badges.append("tax_delinquent")
        if tax["foreclosure_date"]:
            badges.append("foreclosure_filed")
    if value_out.tif:
        badges.append("tif")
    if not parcel["is_active"]:
        badges.append("retired_parcel")

    return ParcelProfile(
        parcel_id=parcel_id,
        address=parcel["parcel_location"],
        is_active=bool(parcel["is_active"]),
        parcel_class=parcel["parcel_class"].name,
        latitude=summary["latitude"] if summary else None,
        longitude=summary["longitude"] if summary else None,
        neighborhood=neighborhood,
        tax_district=district,
        facts=_facts(dwellings, features),
        lot=Lot(
            land_use=detail["land_use"], living_units=detail["living_units"],
            lot_sqft=detail["lot_sqft"], lot_acres=detail["lot_acres"],
            frontage_ft=detail["frontage_ft"], depth_ft=detail["depth_ft"],
        ) if detail else None,
        dwellings=[
            DwellingOut(card=d["card"], living_sqft=d["living_sqft"], year_built=d["year_built"],
                        style=d["style"], sketch=json.loads(d["sketch"]) if d["sketch"] else [])
            for d in dwellings
        ],
        features=[FeatureOut(**{k: f[k] for k in FeatureOut.model_fields}) for f in features],
        value=value_out,
        tax=tax_out,
        owner=owner_out,
        badges=badges,
    )


def _built_title(year: int, placeholder: bool) -> str:
    if placeholder and year == 1919:
        return "Built before 1920"
    if placeholder:
        return "Built around 1900"
    return "Built"


async def get_timeline(session, parcel_id: str) -> list[TimelineEvent]:
    if await _one(session, Parcel.__table__, parcel_id=parcel_id) is None:
        raise not_found(f"Parcel {parcel_id}")
    t = Transaction.__table__
    sales = (await session.execute(
        sa.select(
            t.c.sale_date, t.c.sale_price, t.c.new_owner, t.c.old_owner, t.c.sale_validity,
            t.c.deed_reference,
            sa.case((market_sale_criteria(include_multi_parcel=True), True), else_=False)
            .label("is_market"),
        ).where(t.c.parcel_id == parcel_id)
    )).mappings().all()
    events = [
        TimelineEvent(
            date=s["sale_date"], kind="sale",
            title="Sold" if s["is_market"] else "Transferred",
            amount=s["sale_price"],
            detail={"buyer": s["new_owner"], "seller": s["old_owner"],
                    "is_market_sale": bool(s["is_market"]), "validity": s["sale_validity"],
                    "deed_reference": s["deed_reference"]},
        )
        for s in sales
    ]
    dw = Dwelling.__table__
    primary = (await session.execute(
        sa.select(dw.c.year_built, dw.c.year_built_is_placeholder)
        .where(dw.c.parcel_id == parcel_id, dw.c.year_built.isnot(None))
        .order_by(sa.func.coalesce(dw.c.living_sqft, 0).desc(), dw.c.card).limit(1)
    )).first()
    if primary:
        events.append(TimelineEvent(
            date=date(primary.year_built, 1, 1), kind="built",
            title=_built_title(primary.year_built, primary.year_built_is_placeholder),
        ))
    value = await _one(session, ParcelValue.__table__, parcel_id=parcel_id)
    if value and value["total_2026"] is not None:
        events.append(TimelineEvent(
            date=REAPPRAISAL_DATE, kind="reappraisal", title="2026 reappraisal",
            amount=value["total_2026"],
            detail={"previous": value["total_2025"], "change_pct": value["change_pct"]},
        ))
    return sorted(events, key=lambda e: e.date, reverse=True)
```

Create `src/api/routers/parcels.py`:

```python
from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from db.engine import get_session
from services.analytics.parcels import ParcelProfile, TimelineEvent, get_profile, get_timeline

router = APIRouter(prefix="/parcels", tags=["parcels"])


@router.get("/{parcel_id}", response_model=ParcelProfile)
async def profile(parcel_id: str, session: AsyncSession = Depends(get_session)):
    return await get_profile(session, parcel_id)


@router.get("/{parcel_id}/timeline", response_model=list[TimelineEvent])
async def timeline(parcel_id: str, session: AsyncSession = Depends(get_session)):
    return await get_timeline(session, parcel_id)
```

Register it in `src/api/__init__.py`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/api/test_parcels.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/services/analytics/parcels.py src/api tests/api/test_parcels.py
git commit -m "Add the property profile and timeline endpoints"
```

---

### Task 18: Comparable sales

**Files:**
- Create: `src/services/analytics/comps.py`
- Modify: `src/api/routers/parcels.py`
- Test: `tests/api/test_comps.py`

**Interfaces:**
- Consumes: `parcel_summary`, `dwelling`, `transaction`, `market_sale_criteria`, `latest_sale_date` (Task 12).
- Produces: `GET /v2/parcels/{parcel_id}/comps?limit=10` returning `CompsResult`:
  `{subject: {living_sqft, beds, baths, year_built, style}, basis: "neighborhood" | "radius" | "none", message: str | None, median_price: float | None, median_price_per_sqft: float | None, comps: [{parcel_id, address, sale_date, sale_price, price_per_sqft, living_sqft, beds, baths, year_built, style, distance_miles, similarity}]}`.
- Rules (spec 6.4): market sales in the 24 months before the latest sale date in the data, not part of a multi-parcel deal, same neighborhood (widening to a 1-mile radius when fewer than 5 match), same style family, living area within 20%, beds within 1, baths within 1, year built within 15 years. Similarity score out of 100: minus 1 per percent of living-area difference, 0.5 per year of age difference, 5 per bed or bath of difference, 1 per month since the sale, and 10 per mile for radius matches.

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_comps.py`:

```python
import datetime as dt

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from api.cache import cache
from db.county_models import Dwelling, ParcelSummary
from db.engine import get_session
from db.models import Parcel, ParcelClass, Transaction
from main import app

SNAP = dt.date(2026, 8, 31)


def home(pid, nbhd, sqft, beds, baths, year, style, lat, lng, sale=None, buyer="B"):
    rows = [
        Parcel(parcel_id=pid, parcel_location=f"{pid} ST", parcel_class=ParcelClass.R, acres=0.1,
               neighborhood=nbhd, latitude=lat, longitude=lng),
        ParcelSummary(parcel_id=pid, parcel_class="R", neighborhood=nbhd, latitude=lat,
                      longitude=lng, address=f"{pid} ST", living_sqft=sqft, beds=beds,
                      baths=float(baths), year_built=year, occupancy="unknown"),
        Dwelling(parcel_id=pid, card=1, living_sqft=sqft, beds=beds, full_baths=baths,
                 half_baths=0, year_built=year, style_code=style, snapshot_date=SNAP),
    ]
    if sale:
        rows.append(Transaction(
            parcel_id=pid, sale_date=sale[0], sale_price=sale[1], old_owner="S", new_owner=buyer,
            parcel_location="X", mailing_name=buyer, mailing_address="X",
            parcel_class=ParcelClass.R, acres=0.1, taxable_land=0, taxable_building=0,
            taxable_total=0, sale_validity="VALID SALE"))
    return rows


@pytest.fixture
async def comps_api(db_engine):
    cache.clear()

    async def override():
        async with AsyncSession(db_engine, expire_on_commit=False) as s:
            yield s

    app.dependency_overrides[get_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c, db_engine
    app.dependency_overrides.clear()


async def add(engine, *groups):
    async with AsyncSession(engine) as s:
        for group in groups:
            s.add_all(group)
        await s.commit()


async def test_neighborhood_comps_ranked_by_similarity(comps_api):
    api, engine = comps_api
    d = dt.date(2026, 6, 1)
    await add(
        engine,
        home("S", "NB1", 1500, 3, 2, 1960, "03", 39.70, -84.10),
        home("C1", "NB1", 1510, 3, 2, 1960, "03", 39.701, -84.10, (d, 200_000), "B1"),
        home("C2", "NB1", 1650, 3, 2, 1962, "03", 39.702, -84.10, (d, 210_000), "B2"),
        home("C3", "NB1", 1400, 3, 2, 1958, "03", 39.703, -84.10, (d, 190_000), "B3"),
        home("C4", "NB1", 1550, 4, 2, 1965, "03", 39.704, -84.10, (d, 205_000), "B4"),
        home("C5", "NB1", 1450, 3, 1, 1955, "03", 39.705, -84.10, (d, 185_000), "B5"),
        home("BIG", "NB1", 2400, 3, 2, 1960, "03", 39.706, -84.10, (d, 400_000), "B6"),
        home("COLONIAL", "NB1", 1500, 3, 2, 1960, "07", 39.707, -84.10, (d, 250_000), "B7"),
        home("OLD", "NB1", 1500, 3, 2, 1960, "03", 39.708, -84.10,
             (dt.date(2023, 1, 1), 150_000), "B8"),
    )
    body = (await api.get("/v2/parcels/S/comps")).json()
    assert body["basis"] == "neighborhood"
    ids = [c["parcel_id"] for c in body["comps"]]
    assert ids[0] == "C1"
    assert set(ids) == {"C1", "C2", "C3", "C4", "C5"}
    assert body["median_price"] == 200_000


async def test_widens_to_radius_when_neighborhood_is_thin(comps_api):
    api, engine = comps_api
    d = dt.date(2026, 6, 1)
    await add(
        engine,
        home("S", "NB1", 1500, 3, 2, 1960, "03", 39.70, -84.10),
        home("C1", "NB1", 1500, 3, 2, 1960, "03", 39.701, -84.10, (d, 200_000), "B1"),
        home("NEAR", "NB2", 1500, 3, 2, 1960, "03", 39.705, -84.10, (d, 210_000), "B2"),
        home("FAR", "NB3", 1500, 3, 2, 1960, "03", 39.80, -84.10, (d, 220_000), "B3"),
    )
    body = (await api.get("/v2/parcels/S/comps")).json()
    assert body["basis"] == "radius"
    ids = {c["parcel_id"] for c in body["comps"]}
    assert ids == {"C1", "NEAR"}
    near = next(c for c in body["comps"] if c["parcel_id"] == "NEAR")
    assert near["distance_miles"] == pytest.approx(0.345, abs=0.01)


async def test_no_dwelling_means_no_comps(comps_api):
    api, engine = comps_api
    async with AsyncSession(engine) as s:
        s.add(Parcel(parcel_id="LOT", parcel_location="LOT ST", parcel_class=ParcelClass.R,
                     acres=0.2))
        await s.commit()
    body = (await api.get("/v2/parcels/LOT/comps")).json()
    assert (body["basis"], body["comps"]) == ("none", [])
    assert body["message"] == "No dwelling on record to compare"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/api/test_comps.py -v`
Expected: FAIL (404 from the missing route).

- [ ] **Step 3: Implement `src/services/analytics/comps.py`**

```python
"""Comparable sales for a parcel (spec section 6.4)."""
from __future__ import annotations

import math
import statistics
from datetime import date, timedelta

import sqlalchemy as sa
from pydantic import BaseModel

from api.errors import not_found
from db.county_models import Dwelling, ParcelSummary
from db.criteria import market_sale_criteria
from db.models import Parcel, Transaction
from derived.summary import latest_sale_date

STYLE_FAMILIES = {
    "01": "split", "02": "split", "03": "ranch", "04": "attached", "05": "two_story",
    "06": "story_and_half", "07": "two_story", "08": "story_and_half", "09": "two_story",
    "10": "attached", "11": "multi", "12": "multi", "13": "other", "14": "two_story",
    "15": "two_story", "16": "two_story", "17": "manufactured", "18": "manufactured",
    "19": "other", "20": "two_story",
}
MIN_NEIGHBORHOOD_COMPS = 5
RADIUS_MILES = 1.0
LOOKBACK_DAYS = 730


class Subject(BaseModel):
    living_sqft: int | None = None
    beds: int | None = None
    baths: float | None = None
    year_built: int | None = None
    style: str | None = None


class Comp(BaseModel):
    parcel_id: str
    address: str | None
    sale_date: date
    sale_price: float
    price_per_sqft: float | None
    living_sqft: int | None
    beds: int | None
    baths: float | None
    year_built: int | None
    style: str | None
    distance_miles: float | None
    similarity: float


class CompsResult(BaseModel):
    subject: Subject
    basis: str
    message: str | None = None
    median_price: float | None = None
    median_price_per_sqft: float | None = None
    comps: list[Comp] = []


def miles_between(lat1, lng1, lat2, lng2) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _first_card_style(dw):
    inner = Dwelling.__table__.alias("first_card")
    first = sa.select(sa.func.min(inner.c.card)).where(inner.c.parcel_id == dw.c.parcel_id)
    return dw.c.card == first.scalar_subquery()


async def _candidates(session, subject: dict, since: date, where) -> list[dict]:
    t, ps, dw = Transaction.__table__, ParcelSummary.__table__, Dwelling.__table__
    other = Transaction.__table__.alias("other")
    in_deal = sa.exists().where(
        other.c.sale_date == t.c.sale_date, other.c.new_owner == t.c.new_owner,
        other.c.sale_price == t.c.sale_price, other.c.parcel_id != t.c.parcel_id,
    )
    sqft = subject["living_sqft"]
    query = (
        sa.select(t.c.parcel_id, t.c.sale_date, t.c.sale_price, ps.c.address,
                  ps.c.living_sqft, ps.c.beds, ps.c.baths, ps.c.year_built,
                  ps.c.latitude, ps.c.longitude, dw.c.style_code, dw.c.style)
        .select_from(t)
        .join(ps, ps.c.parcel_id == t.c.parcel_id)
        .join(dw, sa.and_(dw.c.parcel_id == t.c.parcel_id, _first_card_style(dw)))
        .where(
            market_sale_criteria(), ~in_deal, t.c.sale_date >= since,
            t.c.parcel_id != subject["parcel_id"],
            ps.c.living_sqft.between(sqft * 0.8, sqft * 1.2),
            where,
        )
    )
    return [dict(r) for r in (await session.execute(query)).mappings().all()]


def _differs(subject: dict, c: dict, key: str, tolerance: float) -> bool:
    a, b = subject[key], c[key]
    return a is not None and b is not None and abs(a - b) > tolerance


def _matches(subject: dict, c: dict) -> bool:
    if STYLE_FAMILIES.get(c["style_code"]) != STYLE_FAMILIES.get(subject["style_code"]):
        return False
    return not (
        _differs(subject, c, "beds", 1)
        or _differs(subject, c, "baths", 1)
        or _differs(subject, c, "year_built", 15)
    )


def _score(subject: dict, c: dict, anchor: date, distance: float | None) -> float:
    score = 100.0
    score -= abs(c["living_sqft"] - subject["living_sqft"]) / subject["living_sqft"] * 100
    if subject["year_built"] and c["year_built"]:
        score -= abs(c["year_built"] - subject["year_built"]) * 0.5
    for key in ("beds", "baths"):
        if subject[key] is not None and c[key] is not None:
            score -= abs(c[key] - subject[key]) * 5
    score -= (anchor - c["sale_date"]).days / 30.4
    if distance is not None:
        score -= distance * 10
    return round(score, 1)


async def get_comps(session, parcel_id: str, limit: int = 10) -> CompsResult:
    ps, dw = ParcelSummary.__table__, Dwelling.__table__
    parcel = (await session.execute(
        sa.select(Parcel.__table__.c.parcel_id).where(Parcel.__table__.c.parcel_id == parcel_id)
    )).first()
    if parcel is None:
        raise not_found(f"Parcel {parcel_id}")
    row = (await session.execute(
        sa.select(ps.c.parcel_id, ps.c.neighborhood, ps.c.living_sqft, ps.c.beds, ps.c.baths,
                  ps.c.year_built, ps.c.latitude, ps.c.longitude, dw.c.style_code, dw.c.style)
        .select_from(ps)
        .join(dw, sa.and_(dw.c.parcel_id == ps.c.parcel_id, _first_card_style(dw)))
        .where(ps.c.parcel_id == parcel_id)
    )).mappings().first()
    if row is None or not row["living_sqft"]:
        return CompsResult(subject=Subject(), basis="none",
                           message="No dwelling on record to compare")
    subject = dict(row)
    subject_out = Subject(living_sqft=subject["living_sqft"], beds=subject["beds"],
                          baths=subject["baths"], year_built=subject["year_built"],
                          style=subject["style"])
    anchor = await latest_sale_date(await session.connection()) or date.today()
    since = anchor - timedelta(days=LOOKBACK_DAYS)

    basis = "neighborhood"
    found = [c for c in await _candidates(session, subject, since,
                                          ps.c.neighborhood == subject["neighborhood"])
             if _matches(subject, c)]
    distances: dict[str, float | None] = {c["parcel_id"]: None for c in found}
    if len(found) < MIN_NEIGHBORHOOD_COMPS and subject["latitude"] is not None:
        basis = "radius"
        dlat = RADIUS_MILES / 69.0
        dlng = RADIUS_MILES / (69.0 * math.cos(math.radians(subject["latitude"])))
        box = sa.and_(
            ps.c.latitude.between(subject["latitude"] - dlat, subject["latitude"] + dlat),
            ps.c.longitude.between(subject["longitude"] - dlng, subject["longitude"] + dlng),
        )
        found = []
        for c in await _candidates(session, subject, since, box):
            miles = miles_between(subject["latitude"], subject["longitude"],
                                  c["latitude"], c["longitude"])
            if miles <= RADIUS_MILES and _matches(subject, c):
                found.append(c)
                distances[c["parcel_id"]] = round(miles, 3)

    comps = sorted(
        (
            Comp(
                parcel_id=c["parcel_id"], address=c["address"], sale_date=c["sale_date"],
                sale_price=c["sale_price"],
                price_per_sqft=c["sale_price"] / c["living_sqft"] if c["living_sqft"] else None,
                living_sqft=c["living_sqft"], beds=c["beds"], baths=c["baths"],
                year_built=c["year_built"], style=c["style"],
                distance_miles=distances.get(c["parcel_id"]),
                similarity=_score(subject, c, anchor, distances.get(c["parcel_id"])),
            )
            for c in found
        ),
        key=lambda comp: comp.similarity, reverse=True,
    )[:limit]
    return CompsResult(
        subject=subject_out, basis=basis if comps else "none",
        message=None if comps else "No comparable sales in the last 24 months",
        median_price=statistics.median([c.sale_price for c in comps]) if comps else None,
        median_price_per_sqft=statistics.median(
            [c.price_per_sqft for c in comps if c.price_per_sqft]) if comps else None,
        comps=comps,
    )
```

Add the route to `src/api/routers/parcels.py`:

```python
from fastapi import Query

from services.analytics.comps import CompsResult, get_comps


@router.get("/{parcel_id}/comps", response_model=CompsResult)
async def comps(parcel_id: str, limit: int = Query(10, ge=1, le=50),
                session: AsyncSession = Depends(get_session)):
    return await get_comps(session, parcel_id, limit)
```

(Merge the imports into the file's existing import block.)

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/api/test_comps.py -v`
Expected: all 3 tests PASS. In the first test `BIG` fails the 20% living-area window, `COLONIAL` the style family, `OLD` the 24-month window; the anchor is the newest sale in the test data (2026-06-01).

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/services/analytics/comps.py src/api/routers/parcels.py tests/api/test_comps.py
git commit -m "Add comparable sales matched on neighborhood or radius, style and size"
```

---

### Task 19: Sales list, CSV export and flips

**Files:**
- Modify: `src/db/criteria.py` (add `plausible_price_criteria`)
- Create: `src/services/analytics/sales.py`, `src/api/routers/sales.py`
- Modify: `src/main.py` (`get_flips` delegates to the service), `src/api/__init__.py`
- Test: `tests/api/test_sales.py`, `tests/test_criteria.py`

**Interfaces:**
- Produces:
  - `db.criteria.NOMINAL_RATIO = 0.10` and `plausible_price_criteria()`: a sale priced under 10% of the county's market value at the time (`transaction.assessed_total`) is a nominal transfer, not a market or distress price. Rows without a recorded value pass.
  - `db.criteria.single_parcel_criteria()`: excludes rows of a multi-parcel deal (another parcel sold on the same date to the same buyer for the same price), even when the county did not flag it. Used by price points (Task 20) and comps (replace the inline `in_deal` in `services/analytics/comps.py` with it in this task).
  - `GET /v2/sales?<filters>&sort=sale_date|sale_price|price_per_sqft|living_sqft&order=desc|asc&page=1&page_size=50&market_only=false` returning `SalesPage {total, page, page_size, applied_filters, rows: [SaleRow]}`. `SaleRow`: `id, parcel_id, sale_date, sale_price, address, buyer, seller, parcel_class, neighborhood, neighborhood_name, living_sqft, price_per_sqft, year_built, beds, baths, is_market_sale, validity, latitude, longitude`.
  - `GET /v2/sales.csv` with the same parameters (no paging), streamed.
  - `GET /v2/sales/flips?<filters>&max_hold_days=730&min_profit_pct=0.1&limit=100` returning `FlipsPage {applied_filters, rows: [FlipResult]}` (existing `FlipResult` model). Honors `date_from`, `date_to` and every listed class in `classes`.
  - `services.analytics.sales.find_flips(session, *, max_hold_days=730, min_profit_pct=0.1, min_profit=0.0, date_from=None, date_to=None, classes=None, limit=50) -> list[dict]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_criteria.py`:

```python
import datetime as dt

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from db.criteria import plausible_price_criteria
from db.models import Parcel, ParcelClass, Transaction


async def test_plausible_price_criteria(db_engine):
    async with AsyncSession(db_engine) as s:
        s.add(Parcel(parcel_id="P", parcel_location="X", parcel_class=ParcelClass.R, acres=0))
        for i, (price, value) in enumerate([(1_000, 120_000), (15_000, 120_000), (1_000, None)]):
            s.add(Transaction(
                parcel_id="P", sale_date=dt.date(2025, 1, 1 + i), sale_price=price,
                old_owner="A", new_owner="B", parcel_location="X", mailing_name="B",
                mailing_address="X", parcel_class=ParcelClass.R, acres=0, taxable_land=0,
                taxable_building=0, taxable_total=0, assessed_total=value,
            ))
        await s.commit()
        kept = (await s.exec(
            select(Transaction.sale_price).where(plausible_price_criteria())
        )).all()
    assert sorted(kept) == [1_000, 15_000]  # the $1,000 row with no recorded value passes
```

Create `tests/api/test_sales.py`:

```python
import csv
import io


async def get(api, path, **params):
    r = await api.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


async def test_first_page_newest_first(api):
    page = await get(api, "/v2/sales", page_size=3)
    assert page["total"] == 9
    assert [r["sale_date"] for r in page["rows"]] == ["2025-09-01", "2025-08-20", "2025-07-01"]
    assert page["applied_filters"] == []


async def test_second_page(api):
    page = await get(api, "/v2/sales", page_size=3, page=2)
    assert len(page["rows"]) == 3 and page["page"] == 2


async def test_sort_by_price_per_sqft_puts_missing_last(api):
    page = await get(api, "/v2/sales", sort="price_per_sqft", order="desc", page_size=20)
    values = [r["price_per_sqft"] for r in page["rows"]]
    known = [v for v in values if v is not None]
    assert known == sorted(known, reverse=True)
    assert values[len(known):] == [None] * (len(values) - len(known))


async def test_filters_are_honored_and_reported(api):
    page = await get(api, "/v2/sales", price_min=100_000, neighborhood="15007000",
                     market_only="true")
    assert [r["sale_price"] for r in page["rows"]] == [150_000]
    assert page["applied_filters"] == ["price_min", "neighborhood"]
    row = page["rows"][0]
    assert (row["neighborhood_name"], row["living_sqft"], row["is_market_sale"]) == (
        "NEWCOM KNOLLS", 1008, True
    )
    assert row["price_per_sqft"] == 150_000 / 1008


async def test_filters_matching_nothing_return_zeros(api):
    page = await get(api, "/v2/sales", price_min=10_000_000)
    assert (page["total"], page["rows"]) == (0, [])


async def test_nominal_transfer_is_not_a_market_sale(api):
    page = await get(api, "/v2/sales", page_size=1)
    assert page["rows"][0]["sale_price"] == 1
    assert page["rows"][0]["is_market_sale"] is False


async def test_csv_export(api):
    r = await api.get("/v2/sales.csv", params={"price_min": 100_000})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 6
    assert set(rows[0]) >= {"sale_date", "sale_price", "address", "buyer", "seller",
                            "price_per_sqft"}


async def test_flips_exclude_multi_parcel_deals(api):
    page = await get(api, "/v2/sales/flips")
    # R72: bought 2024-03-15 for 300k, sold 2025-08-20 for 330k = +10%.
    assert [(f["parcel_id"], f["buy_price"], f["sell_price"]) for f in page["rows"]] == [
        ("R72 00304 0025", 300_000, 330_000)
    ]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_criteria.py tests/api/test_sales.py -v`
Expected: FAIL (`ImportError` for `plausible_price_criteria`, 404 for the routes).

- [ ] **Step 3: Implement**

In `src/db/criteria.py` add:

```python
# A sale under this share of the county's market value at the time is a
# nominal transfer (the county records many "$1,000" and "$10" deeds), not a
# market price and not a distress price. Rows with no recorded value pass.
NOMINAL_RATIO = 0.10


def plausible_price_criteria() -> object:
    return or_(
        Transaction.assessed_total.is_(None),
        Transaction.assessed_total <= 0,
        Transaction.sale_price >= NOMINAL_RATIO * Transaction.assessed_total,
    )


def single_parcel_criteria() -> object:
    """Not part of a deal covering several parcels (same date, buyer and price).

    The county records the whole deal price on every parcel row and does not
    always flag it, so detect it structurally, as get_market_stats does.
    """
    t = Transaction.__table__
    other = t.alias("same_deal")
    return ~exists().where(
        other.c.sale_date == t.c.sale_date,
        other.c.new_owner == t.c.new_owner,
        other.c.sale_price == t.c.sale_price,
        other.c.parcel_id != t.c.parcel_id,
    )
```

(Change the import at the top of `src/db/criteria.py` to `from sqlalchemy import and_, exists, or_`.) In `src/services/analytics/comps.py`, delete the `other`/`in_deal` lines in `_candidates` and use `single_parcel_criteria()` in place of `~in_deal`.

Create `src/services/analytics/sales.py`:

```python
"""Sales list, CSV export and flip detection."""
from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterator
from datetime import date

import sqlalchemy as sa
from pydantic import BaseModel

from api.filters import Filters, sale_conditions
from db.county_models import Neighborhood, ParcelSummary
from db.criteria import market_sale_criteria, plausible_price_criteria, single_parcel_criteria
from db.models import FlipResult, Parcel, ParcelClass, Transaction
from db.sqlutil import days_between

SORTABLE = ("sale_date", "sale_price", "price_per_sqft", "living_sqft")
CSV_COLUMNS = ("sale_date", "sale_price", "address", "buyer", "seller", "parcel_class",
               "neighborhood", "neighborhood_name", "living_sqft", "price_per_sqft",
               "year_built", "beds", "baths", "is_market_sale", "validity", "parcel_id")


class SaleRow(BaseModel):
    id: int
    parcel_id: str
    sale_date: date
    sale_price: float
    address: str | None
    buyer: str
    seller: str
    parcel_class: str
    neighborhood: str | None
    neighborhood_name: str | None
    living_sqft: int | None
    price_per_sqft: float | None
    year_built: int | None
    beds: int | None
    baths: float | None
    is_market_sale: bool
    validity: str | None
    latitude: float | None
    longitude: float | None


class SalesPage(BaseModel):
    total: int
    page: int
    page_size: int
    applied_filters: list[str]
    rows: list[SaleRow]


class FlipsPage(BaseModel):
    applied_filters: list[str]
    rows: list[FlipResult]


def _sales_select(f: Filters, market_only: bool):
    t, ps, p, n = (Transaction.__table__, ParcelSummary.__table__, Parcel.__table__,
                   Neighborhood.__table__)
    ppsf = sa.case((ps.c.living_sqft > 0, t.c.sale_price * 1.0 / ps.c.living_sqft))
    # A market sale: arm's length, a real price, and a per-parcel price (not
    # one row of a multi-parcel deal, flagged or not).
    market = sa.and_(market_sale_criteria(), plausible_price_criteria(), single_parcel_criteria())
    is_market = sa.case((market, True), else_=False)
    conditions = sale_conditions(f, t, ps)
    if market_only:
        conditions.append(market)
    columns = [
        t.c.id, t.c.parcel_id, t.c.sale_date, t.c.sale_price,
        t.c.parcel_location.label("address"), t.c.new_owner.label("buyer"),
        t.c.old_owner.label("seller"), t.c.parcel_class, p.c.neighborhood,
        n.c.name.label("neighborhood_name"), ps.c.living_sqft, ppsf.label("price_per_sqft"),
        ps.c.year_built, ps.c.beds, ps.c.baths, is_market.label("is_market_sale"),
        t.c.sale_validity.label("validity"), ps.c.latitude, ps.c.longitude,
    ]
    base = (
        sa.select(*columns).select_from(t)
        .outerjoin(ps, ps.c.parcel_id == t.c.parcel_id)
        .outerjoin(p, p.c.parcel_id == t.c.parcel_id)
        .outerjoin(n, n.c.code == p.c.neighborhood)
        .where(*conditions)
    )
    sort_columns = {"sale_date": t.c.sale_date, "sale_price": t.c.sale_price,
                    "price_per_sqft": ppsf, "living_sqft": ps.c.living_sqft}
    return base, sort_columns, t.c.id


def _row(mapping) -> dict:
    row = dict(mapping)
    cls = row["parcel_class"]
    row["parcel_class"] = cls.name if isinstance(cls, ParcelClass) else cls
    row["is_market_sale"] = bool(row["is_market_sale"])
    return row


def _ordered(base, sort_columns, tiebreak, sort: str, order: str):
    column = sort_columns[sort]
    direction = column.desc() if order == "desc" else column.asc()
    return base.order_by(sa.nulls_last(direction), tiebreak.desc())


async def list_sales(session, f: Filters, *, sort: str, order: str, page: int, page_size: int,
                     market_only: bool) -> SalesPage:
    base, sort_columns, tiebreak = _sales_select(f, market_only)
    total = (await session.execute(
        sa.select(sa.func.count()).select_from(base.subquery())
    )).scalar_one()
    rows = (await session.execute(
        _ordered(base, sort_columns, tiebreak, sort, order)
        .limit(page_size).offset((page - 1) * page_size)
    )).mappings().all()
    return SalesPage(total=total, page=page, page_size=page_size, applied_filters=f.active(),
                     rows=[SaleRow(**_row(r)) for r in rows])


async def stream_sales_csv(session, f: Filters, *, sort: str, order: str,
                           market_only: bool) -> AsyncIterator[str]:
    base, sort_columns, tiebreak = _sales_select(f, market_only)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    yield buffer.getvalue()
    result = await session.stream(_ordered(base, sort_columns, tiebreak, sort, order))
    async for partition in result.mappings().partitions(2000):
        buffer.seek(0)
        buffer.truncate()
        for mapping in partition:
            row = _row(mapping)
            writer.writerow(["" if row[c] is None else row[c] for c in CSV_COLUMNS])
        yield buffer.getvalue()


async def find_flips(
    session,
    *,
    max_hold_days: int = 730,
    min_profit_pct: float = 0.1,
    min_profit: float = 0.0,
    date_from: date | None = None,
    date_to: date | None = None,
    classes: list[ParcelClass] | None = None,
    limit: int = 50,
) -> list[dict]:
    """Paste here the body of get_flips from src/main.py (see Step 4)."""
```

- [ ] **Step 4: Move the flip query into the service**

Cut the body of `get_flips` in `src/main.py` (from its docstring through `return result.mappings().all()`) into `find_flips`, replacing the placeholder docstring, then make exactly these edits in the moved code:

1. In the `sides` subquery, change `.where(market_sale_criteria(include_distress=True))` to
   `.where(market_sale_criteria(include_distress=True), plausible_price_criteria())`.
2. Replace the three trailing filter blocks with:

```python
    if date_from:
        query = query.where(t1.c.sale_date >= date_from)
    if date_to:
        query = query.where(t2.c.sale_date <= date_to)
    if classes:
        query = query.where(t1.c.parcel_class.in_([c.value for c in classes]))

    result = await session.execute(query)
    return [dict(r) for r in result.mappings().all()]
```

3. Change `desc(profit_pct_expr)` to `profit_pct_expr.desc()` and `select(` to `sa.select(`, `func.` to `sa.func.`.

Replace the old route's body in `src/main.py` with a delegation (keep its signature and decorator):

```python
    return await find_flips(
        session, max_hold_days=max_hold_days, min_profit_pct=min_profit_pct,
        min_profit=min_profit, date_from=sale_date__gte, date_to=sale_date__lte,
        classes=[parcel_class] if parcel_class else None, limit=limit,
    )
```

and import `find_flips` from `services.analytics.sales` at the top of `main.py`.

Create `src/api/routers/sales.py`:

```python
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from api.filters import Filters, get_filters, honored
from db.engine import get_session
from db.models import ParcelClass
from services.analytics.sales import (
    FlipsPage,
    SalesPage,
    find_flips,
    list_sales,
    stream_sales_csv,
)

router = APIRouter(prefix="/sales", tags=["sales"])
Sort = Literal["sale_date", "sale_price", "price_per_sqft", "living_sqft"]
Order = Literal["desc", "asc"]


@router.get("", response_model=SalesPage)
async def sales(
    f: Filters = Depends(get_filters),
    sort: Sort = "sale_date",
    order: Order = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    market_only: bool = False,
    session: AsyncSession = Depends(get_session),
):
    return await list_sales(session, f, sort=sort, order=order, page=page,
                            page_size=page_size, market_only=market_only)


@router.get(".csv")
async def sales_csv(
    f: Filters = Depends(get_filters),
    sort: Sort = "sale_date",
    order: Order = "desc",
    market_only: bool = False,
    session: AsyncSession = Depends(get_session),
):
    return StreamingResponse(
        stream_sales_csv(session, f, sort=sort, order=order, market_only=market_only),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="sales.csv"'},
    )


@router.get("/flips", response_model=FlipsPage)
async def flips(
    f: Filters = Depends(get_filters),
    max_hold_days: int = Query(730, ge=1, le=3650),
    min_profit_pct: float = Query(0.1, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    rows = await find_flips(
        session, max_hold_days=max_hold_days, min_profit_pct=min_profit_pct,
        date_from=f.date_from, date_to=f.date_to,
        classes=[ParcelClass[c] for c in f.classes] if f.classes else None, limit=limit,
    )
    return FlipsPage(applied_filters=honored(f, ["date_from", "date_to", "classes"]), rows=rows)
```

`@router.get(".csv")` under the `/sales` prefix serves `/v2/sales.csv`; register the router in `src/api/__init__.py`.

- [ ] **Step 5: Run the tests, then the old flip tests**

Run: `uv run pytest tests/test_criteria.py tests/api/test_sales.py tests/test_api.py -v`
Expected: all PASS, including the two existing `/analytics/flips` tests (the delegation keeps their behavior; if one of them used a $1,000-style nominal buy on a valued parcel, it now correctly finds no flip; update that test's expectation and say so in the commit message).

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check src tests
git add src/db/criteria.py src/services/analytics/sales.py src/api src/main.py tests/test_criteria.py tests/api/test_sales.py
git commit -m "Add paged, sortable sales with CSV export; ignore nominal transfers in flips"
```

---

### Task 20: Market summary, trends, top buyers and sellers, price points

**Files:**
- Create: `src/services/analytics/market.py`, `src/api/routers/market.py`
- Modify: `src/main.py` (`get_market_stats`, `get_top_buyers`, `get_top_sellers` delegate), `src/api/__init__.py`
- Test: `tests/api/test_market.py`

**Interfaces:**
- Produces:
  - `market_buckets(session, *, granularity: Literal["month","quarter","year","all"], market_only: bool, apply: Callable[[Select], Select], with_ppsf: bool = False) -> list[MarketStatsBucket]`. `MarketStatsBucket` (in `db.models`) gains `median_price_per_sqft: float | None = None`.
  - `top_buyers(session, *, limit=10, min_spent=0.0, market_only=True, date_from=None, date_to=None)` and `top_sellers(session, *, limit=10, market_only=True, date_from=None, date_to=None)` returning `list[OwnerStats]`.
  - `GET /v2/market/summary?<filters>` returning `MarketSummary {applied_filters, anchor_date, totals: Bucket, current: WindowStats, prior: WindowStats}` where `WindowStats {label: str, start: date, end: date, stats: Bucket | None}` and `current`/`prior` are the 12 months ending at the newest sale in the data and the 12 months before (non-date filters still apply).
  - `GET /v2/market/trends?<filters>&granularity=year` returning `{applied_filters, buckets: [MarketStatsBucket]}` with `median_price_per_sqft` filled.
  - `GET /v2/market/top-buyers`, `GET /v2/market/top-sellers` (`?limit=15&date_from&date_to`) returning `{applied_filters, rows: [OwnerStats]}`.
  - `GET /v2/market/price-points?<filters>&limit=5000` returning `{applied_filters, total: int, points: [{parcel_id, sale_date, sale_price, parcel_class}]}`: a random sample across the whole filtered range (not just the newest rows), market sales only.

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_market.py`:

```python
import pytest


async def get(api, path, **params):
    r = await api.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


async def test_summary_windows_are_anchored_to_the_data(api):
    body = await get(api, "/v2/market/summary")
    assert body["anchor_date"] == "2025-08-20"
    assert (body["current"]["start"], body["current"]["end"]) == ("2024-08-21", "2025-08-20")
    assert (body["prior"]["start"], body["prior"]["end"]) == ("2023-08-22", "2024-08-20")
    # Current window market sales, single-parcel only: N64 150k, R72 330k.
    assert body["current"]["stats"]["transaction_count"] == 2
    assert body["current"]["stats"]["median_price"] == 240_000
    # Prior window: R72 300k (2024-03-15).
    assert body["prior"]["stats"]["transaction_count"] == 1
    assert body["current"]["label"] == "Aug 2024 - Aug 2025"


async def test_summary_honors_filters(api):
    body = await get(api, "/v2/market/summary", neighborhood="15007000")
    assert body["applied_filters"] == ["neighborhood"]
    assert body["totals"]["transaction_count"] == 2  # N64: 2019 and 2025 market sales


async def test_trends_include_price_per_sqft(api):
    body = await get(api, "/v2/market/trends", granularity="year")
    by_period = {b["period"]: b for b in body["buckets"]}
    assert by_period["2025"]["transaction_count"] == 2
    assert by_period["2025"]["median_price_per_sqft"] == pytest.approx(
        ((150_000 / 1008) + (330_000 / 5103)) / 2
    )


async def test_top_buyers(api):
    body = await get(api, "/v2/market/top-buyers", limit=3)
    assert body["applied_filters"] == []
    assert len(body["rows"]) <= 3


async def test_price_points_cover_the_range(api):
    body = await get(api, "/v2/market/price-points", limit=2)
    assert body["total"] == 6
    assert len(body["points"]) == 2
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/api/test_market.py -v`
Expected: FAIL (404s).

- [ ] **Step 3: Move and extend the market queries**

1. Add `median_price_per_sqft: float | None = None` to `MarketStatsBucket` in `src/db/models.py`.
2. Create `src/services/analytics/market.py` and move the body of `get_market_stats` from `src/main.py` into:

```python
async def market_buckets(
    session,
    *,
    granularity: Literal["month", "quarter", "year", "all"],
    market_only: bool,
    apply: Callable[[Select], Select],
    with_ppsf: bool = False,
) -> list[MarketStatsBucket]:
```

   In the moved code: replace `deal_rows = filters.filter(deal_rows).subquery()` with `deal_rows = apply(deal_rows).subquery()`; replace `session.exec(` with `session.execute(`; prefix bare SQLAlchemy names with `sa.` (and `func.` with `sa.func.`). Then add the price-per-square-foot median:

   - When `with_ppsf` is true, add to the `deal_rows` select (before `apply`) the column `sa.case((ps.c.living_sqft > 0, Transaction.sale_price * 1.0 / ps.c.living_sqft)).label("ppsf")`, and `.outerjoin(ps, ps.c.parcel_id == Transaction.parcel_id)` where `ps = ParcelSummary.__table__`. When false, add `sa.literal(None).label("ppsf")` instead so the shape is the same.
   - In `base`, add `deal_rows.c.ppsf.label("ppsf")`, `sa.func.row_number().over(partition_by=[year_col, sub_col], order_by=sa.nulls_last(deal_rows.c.ppsf.asc())).label("rn_ppsf")` and `sa.func.count(deal_rows.c.ppsf).over(partition_by=[year_col, sub_col]).label("cnt_ppsf")`.
   - In the final `query`, add `sa.func.avg(sa.case((sa.or_(base.c.rn_ppsf == (base.c.cnt_ppsf + 1) // 2, base.c.rn_ppsf == (base.c.cnt_ppsf + 2) // 2), base.c.ppsf))).label("median_ppsf")` and pass `median_price_per_sqft=row["median_ppsf"]` into each `MarketStatsBucket`. Rows with a NULL `ppsf` sort last and are not counted by `count(ppsf)`, so the middle row numbers land on real values.
   - When `apply` adds a join to `parcel_summary` for summary filters, it must use the same `ps` alias; pass the join through `apply` only when `with_ppsf` is false (see `_apply_filters` below).

3. The old route keeps its signature and becomes:

```python
    return await market_buckets(session, granularity=granularity, market_only=market_only,
                                apply=filters.filter)
```

4. Move `get_top_buyers` and `get_top_sellers` bodies into `top_buyers` and `top_sellers` in the same module (keyword-only parameters as in the Interfaces list; add `date_from`/`date_to` filtering on `Transaction.sale_date` before the aggregation), and make the old routes delegate with their existing parameters.

5. Add the new functions to `src/services/analytics/market.py`:

```python
import random
from datetime import date, timedelta

from api.filters import Filters, needs_summary, sale_conditions
from db.county_models import ParcelSummary
from db.criteria import market_sale_criteria, plausible_price_criteria, single_parcel_criteria
from derived.summary import latest_sale_date


class WindowStats(BaseModel):
    label: str
    start: date
    end: date
    stats: MarketStatsBucket | None


class MarketSummary(BaseModel):
    applied_filters: list[str]
    anchor_date: date | None
    totals: MarketStatsBucket | None
    current: WindowStats | None
    prior: WindowStats | None


def _apply_filters(f: Filters, *, join_summary: bool):
    t, ps = Transaction.__table__, ParcelSummary.__table__

    def apply(stmt):
        if join_summary:
            stmt = stmt.outerjoin(ps, ps.c.parcel_id == t.c.parcel_id)
        return stmt.where(*sale_conditions(f, t, ps))

    return apply


def _label(start: date, end: date) -> str:
    return f"{start:%b %Y} - {end:%b %Y}"


async def market_summary(session, f: Filters) -> MarketSummary:
    anchor = await latest_sale_date(await session.connection())
    apply = _apply_filters(f, join_summary=needs_summary(f))
    totals = await market_buckets(session, granularity="all", market_only=True, apply=apply)
    if anchor is None:
        return MarketSummary(applied_filters=f.active(), anchor_date=None,
                             totals=totals[0] if totals else None, current=None, prior=None)
    windows = []
    current_start = anchor - timedelta(days=364)
    previous_end = current_start - timedelta(days=1)
    for start, end in ((current_start, anchor),
                       (previous_end - timedelta(days=364), previous_end)):
        window_filters = f.model_copy(update={"date_from": start, "date_to": end})
        buckets = await market_buckets(
            session, granularity="all", market_only=True,
            apply=_apply_filters(window_filters, join_summary=needs_summary(f)),
        )
        windows.append(WindowStats(label=_label(start, end), start=start, end=end,
                                   stats=buckets[0] if buckets else None))
    return MarketSummary(applied_filters=f.active(), anchor_date=anchor,
                         totals=totals[0] if totals else None,
                         current=windows[0], prior=windows[1])


async def market_trends(session, f: Filters, granularity: str) -> list[MarketStatsBucket]:
    # with_ppsf joins parcel_summary itself, so apply only adds conditions.
    return await market_buckets(session, granularity=granularity, market_only=True,
                                apply=_apply_filters(f, join_summary=False), with_ppsf=True)


class PricePoint(BaseModel):
    parcel_id: str
    sale_date: date
    sale_price: float
    parcel_class: str


async def price_points(session, f: Filters, limit: int) -> tuple[int, list[PricePoint]]:
    t, ps = Transaction.__table__, ParcelSummary.__table__
    base = sa.select(t.c.parcel_id, t.c.sale_date, t.c.sale_price, t.c.parcel_class)
    if needs_summary(f):
        base = base.outerjoin(ps, ps.c.parcel_id == t.c.parcel_id)
    base = base.where(market_sale_criteria(), plausible_price_criteria(),
                      single_parcel_criteria(), *sale_conditions(f, t, ps))
    total = (await session.execute(
        sa.select(sa.func.count()).select_from(base.subquery())
    )).scalar_one()
    rows = (await session.execute(base.order_by(sa.func.random()).limit(limit))).all()
    points = [PricePoint(parcel_id=r.parcel_id, sale_date=r.sale_date, sale_price=r.sale_price,
                         parcel_class=r.parcel_class.name) for r in rows]
    return total, sorted(points, key=lambda p: p.sale_date)
```

   Each window spans 365 days, and the prior window ends the day before the current one starts. With the anchor 2025-08-20 that gives 2024-08-21..2025-08-20 and 2023-08-22..2024-08-20, as the test expects. (Drop the unused `random` import if ruff flags it.)

6. Create `src/api/routers/market.py`:

```python
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from api.cache import cache, data_version
from api.filters import Filters, get_filters, honored
from db.engine import get_session
from db.models import MarketStatsBucket, OwnerStats
from services.analytics.market import (
    MarketSummary,
    PricePoint,
    market_summary,
    market_trends,
    price_points,
    top_buyers,
    top_sellers,
)

router = APIRouter(prefix="/market", tags=["market"])


class TrendsResponse(BaseModel):
    applied_filters: list[str]
    buckets: list[MarketStatsBucket]


class OwnerRows(BaseModel):
    applied_filters: list[str]
    rows: list[OwnerStats]


class PricePoints(BaseModel):
    applied_filters: list[str]
    total: int
    points: list[PricePoint]


def _key(name: str, f: Filters, *extra) -> tuple:
    return (name, f.model_dump_json(), *extra)


@router.get("/summary", response_model=MarketSummary)
async def summary(f: Filters = Depends(get_filters),
                  session: AsyncSession = Depends(get_session)):
    version = await data_version(session)
    return await cache.get_or_compute(_key("summary", f), version,
                                      lambda: market_summary(session, f))


@router.get("/trends", response_model=TrendsResponse)
async def trends(f: Filters = Depends(get_filters),
                 granularity: Literal["month", "quarter", "year"] = "year",
                 session: AsyncSession = Depends(get_session)):
    version = await data_version(session)
    buckets = await cache.get_or_compute(_key("trends", f, granularity), version,
                                         lambda: market_trends(session, f, granularity))
    return TrendsResponse(applied_filters=f.active(), buckets=buckets)


@router.get("/top-buyers", response_model=OwnerRows)
async def buyers(f: Filters = Depends(get_filters), limit: int = Query(15, ge=1, le=100),
                 session: AsyncSession = Depends(get_session)):
    rows = await top_buyers(session, limit=limit, date_from=f.date_from, date_to=f.date_to)
    return OwnerRows(applied_filters=honored(f, ["date_from", "date_to"]), rows=rows)


@router.get("/top-sellers", response_model=OwnerRows)
async def sellers(f: Filters = Depends(get_filters), limit: int = Query(15, ge=1, le=100),
                  session: AsyncSession = Depends(get_session)):
    rows = await top_sellers(session, limit=limit, date_from=f.date_from, date_to=f.date_to)
    return OwnerRows(applied_filters=honored(f, ["date_from", "date_to"]), rows=rows)


@router.get("/price-points", response_model=PricePoints)
async def points(f: Filters = Depends(get_filters), limit: int = Query(5000, ge=1, le=20000),
                 session: AsyncSession = Depends(get_session)):
    total, pts = await price_points(session, f, limit)
    return PricePoints(applied_filters=f.active(), total=total, points=pts)
```

Register it in `src/api/__init__.py`.

- [ ] **Step 4: Run the tests (new and old)**

Run: `uv run pytest tests/api/test_market.py tests/test_api.py -v`
Expected: all PASS; the seven existing `/analytics/market-stats` tests and the top-buyer/seller tests prove the move kept behavior. `price-points` total is 6: the nine seeded rows minus the $1 transfer (below the market floor) and the two rows of the unflagged two-parcel deal (removed by `single_parcel_criteria`).

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/services/analytics/market.py src/api src/main.py src/db/models.py tests/api/test_market.py
git commit -m "Add market summary anchored to the newest sale, trends with price per sq ft, and price points"
```

---

### Task 21: Neighborhoods

**Files:**
- Modify: `src/services/analytics/market.py` (add `medians_by_group`)
- Create: `src/services/analytics/neighborhoods.py`, `src/api/routers/neighborhoods.py`
- Modify: `src/api/__init__.py`
- Test: `tests/api/test_neighborhoods.py`

**Interfaces:**
- Produces:
  - `medians_by_group(session, rows: Subquery, groups: list[str], value: str) -> dict[tuple, GroupStats]` with `GroupStats(count: int, median: float | None, total: float | None)`; portable window-function medians over any subquery.
  - `market_sale_rows(f: Filters, *, extra_columns=()) -> Subquery`: filtered market sales (`market_sale_criteria`, `plausible_price_criteria`, `single_parcel_criteria`, `sale_conditions`) with columns `parcel_id`, `neighborhood` (from `parcel`), `year`, `sale_price`, `ppsf`.
  - `GET /v2/neighborhoods?<filters>` returning `{applied_filters, rows: [NeighborhoodRow]}`; `NeighborhoodRow`: `code, name, display_name, tax_district, sales, median_price, median_price_per_sqft, total_volume, parcel_count, owner_occupied_share, median_year_built, median_value_change_pct`. Only neighborhoods with at least one matching sale, most sales first.
  - `GET /v2/neighborhoods/trends?<filters>&codes=...&limit=10&min_sales=5` returning `{applied_filters, rows: [{neighborhood, name, year, sales, median_price}]}`; without `codes`, the `limit` neighborhoods with the most matching sales. Years with fewer than `min_sales` sales are dropped.
  - `GET /v2/neighborhoods/{code}` returning `NeighborhoodReport {code, name, display_name, tax_district: DistrictRef | None, summary: dict | None, trend: [{year, sales, median_price, median_price_per_sqft}], recent_sales: [SaleRow]}`; 404 for unknown codes.

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_neighborhoods.py`:

```python
async def get(api, path, **params):
    r = await api.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


async def test_list(api):
    body = await get(api, "/v2/neighborhoods")
    rows = {r["code"]: r for r in body["rows"]}
    assert set(rows) == {"15007000", "3100WALK", "48150000"}
    assert (rows["15007000"]["sales"], rows["15007000"]["median_price"]) == (2, 120_000)
    assert rows["15007000"]["name"] == "NEWCOM KNOLLS"
    assert rows["48150000"]["sales"] == 1  # the two-parcel deal is excluded
    assert rows["48150000"]["parcel_count"] == 2


async def test_list_honors_date_filter(api):
    body = await get(api, "/v2/neighborhoods", date_from="2025-01-01")
    assert body["applied_filters"] == ["date_from"]
    assert {r["code"]: r["sales"] for r in body["rows"]} == {"15007000": 1, "3100WALK": 1}


async def test_trends(api):
    body = await get(api, "/v2/neighborhoods/trends", min_sales=1)
    assert {"neighborhood": "15007000", "name": "NEWCOM KNOLLS", "year": 2019, "sales": 1,
            "median_price": 90_000} in body["rows"]


async def test_report(api):
    body = await get(api, "/v2/neighborhoods/48150000")
    assert (body["name"], body["tax_district"]["code"]) == ("N BUTLER TWP", "A01")
    assert body["summary"]["parcel_count"] == 2
    assert body["trend"] == [{"year": 2023, "sales": 1, "median_price": 320_000,
                              "median_price_per_sqft": 320_000 / 2464}]
    assert [s["sale_price"] for s in body["recent_sales"]] == [320_000]


async def test_unknown_neighborhood_is_404(api):
    r = await api.get("/v2/neighborhoods/NOPE")
    assert r.status_code == 404
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/api/test_neighborhoods.py -v`
Expected: FAIL (404s).

- [ ] **Step 3: Implement**

Add to `src/services/analytics/market.py`:

```python
from dataclasses import dataclass


@dataclass
class GroupStats:
    count: int
    median: float | None
    total: float | None


async def medians_by_group(session, rows, groups: list[str], value: str) -> dict[tuple, GroupStats]:
    """Count, median and sum of ``value`` per group, portable to SQLite and Postgres.

    NULL values sort last and are not counted, so the middle row numbers land
    on real values.
    """
    keys = [rows.c[g] for g in groups]
    v = rows.c[value]
    ranked = sa.select(
        *[k.label(f"g{i}") for i, k in enumerate(keys)], v.label("v"),
        sa.func.row_number().over(partition_by=keys, order_by=sa.nulls_last(v.asc())).label("rn"),
        sa.func.count(v).over(partition_by=keys).label("cnt"),
    ).subquery()
    group_cols = [ranked.c[f"g{i}"] for i in range(len(keys))]
    middle = sa.or_(ranked.c.rn == (ranked.c.cnt + 1) // 2, ranked.c.rn == (ranked.c.cnt + 2) // 2)
    query = sa.select(
        *group_cols, sa.func.count(ranked.c.v), sa.func.avg(sa.case((middle, ranked.c.v))),
        sa.func.sum(ranked.c.v),
    ).group_by(*group_cols)
    out = {}
    for row in (await session.execute(query)).all():
        *key, count, median, total = row
        out[tuple(key)] = GroupStats(count=count, median=median, total=total)
    return out


def market_sale_rows(f: Filters):
    t, ps, p = Transaction.__table__, ParcelSummary.__table__, Parcel.__table__
    ppsf = sa.case((ps.c.living_sqft > 0, t.c.sale_price * 1.0 / ps.c.living_sqft))
    return (
        sa.select(
            t.c.parcel_id, p.c.neighborhood,
            sa.cast(sa.extract("year", t.c.sale_date), sa.Integer).label("year"),
            t.c.sale_price, ppsf.label("ppsf"),
        )
        .select_from(t)
        .join(p, p.c.parcel_id == t.c.parcel_id)
        .outerjoin(ps, ps.c.parcel_id == t.c.parcel_id)
        .where(market_sale_criteria(), plausible_price_criteria(), single_parcel_criteria(),
               *sale_conditions(f, t, ps))
        .subquery()
    )
```

(Import `Parcel` from `db.models` in `market.py`.)

Create `src/services/analytics/neighborhoods.py`:

```python
"""Neighborhood list, multi-neighborhood trends and single-neighborhood report."""
from __future__ import annotations

import sqlalchemy as sa
from pydantic import BaseModel

from api.errors import not_found
from api.filters import Filters
from db.county_models import Neighborhood, NeighborhoodSummary, TaxDistrict
from services.analytics.market import market_sale_rows, medians_by_group
from services.analytics.parcels import DistrictRef
from services.analytics.sales import SaleRow, list_sales

_STATIC = ("parcel_count", "owner_occupied_share", "median_year_built", "median_value_change_pct")


class NeighborhoodRow(BaseModel):
    code: str
    name: str | None
    display_name: str | None
    tax_district: str | None
    sales: int
    median_price: float | None
    median_price_per_sqft: float | None
    total_volume: float | None
    parcel_count: int | None = None
    owner_occupied_share: float | None = None
    median_year_built: float | None = None
    median_value_change_pct: float | None = None


class TrendRow(BaseModel):
    neighborhood: str
    name: str | None
    year: int
    sales: int
    median_price: float | None


class YearStats(BaseModel):
    year: int
    sales: int
    median_price: float | None
    median_price_per_sqft: float | None


class NeighborhoodReport(BaseModel):
    code: str
    name: str
    display_name: str
    tax_district: DistrictRef | None
    summary: dict | None
    trend: list[YearStats]
    recent_sales: list[SaleRow]


async def _names(session) -> dict[str, dict]:
    n, ns = Neighborhood.__table__, NeighborhoodSummary.__table__
    rows = (await session.execute(
        sa.select(n.c.code, n.c.name, n.c.display_name, n.c.tax_district,
                  *[ns.c[c] for c in _STATIC]).select_from(n)
        .outerjoin(ns, ns.c.code == n.c.code)
    )).mappings().all()
    return {r["code"]: dict(r) for r in rows}


async def list_neighborhoods(session, f: Filters) -> list[NeighborhoodRow]:
    rows = market_sale_rows(f)
    prices = await medians_by_group(session, rows, ["neighborhood"], "sale_price")
    ppsf = await medians_by_group(session, rows, ["neighborhood"], "ppsf")
    names = await _names(session)
    out = []
    for (code,), stats in prices.items():
        if code is None:
            continue
        meta = names.get(code, {})
        out.append(NeighborhoodRow(
            code=code, name=meta.get("name"), display_name=meta.get("display_name"),
            tax_district=meta.get("tax_district"), sales=stats.count,
            median_price=stats.median, total_volume=stats.total,
            median_price_per_sqft=ppsf.get((code,)).median if (code,) in ppsf else None,
            **{k: meta.get(k) for k in _STATIC},
        ))
    return sorted(out, key=lambda r: (-r.sales, r.code))


async def neighborhood_trends(session, f: Filters, codes: list[str] | None, limit: int,
                              min_sales: int) -> list[TrendRow]:
    rows = market_sale_rows(f)
    stats = await medians_by_group(session, rows, ["neighborhood", "year"], "sale_price")
    if not codes:
        totals: dict[str, int] = {}
        for (code, _year), s in stats.items():
            if code:
                totals[code] = totals.get(code, 0) + s.count
        codes = [c for c, _ in sorted(totals.items(), key=lambda kv: -kv[1])[:limit]]
    names = await _names(session)
    wanted = set(codes)
    return sorted(
        (TrendRow(neighborhood=code, name=names.get(code, {}).get("name"), year=year,
                  sales=s.count, median_price=s.median)
         for (code, year), s in stats.items() if code in wanted and s.count >= min_sales),
        key=lambda r: (r.neighborhood, r.year),
    )


async def neighborhood_report(session, code: str) -> NeighborhoodReport:
    names = await _names(session)
    if code not in names:
        raise not_found(f"Neighborhood {code}")
    meta = names[code]
    f = Filters(neighborhood=code)
    rows = market_sale_rows(f)
    prices = await medians_by_group(session, rows, ["year"], "sale_price")
    ppsf = await medians_by_group(session, rows, ["year"], "ppsf")
    trend = [
        YearStats(year=year, sales=s.count, median_price=s.median,
                  median_price_per_sqft=ppsf[(year,)].median if (year,) in ppsf else None)
        for (year,), s in sorted(prices.items())
    ]
    district = None
    if meta["tax_district"]:
        districts = TaxDistrict.__table__
        row = (await session.execute(
            sa.select(districts).where(districts.c.code == meta["tax_district"])
        )).mappings().first()
        if row:
            district = DistrictRef(code=row["code"], name=row["name"],
                                   school_district=row["school_district"])
    summaries = NeighborhoodSummary.__table__
    summary = (await session.execute(
        sa.select(summaries).where(summaries.c.code == code)
    )).mappings().first()
    recent = await list_sales(session, f, sort="sale_date", order="desc", page=1, page_size=10,
                              market_only=True)
    return NeighborhoodReport(
        code=code, name=meta["name"], display_name=meta["display_name"], tax_district=district,
        summary=dict(summary) if summary else None, trend=trend, recent_sales=recent.rows,
    )
```

Create `src/api/routers/neighborhoods.py` (the `/trends` route must be declared before `/{code}`):

```python
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from api.cache import cache, data_version
from api.filters import Filters, get_filters
from db.engine import get_session
from services.analytics.neighborhoods import (
    NeighborhoodReport,
    NeighborhoodRow,
    TrendRow,
    list_neighborhoods,
    neighborhood_report,
    neighborhood_trends,
)

router = APIRouter(prefix="/neighborhoods", tags=["neighborhoods"])


class NeighborhoodList(BaseModel):
    applied_filters: list[str]
    rows: list[NeighborhoodRow]


class TrendList(BaseModel):
    applied_filters: list[str]
    rows: list[TrendRow]


@router.get("", response_model=NeighborhoodList)
async def neighborhoods(f: Filters = Depends(get_filters),
                        session: AsyncSession = Depends(get_session)):
    version = await data_version(session)
    rows = await cache.get_or_compute(("neighborhoods", f.model_dump_json()), version,
                                      lambda: list_neighborhoods(session, f))
    return NeighborhoodList(applied_filters=f.active(), rows=rows)


@router.get("/trends", response_model=TrendList)
async def trends(f: Filters = Depends(get_filters),
                 codes: list[str] | None = Query(None),
                 limit: int = Query(10, ge=1, le=50),
                 min_sales: int = Query(5, ge=1),
                 session: AsyncSession = Depends(get_session)):
    rows = await neighborhood_trends(session, f, codes, limit, min_sales)
    return TrendList(applied_filters=f.active(), rows=rows)


@router.get("/{code}", response_model=NeighborhoodReport)
async def report(code: str, session: AsyncSession = Depends(get_session)):
    return await neighborhood_report(session, code)
```

Register it in `src/api/__init__.py`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/api/test_neighborhoods.py -v`
Expected: all 5 tests PASS. In `test_report`, the 2023 sale's price per square foot uses the dwelling's current living area (2,464 sq ft), which is how `ppsf` is defined everywhere.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/services/analytics src/api tests/api/test_neighborhoods.py
git commit -m "Add neighborhood list, trends and report endpoints"
```

---

### Task 22: Owners and investors

**Files:**
- Create: `src/services/analytics/owners.py`, `src/api/routers/owners.py`, `src/api/routers/investors.py`
- Modify: `src/main.py` (`get_owner_profile`, `get_acquisition_waves`, `get_net_sellers`, `get_absentee_owners` delegate), `src/api/__init__.py`
- Test: `tests/test_api_characterization.py`, `tests/api/test_owners.py`

**Interfaces:**
- Produces:
  - Moved (bodies unchanged except `session.exec` becomes `session.execute` where the result is used with `.mappings()` or `.all()` on core statements, and bare SQLAlchemy names gain the `sa.` prefix): `owner_profile(session, owner_name: str) -> OwnerProfile`, `acquisition_waves(session, *, window_days=90, min_acquisitions=5, date_from=None, date_to=None, limit=50) -> list[AcquisitionWave]`, `net_sellers(session, *, min_net_sells=3, date_from=None, date_to=None, limit=50) -> list[NetSellerStats]`, `absentee_owners(session, *, parcel_class=None, limit=50) -> list[OwnerStats]`.
  - New: `top_owners(session, f: Filters, *, order_by: Literal["parcels","acres","value"], limit: int) -> list[OwnerPortfolio]` over current owners in `parcel_summary`; `OwnerPortfolio {owner_name, parcel_count, total_acres, total_market_value}`.
  - New: `owner_detail(session, name: str) -> OwnerDetail {owner_name, profile: OwnerProfile, holdings: [Holding], totals: {parcel_count, total_market_value, total_acres}}`; `Holding {parcel_id, address, parcel_class, neighborhood, living_sqft, year_built, market_value, last_sale_date, last_sale_price, occupancy, latitude, longitude}`; 404 when the name has no holdings and no recorded purchases or sales.
  - Routes: `GET /v2/owners/top?<filters>&order_by=parcels&limit=15` (`{applied_filters, rows}`, honors `parcel_conditions` filters), `GET /v2/owners/{name}`, `GET /v2/investors/acquisition-waves`, `GET /v2/investors/net-sellers` (both honor `date_from`, `date_to`), `GET /v2/investors/absentee-owners` (honors the first of `classes` only if exactly one class is given; otherwise reports it as not applied). Each list returns `{applied_filters, rows}`.

- [ ] **Step 1: Pin the untested old endpoints with characterization tests**

`/analytics/net-sellers` and `/analytics/absentee-owners` have no tests. Before moving them, create `tests/test_api_characterization.py`:

```python
import datetime as dt

from db.models import Parcel, ParcelClass, Transaction


def txn(pid, day, price, buyer, seller, mailing="1 LOCAL ST, DAYTON OH 45402"):
    return Transaction(
        parcel_id=pid, sale_date=day, sale_price=price, old_owner=seller, new_owner=buyer,
        parcel_location=f"{pid} ST", mailing_name=buyer, mailing_address=mailing,
        parcel_class=ParcelClass.R, acres=0.1, taxable_land=0, taxable_building=0,
        taxable_total=0, sale_validity="VALID SALE",
    )


async def seed(session):
    for i in range(6):
        session.add(Parcel(parcel_id=f"P{i}", parcel_location=f"P{i} ST",
                           parcel_class=ParcelClass.R, acres=0.1))
    # DUMPER LLC buys 1 and sells 5: a net seller.
    session.add(txn("P0", dt.date(2020, 1, 1), 100_000, "DUMPER LLC", "A"))
    for i in range(1, 6):
        session.add(txn(f"P{i}", dt.date(2021, i, 1), 100_000, f"BUYER {i}", "DUMPER LLC"))
    # FAR AWAY LLC mails out of state.
    session.add(txn("P0", dt.date(2022, 1, 1), 150_000, "FAR AWAY LLC", "DUMPER LLC",
                    mailing="PO BOX 1, AUSTIN TX 78701"))
    await session.commit()


async def test_net_sellers_characterization(client, session):
    await seed(session)
    r = await client.get("/analytics/net-sellers")
    assert r.status_code == 200
    rows = r.json()
    dumper = next(row for row in rows if row["owner_name"] == "DUMPER LLC")
    assert (dumper["buy_count"], dumper["sell_count"]) == (1, 6)


async def test_absentee_owners_characterization(client, session):
    await seed(session)
    r = await client.get("/analytics/absentee-owners")
    assert r.status_code == 200
    assert [row["owner_name"] for row in r.json()] == ["FAR AWAY LLC"]
```

Run: `uv run pytest tests/test_api_characterization.py -v`
Expected: PASS against the current, unmoved code. If an assertion does not match what the old endpoint returns, the old endpoint's behavior is the truth: correct the test's expectation (not the endpoint) so it pins today's behavior, then continue.

- [ ] **Step 2: Write the failing /v2 tests**

Create `tests/api/test_owners.py`:

```python
import datetime as dt

from sqlmodel.ext.asyncio.session import AsyncSession

from tests.api.conftest import sale
from db.models import Parcel, ParcelClass


async def get(api, path, **params):
    r = await api.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


async def test_top_owners_are_current_owners(api):
    body = await get(api, "/v2/owners/top", order_by="value")
    mullenax = next(r for r in body["rows"] if r["owner_name"] == "MULLENAX SAMANTHA MARIE")
    assert (mullenax["parcel_count"], mullenax["total_market_value"]) == (1, 267_560)


async def test_top_owners_honor_parcel_filters(api):
    body = await get(api, "/v2/owners/top", neighborhood="48150000", price_min=1)
    assert body["applied_filters"] == ["price_min", "neighborhood"]


async def test_owner_detail(api):
    body = await get(api, "/v2/owners/MULLENAX SAMANTHA MARIE")
    assert [h["parcel_id"] for h in body["holdings"]] == ["A01 00101 0001"]
    assert body["totals"]["parcel_count"] == 1
    assert body["profile"]["total_buys"] == 1
    assert body["profile"]["total_sells"] == 1


async def test_past_owner_without_holdings_still_resolves(api):
    body = await get(api, "/v2/owners/FUND LLC")
    assert body["holdings"] == []
    assert body["profile"]["total_buys"] == 2


async def test_unknown_owner_is_404(api):
    r = await api.get("/v2/owners/NOBODY AT ALL")
    assert r.status_code == 404


async def test_acquisition_wave(api, county_db):
    async with AsyncSession(county_db) as s:
        for i in range(5):
            s.add(Parcel(parcel_id=f"W{i}", parcel_location=f"W{i} ST",
                         parcel_class=ParcelClass.R, acres=0.1))
            s.add(sale(f"W{i}", dt.date(2025, 1, 1) + dt.timedelta(days=10 * i), 80_000 + i,
                       buyer="WAVE LLC", seller=f"S{i}"))
        await s.commit()
    body = await get(api, "/v2/investors/acquisition-waves", date_from="2024-01-01")
    assert body["applied_filters"] == ["date_from"]
    assert [r["owner_name"] for r in body["rows"]] == ["WAVE LLC"]
    assert body["rows"][0]["acquisition_count"] == 5


async def test_net_sellers_and_absentee_shapes(api):
    for path in ("/v2/investors/net-sellers", "/v2/investors/absentee-owners"):
        body = await get(api, path)
        assert set(body) == {"applied_filters", "rows"}
```

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run pytest tests/api/test_owners.py -v`
Expected: FAIL (404s).

- [ ] **Step 4: Move the old bodies and add the new queries**

1. Create `src/services/analytics/owners.py`. Move into it, with the keyword-only signatures from the Interfaces list: the body of `get_owner_profile` (together with the `_MAX_OWNERS_PER_ADDRESS` constant above it), `get_acquisition_waves`, `get_net_sellers` and `get_absentee_owners`. Rename the date parameters inside the moved bodies from `sale_date__gte`/`sale_date__lte` to `date_from`/`date_to`. Import what the bodies use (`merge_owner_rows`, `days_between`, `date_add_days`, `market_sale_criteria`, the models).
2. Replace each old route body in `src/main.py` with a delegation that keeps the route's signature, for example:

```python
    return await acquisition_waves(
        session, window_days=window_days, min_acquisitions=min_acquisitions,
        date_from=sale_date__gte, date_to=sale_date__lte, limit=limit,
    )
```

3. Add the new queries to `src/services/analytics/owners.py`:

```python
class OwnerPortfolio(BaseModel):
    owner_name: str
    parcel_count: int
    total_acres: float
    total_market_value: float


class Holding(BaseModel):
    parcel_id: str
    address: str | None
    parcel_class: str
    neighborhood: str | None
    living_sqft: int | None
    year_built: int | None
    market_value: float | None
    last_sale_date: date | None
    last_sale_price: float | None
    occupancy: str
    latitude: float | None
    longitude: float | None


class OwnerDetail(BaseModel):
    owner_name: str
    profile: OwnerProfile
    holdings: list[Holding]
    totals: dict[str, float]


async def top_owners(session, f: Filters, *, order_by: str, limit: int) -> list[OwnerPortfolio]:
    ps, p = ParcelSummary.__table__, Parcel.__table__
    count = sa.func.count().label("parcel_count")
    acres = sa.func.coalesce(sa.func.sum(p.c.acres), 0).label("total_acres")
    value = sa.func.coalesce(sa.func.sum(ps.c.market_value), 0).label("total_market_value")
    sort = {"parcels": count, "acres": acres, "value": value}[order_by]
    rows = (await session.execute(
        sa.select(ps.c.owner_name, count, acres, value)
        .select_from(ps).join(p, p.c.parcel_id == ps.c.parcel_id)
        .where(ps.c.owner_name.isnot(None), ps.c.is_active.is_(True), *parcel_conditions(f, ps))
        .group_by(ps.c.owner_name)
        .order_by(sort.desc(), ps.c.owner_name)
        .limit(limit)
    )).mappings().all()
    return [OwnerPortfolio(**r) for r in rows]


async def owner_detail(session, name: str) -> OwnerDetail:
    ps, p = ParcelSummary.__table__, Parcel.__table__
    rows = (await session.execute(
        sa.select(ps.c.parcel_id, ps.c.address, ps.c.parcel_class, ps.c.neighborhood,
                  ps.c.living_sqft, ps.c.year_built, ps.c.market_value, ps.c.last_sale_date,
                  ps.c.last_sale_price, ps.c.occupancy, ps.c.latitude, ps.c.longitude,
                  p.c.acres)
        .select_from(ps).join(p, p.c.parcel_id == ps.c.parcel_id)
        .where(ps.c.owner_name == name, ps.c.is_active.is_(True))
        .order_by(ps.c.address)
    )).mappings().all()
    profile = await owner_profile(session, name)
    if not rows and not profile.total_buys and not profile.total_sells:
        raise not_found(f"Owner {name}")
    holdings = [Holding(**{k: r[k] for k in Holding.model_fields}) for r in rows]
    return OwnerDetail(
        owner_name=name, profile=profile, holdings=holdings,
        totals={
            "parcel_count": len(rows),
            "total_market_value": sum(r["market_value"] or 0 for r in rows),
            "total_acres": sum(r["acres"] or 0 for r in rows),
        },
    )
```

4. Create `src/api/routers/owners.py` and `src/api/routers/investors.py`:

```python
# src/api/routers/owners.py
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from api.filters import Filters, get_filters, honored
from db.engine import get_session
from services.analytics.owners import OwnerDetail, OwnerPortfolio, owner_detail, top_owners

router = APIRouter(prefix="/owners", tags=["owners"])
PARCEL_FILTERS = ("date_from", "date_to", "price_min", "price_max", "classes", "beds_min",
                  "sqft_min", "sqft_max", "year_built_min", "year_built_max", "occupancy",
                  "distress_min", "neighborhood")


class OwnerList(BaseModel):
    applied_filters: list[str]
    rows: list[OwnerPortfolio]


@router.get("/top", response_model=OwnerList)
async def top(f: Filters = Depends(get_filters),
              order_by: Literal["parcels", "acres", "value"] = "parcels",
              limit: int = Query(15, ge=1, le=100),
              session: AsyncSession = Depends(get_session)):
    rows = await top_owners(session, f, order_by=order_by, limit=limit)
    return OwnerList(applied_filters=honored(f, PARCEL_FILTERS), rows=rows)


@router.get("/{name}", response_model=OwnerDetail)
async def detail(name: str, session: AsyncSession = Depends(get_session)):
    return await owner_detail(session, name)
```

```python
# src/api/routers/investors.py
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from api.filters import Filters, get_filters, honored
from db.engine import get_session
from db.models import AcquisitionWave, NetSellerStats, OwnerStats, ParcelClass
from services.analytics.owners import absentee_owners, acquisition_waves, net_sellers

router = APIRouter(prefix="/investors", tags=["investors"])


class Waves(BaseModel):
    applied_filters: list[str]
    rows: list[AcquisitionWave]


class NetSellers(BaseModel):
    applied_filters: list[str]
    rows: list[NetSellerStats]


class Absentee(BaseModel):
    applied_filters: list[str]
    rows: list[OwnerStats]


@router.get("/acquisition-waves", response_model=Waves)
async def waves(f: Filters = Depends(get_filters), window_days: int = Query(90, ge=7, le=730),
                min_acquisitions: int = Query(5, ge=2), limit: int = Query(50, ge=1, le=500),
                session: AsyncSession = Depends(get_session)):
    rows = await acquisition_waves(session, window_days=window_days,
                                   min_acquisitions=min_acquisitions, date_from=f.date_from,
                                   date_to=f.date_to, limit=limit)
    return Waves(applied_filters=honored(f, ["date_from", "date_to"]), rows=rows)


@router.get("/net-sellers", response_model=NetSellers)
async def sellers(f: Filters = Depends(get_filters), min_net_sells: int = Query(3, ge=1),
                  limit: int = Query(50, ge=1, le=500),
                  session: AsyncSession = Depends(get_session)):
    rows = await net_sellers(session, min_net_sells=min_net_sells, date_from=f.date_from,
                             date_to=f.date_to, limit=limit)
    return NetSellers(applied_filters=honored(f, ["date_from", "date_to"]), rows=rows)


@router.get("/absentee-owners", response_model=Absentee)
async def absentee(f: Filters = Depends(get_filters), limit: int = Query(50, ge=1, le=500),
                   session: AsyncSession = Depends(get_session)):
    single = f.classes[0] if f.classes and len(f.classes) == 1 else None
    rows = await absentee_owners(session, parcel_class=ParcelClass[single] if single else None,
                                 limit=limit)
    return Absentee(applied_filters=["classes"] if single else [], rows=rows)
```

Register both routers in `src/api/__init__.py`.

- [ ] **Step 5: Run the tests, including the old ones**

Run: `uv run pytest tests/api/test_owners.py tests/test_api_characterization.py tests/test_api.py -v`
Expected: all PASS. The `/analytics/owner-profile` and `/analytics/acquisition-waves` tests plus the new characterization tests prove the moves kept behavior. In `test_owner_detail`, MULLENAX bought once (2023) and sold once (the 2025 deal), so `total_buys == total_sells == 1`; if `owner_profile` counts the deal differently, the moved code's behavior wins: adjust the expectation and note why in the test.

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check src tests
git add src/services/analytics/owners.py src/api src/main.py tests/test_api_characterization.py tests/api/test_owners.py
git commit -m "Add owner and investor endpoints; share owner queries with the old routes"
```

---

### Task 23: Distress parity: distressed sales and stale parcels

**Files:**
- Create: `src/services/analytics/distress.py`, `src/api/routers/distress.py`
- Modify: `src/main.py` (`get_distressed_sales`, `get_stale_parcels` delegate), `src/api/__init__.py`
- Test: `tests/api/test_distress.py`

**Interfaces:**
- Produces:
  - Moved: `distressed_sales(session, *, max_ratio=0.7, min_assessed=10000, date_from=None, date_to=None, classes=None, limit=50) -> list[dict]` (adds `plausible_price_criteria()` so nominal transfers no longer appear), `stale_parcels(session, *, min_years=10.0, classes=None, limit=50) -> list[dict]`.
  - `GET /v2/distress/distressed-sales?<filters>&max_ratio=0.7&limit=50` and `GET /v2/distress/stale-parcels?<filters>&min_years=10&limit=50`, each `{applied_filters, rows}`; the first honors `date_from`, `date_to`, `classes`; the second honors `classes`.

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_distress.py`:

```python
import datetime as dt

from sqlmodel.ext.asyncio.session import AsyncSession

from tests.api.conftest import sale
from db.models import Parcel, ParcelClass


async def seed_distress(engine):
    async with AsyncSession(engine) as s:
        for pid in ("D1", "D2"):
            s.add(Parcel(parcel_id=pid, parcel_location=f"{pid} ST", parcel_class=ParcelClass.R,
                         acres=0.1))
        cheap = sale("D1", dt.date(2025, 5, 1), 50_000, buyer="BARGAIN LLC")
        cheap.assessed_total = 200_000
        nominal = sale("D2", dt.date(2025, 5, 2), 1_000, buyer="HEIR")
        nominal.assessed_total = 4_125_980
        s.add_all([cheap, nominal])
        await s.commit()


async def test_distressed_sales_skip_nominal_transfers(api, county_db):
    await seed_distress(county_db)
    body = (await api.get("/v2/distress/distressed-sales")).json()
    assert [r["parcel_id"] for r in body["rows"]] == ["D1"]
    assert body["rows"][0]["assessed_ratio"] == 0.25


async def test_distressed_sales_honor_dates(api, county_db):
    await seed_distress(county_db)
    body = (await api.get("/v2/distress/distressed-sales",
                          params={"date_from": "2025-06-01"})).json()
    assert body == {"applied_filters": ["date_from"], "rows": []}


async def test_stale_parcels(api):
    body = (await api.get("/v2/distress/stale-parcels")).json()
    assert "Z99 99999 9999" in [r["parcel_id"] for r in body["rows"]]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/api/test_distress.py -v`
Expected: FAIL (404s).

- [ ] **Step 3: Move the bodies and add the routes**

1. Create `src/services/analytics/distress.py`; move the bodies of `get_distressed_sales` and `get_stale_parcels` from `src/main.py` into `distressed_sales` and `stale_parcels` with the keyword-only signatures above. In `distressed_sales`, change `.where(market_sale_criteria(include_distress=True))` to `.where(market_sale_criteria(include_distress=True), plausible_price_criteria())`, rename the date parameters to `date_from`/`date_to`, and replace the single-class filter with `if classes: query = query.where(Transaction.parcel_class.in_(classes))`. In `stale_parcels`, replace its single-class filter the same way. Return `[dict(r) for r in result.mappings().all()]`.
2. Make the old routes delegate (`classes=[parcel_class] if parcel_class else None`).
3. Create `src/api/routers/distress.py`:

```python
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from api.filters import Filters, get_filters, honored
from db.engine import get_session
from db.models import DistressedSale, ParcelClass, StaleParcel
from services.analytics.distress import distressed_sales, stale_parcels

router = APIRouter(prefix="/distress", tags=["distress"])


class DistressedList(BaseModel):
    applied_filters: list[str]
    rows: list[DistressedSale]


class StaleList(BaseModel):
    applied_filters: list[str]
    rows: list[StaleParcel]


def _classes(f: Filters) -> list[ParcelClass] | None:
    return [ParcelClass[c] for c in f.classes] if f.classes else None


@router.get("/distressed-sales", response_model=DistressedList)
async def distressed(f: Filters = Depends(get_filters),
                     max_ratio: float = Query(0.7, gt=0, le=1),
                     limit: int = Query(50, ge=1, le=500),
                     session: AsyncSession = Depends(get_session)):
    rows = await distressed_sales(session, max_ratio=max_ratio, date_from=f.date_from,
                                  date_to=f.date_to, classes=_classes(f), limit=limit)
    return DistressedList(applied_filters=honored(f, ["date_from", "date_to", "classes"]),
                          rows=rows)


@router.get("/stale-parcels", response_model=StaleList)
async def stale(f: Filters = Depends(get_filters),
                min_years: float = Query(10.0, ge=1),
                limit: int = Query(50, ge=1, le=500),
                session: AsyncSession = Depends(get_session)):
    rows = await stale_parcels(session, min_years=min_years, classes=_classes(f), limit=limit)
    return StaleList(applied_filters=honored(f, ["classes"]), rows=rows)
```

Register it in `src/api/__init__.py`.

- [ ] **Step 4: Run the tests, including the old ones**

Run: `uv run pytest tests/api/test_distress.py tests/test_api.py -v`
Expected: all PASS, including the existing `/analytics/distressed` and `/analytics/stale-parcels` tests.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check src tests
git add src/services/analytics/distress.py src/api src/main.py tests/api/test_distress.py
git commit -m "Add distress endpoints; ignore nominal transfers in distressed sales"
```

---

### Task 24: OpenAPI export and real-data verification

**Files:**
- Create: `scripts/export_openapi.py`, `scripts/verify_real_data.py`
- Create: `frontend/openapi.json` (generated)
- Modify: `Readme.md`
- Test: `tests/test_export_openapi.py`

**Interfaces:**
- Produces:
  - `scripts/export_openapi.py [OUT]` writes the app's OpenAPI document (default `frontend/openapi.json`). Plan 1B generates TypeScript types from it, and CI (plan 1B) fails when it is stale.
  - `scripts/verify_real_data.py` runs the full ingest against a copy of the real database and the real county files, prints a coverage and timing report, and exits non-zero when a threshold fails.

- [ ] **Step 1: Write the failing test for the export**

Create `tests/test_export_openapi.py`:

```python
import json
import subprocess
import sys


def test_export_openapi(tmp_path):
    out = tmp_path / "openapi.json"
    subprocess.run([sys.executable, "scripts/export_openapi.py", str(out)], check=True)
    doc = json.loads(out.read_text())
    for path in ("/v2/search", "/v2/parcels/{parcel_id}", "/v2/sales", "/v2/market/summary",
                 "/v2/meta", "/v2/neighborhoods", "/v2/owners/top", "/v2/distress/stale-parcels"):
        assert path in doc["paths"], path
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_export_openapi.py -v`
Expected: FAIL (`scripts/export_openapi.py` does not exist).

- [ ] **Step 3: Implement the export**

Create `scripts/export_openapi.py`:

```python
"""Write the API's OpenAPI document (for frontend type generation).

Usage: uv run python scripts/export_openapi.py [OUT]   (default: frontend/openapi.json)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from main import app  # noqa: E402


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "frontend/openapi.json")
    out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
```

Run: `uv run pytest tests/test_export_openapi.py -v && uv run python scripts/export_openapi.py`
Expected: PASS, and `frontend/openapi.json` is written.

- [ ] **Step 4: Write the real-data verification script**

Create `scripts/verify_real_data.py`:

```python
"""End-to-end check of the data platform against real county files.

Usage:
    uv run python scripts/verify_real_data.py [--db database.db] [--county-dir /tmp/county]

Copies the local database (so the real one is untouched), downloads the
newest CAMA, tax roll and neighborhood files into --county-dir (reusing any
already there), runs every ingest step and the derived rebuild, then prints
coverage and timing, and calls the main /v2 endpoints through the ASGI app.
Exits 1 when a threshold fails.
"""
import argparse
import asyncio
import gzip
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

THRESHOLDS = {
    "active parcels": 250_000,
    "dwellings": 180_000,
    "parcel_tax rows": 250_000,
    "coordinates (% of active)": 95.0,
    "sales with a parcel neighborhood (%)": 97.0,
    "map binary gzip MB (max)": 8.0,
    "endpoint p95 ms (max)": 300.0,
}


async def main(db: Path, county_dir: Path) -> int:
    work = Path(tempfile.mkdtemp())
    copy = work / "verify.db"
    shutil.copy(db, copy)
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{copy}"
    os.environ["DATA_DIR"] = str(work)

    import sqlalchemy as sa
    from httpx import ASGITransport, AsyncClient

    from county import sources
    from db.engine import engine, init_db
    from db.maintenance import ensure_schema
    from derived import mapbinary
    from derived.summary import rebuild_derived
    from ingest.cama_ingest import ingest_cama
    from ingest.neighborhood_ingest import ingest_neighborhood_names
    from ingest.taxroll_ingest import ingest_taxroll
    from main import app

    mapbinary.DERIVED_DIR = work / "derived"
    await init_db()
    await ensure_schema()

    timings: dict[str, float] = {}
    async with sources.county_client() as client:
        paths = {}
        for dataset in ("cama", "taxroll", "neighborhoods"):
            name = await sources.latest_file(dataset, client)
            paths[dataset] = await sources.download(dataset, name, county_dir, client)
            print(f"{dataset}: {paths[dataset]}")
    for label, step in (
        ("cama", lambda: ingest_cama(paths["cama"])),
        ("neighborhoods", lambda: ingest_neighborhood_names(paths["neighborhoods"])),
        ("taxroll", lambda: ingest_taxroll(paths["taxroll"])),
        ("derived", rebuild_derived),
    ):
        start = time.perf_counter()
        await step()
        timings[label] = time.perf_counter() - start
        print(f"{label}: {timings[label]:.1f}s")

    async with engine.connect() as conn:
        def scalar(sql):
            return conn.execute(sa.text(sql))

        active = (await scalar("SELECT count(*) FROM parcel WHERE is_active")).scalar_one()
        located = (await scalar(
            "SELECT count(*) FROM parcel WHERE is_active AND latitude IS NOT NULL "
            "AND latitude != 0")).scalar_one()
        dwellings = (await scalar("SELECT count(*) FROM dwelling")).scalar_one()
        taxes = (await scalar("SELECT count(*) FROM parcel_tax")).scalar_one()
        with_hood = (await scalar(
            'SELECT count(*) FROM "transaction" t JOIN parcel p ON p.parcel_id = t.parcel_id '
            "WHERE p.neighborhood IS NOT NULL")).scalar_one()
        sales = (await scalar('SELECT count(*) FROM "transaction"')).scalar_one()

    _, path = mapbinary.latest_map_binary()
    gz_mb = len(gzip.compress(path.read_bytes())) / 1e6

    latencies: list[float] = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://v") as client:
        calls = ["/v2/meta", "/v2/market/summary", "/v2/market/trends?granularity=month",
                 "/v2/sales?page_size=50", "/v2/sales?sort=price_per_sqft&neighborhood=48150000",
                 "/v2/search?q=main", "/v2/search?q=smith", "/v2/neighborhoods",
                 "/v2/owners/top", "/v2/parcels/A01 00101 0001",
                 "/v2/parcels/A01 00101 0001/comps", "/v2/distress/distressed-sales"]
        for _ in range(3):  # the first pass warms caches
            for url in calls:
                start = time.perf_counter()
                r = await client.get(url)
                latencies.append((time.perf_counter() - start) * 1000)
                if r.status_code != 200:
                    print(f"FAIL {url}: {r.status_code} {r.text[:200]}")
                    return 1
    p95 = statistics.quantiles(latencies[len(calls):], n=20)[-1]

    results = {
        "active parcels": active,
        "dwellings": dwellings,
        "parcel_tax rows": taxes,
        "coordinates (% of active)": located / active * 100,
        "sales with a parcel neighborhood (%)": with_hood / sales * 100,
        "map binary gzip MB (max)": gz_mb,
        "endpoint p95 ms (max)": p95,
    }
    failed = False
    for name, value in results.items():
        limit = THRESHOLDS[name]
        ok = value <= limit if "(max)" in name else value >= limit
        failed |= not ok
        print(f"{'ok  ' if ok else 'FAIL'} {name}: {value:,.1f} (threshold {limit:,})")
    print(f"Work dir kept for inspection: {work}")
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("database.db"))
    parser.add_argument("--county-dir", type=Path, default=Path("/tmp/county"))
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.db, args.county_dir)))
```

- [ ] **Step 5: Run it against the real data**

Run: `uv run python scripts/verify_real_data.py`
Expected: every line prints `ok`, and the script exits 0. Expected magnitudes from the profiling reports: about 259k active parcels, about 189k dwellings, about 254k tax rows, coordinates on about 97% of active parcels, and a map binary of a few MB gzipped.

If a threshold fails, treat it as a bug to fix in this task, not a threshold to relax. Typical causes: a layout offset (check `reader.bad` counts, which `check()` logs), a slow query missing an index (add the index to the model and a repair in `db/maintenance.py`), or the neighborhood join (confirm `parcel.neighborhood` is filled for parcels that exist only in sales history). Record the final report in the commit message.

- [ ] **Step 6: Document the new data and API**

In `Readme.md`:
- Add `COUNTY_INGEST` (default `true`) to the configuration table: "Whether the population run also ingests CAMA, the tax roll and neighborhood names."
- Replace the "Automated population" list with the new order: yearly sales, weekly sales, CAMA (monthly), neighborhood names (monthly), tax roll (weekly), geocoding (only parcels the county does not locate), derived rebuild (`parcel_summary`, `neighborhood_summary`, map binary).
- Add a short "API" section: the frontend uses `/v2` (see `frontend/openapi.json`); `/analytics` and the other unversioned routes remain until the new frontend ships.
- Link `docs/data-sources/README.md` under a "Data sources" heading.
- One sentence per line, per the repo's Markdown convention.

- [ ] **Step 7: Full suite, lint, commit**

```bash
uv run pytest -q
uv run ruff check src tests scripts
git add scripts frontend/openapi.json Readme.md tests/test_export_openapi.py
git commit -m "Export the OpenAPI document and verify the data platform against real county files"
```

Expected: every test passes on SQLite; CI runs the same suite on Postgres.
