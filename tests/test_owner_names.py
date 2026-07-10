"""Unit tests for owner-name normalization and merge logic."""
from services.owner_names import merge_owner_rows, normalize_owner


def test_city_of_rotation():
    assert normalize_owner("DAYTON CITY OF") == normalize_owner("CITY OF DAYTON")
    assert normalize_owner("OHIO STATE OF") == normalize_owner("STATE OF OHIO")


def test_hud_variants_collide():
    assert (
        normalize_owner("HUD SEC OF")
        == normalize_owner("SECRETARY OF HOUSING AND URBAN DEVELOPMENT")
        == "US DEPT OF HOUSING & URBAN DEVELOPMENT"
    )


def test_fannie_mae_variants_collide():
    assert normalize_owner("FEDERAL NATIONAL MORTGAGE ASSN") == "FANNIE MAE"
    assert normalize_owner("FANNIE MAE") == "FANNIE MAE"


def test_punctuation_and_whitespace_ignored():
    assert normalize_owner("SMITH, JOHN  A.") == normalize_owner("SMITH JOHN A")


def test_distinct_names_stay_distinct():
    assert normalize_owner("VB ONE LLC") != normalize_owner("VB ELEVEN LLC")


def test_merge_owner_rows_sums_and_keeps_biggest_display_name():
    rows = [
        {"owner_name": "CITY OF DAYTON", "transaction_count": 900, "total_spent": 100.0},
        {"owner_name": "DAYTON CITY OF", "transaction_count": 1800, "total_spent": 50.0},
        {"owner_name": "NVR INC", "transaction_count": 1000, "total_spent": 5.0},
    ]
    merged = merge_owner_rows(rows, sum_fields=("transaction_count", "total_spent"), limit=10)
    assert len(merged) == 2
    assert merged[0]["owner_name"] == "DAYTON CITY OF"
    assert merged[0]["transaction_count"] == 2700
    assert merged[0]["total_spent"] == 150.0
    assert merged[1]["owner_name"] == "NVR INC"


def test_merge_owner_rows_truncates_to_limit():
    rows = [
        {"owner_name": f"OWNER {i}", "transaction_count": i, "total_spent": 0}
        for i in range(10)
    ]
    merged = merge_owner_rows(rows, sum_fields=("transaction_count", "total_spent"), limit=3)
    assert len(merged) == 3
    assert merged[0]["transaction_count"] == 9
