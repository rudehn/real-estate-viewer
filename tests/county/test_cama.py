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
