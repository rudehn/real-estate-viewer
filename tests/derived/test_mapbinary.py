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
