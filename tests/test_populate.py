"""Tests for the background scrape-and-populate pipeline (services/populate.py)."""
import pytest

import services.populate as populate


@pytest.fixture
def steps(monkeypatch):
    """Replace every pipeline step with a recorder; returns the call log."""
    calls: list[str] = []

    def retrieve_yearly():
        calls.append("retrieve_yearly")

    async def ingest_yearly(_directory):
        calls.append("ingest_yearly")

    async def ingest_weekly():
        calls.append("ingest_weekly")

    async def geocode(batch_size):
        calls.append("geocode")
        return 0

    async def cama():
        calls.append("cama")

    async def neighborhood_names():
        calls.append("neighborhood_names")

    async def taxroll():
        calls.append("taxroll")

    async def derived():
        calls.append("derived")

    monkeypatch.setattr(populate, "retrieve_yearly_data", retrieve_yearly)
    monkeypatch.setattr(populate, "ingest_data_files", ingest_yearly)
    monkeypatch.setattr(populate, "ingest_weekly_data", ingest_weekly)
    monkeypatch.setattr(populate, "geocode_parcels", geocode)
    monkeypatch.setattr(populate, "_cama", cama)
    monkeypatch.setattr(populate, "_neighborhood_names", neighborhood_names)
    monkeypatch.setattr(populate, "_taxroll", taxroll)
    monkeypatch.setattr(populate, "_derived", derived)
    return calls


async def test_all_steps_run(steps):
    await populate.populate_once()
    assert steps == ["retrieve_yearly", "ingest_yearly", "ingest_weekly", "cama",
                     "neighborhood_names", "taxroll", "geocode", "derived"]


async def test_yearly_failure_does_not_block_weekly_or_geocode(steps, monkeypatch):
    """A broken yearly download/ingest must not stop new weekly sales arriving."""
    def broken_retrieve():
        raise ConnectionError("county site down")

    monkeypatch.setattr(populate, "retrieve_yearly_data", broken_retrieve)
    await populate.populate_once()
    assert steps == ["ingest_weekly", "cama", "neighborhood_names", "taxroll", "geocode",
                     "derived"]


async def test_weekly_failure_does_not_block_geocode(steps, monkeypatch):
    async def broken_weekly():
        raise UnicodeDecodeError("utf-8", b"\xa0", 0, 1, "invalid start byte")

    monkeypatch.setattr(populate, "ingest_weekly_data", broken_weekly)
    await populate.populate_once()
    assert steps == ["retrieve_yearly", "ingest_yearly", "cama", "neighborhood_names",
                     "taxroll", "geocode", "derived"]


async def test_county_steps_can_be_disabled(steps, monkeypatch):
    monkeypatch.setenv("COUNTY_INGEST", "false")
    await populate.populate_once()
    assert "cama" not in steps and "taxroll" not in steps
    assert steps[-1] == "derived"
