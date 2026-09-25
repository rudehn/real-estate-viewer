import datetime as dt
import zipfile
from pathlib import Path

import pytest

from county.taxroll import TaxRollReader, annual_bill, snapshot_date

FIXTURE = Path(__file__).parent.parent / "fixtures" / "county" / "TAXROLL_20260923.zip"


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


def test_missing_column_is_rejected_with_its_name(tmp_path):
    from county.fixedwidth import TooManyBadRows

    with zipfile.ZipFile(FIXTURE) as zf:
        (entry,) = zf.namelist()
        lines = zf.read(entry).split(b'\r\n')
    # Rename FRCLSR to FRCLSR2 in header
    header = lines[0].replace(b'FRCLSR', b'FRCLSR2')
    broken = header + b'\r\n' + b'\r\n'.join(lines[1:])
    path = tmp_path / "TAXROLL_20260923.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(entry, broken)
    reader = TaxRollReader()
    with pytest.raises(TooManyBadRows) as exc_info:
        list(reader.rows(path))
    assert "FRCLSR" in str(exc_info.value)


def test_missing_bill_component_column_is_rejected(tmp_path):
    from county.fixedwidth import TooManyBadRows

    with zipfile.ZipFile(FIXTURE) as zf:
        (entry,) = zf.namelist()
        lines = zf.read(entry).split(b'\r\n')
    # Rename HLF1ADJ to HLF1ADJ2 in header
    header = lines[0].replace(b'HLF1ADJ', b'HLF1ADJ2')
    broken = header + b'\r\n' + b'\r\n'.join(lines[1:])
    path = tmp_path / "TAXROLL_20260923.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(entry, broken)
    reader = TaxRollReader()
    with pytest.raises(TooManyBadRows) as exc_info:
        list(reader.rows(path))
    assert "HLF1ADJ" in str(exc_info.value)
