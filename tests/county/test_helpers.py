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
    # Regression: straight and curly apostrophes must normalize identically.
    assert normalize_search("D'ANGELO") == normalize_search("D'ANGELO") == "DANGELO"
