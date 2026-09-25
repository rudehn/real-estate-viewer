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
