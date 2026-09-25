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

    monkeypatch.setattr(populate, "retrieve_yearly_data", retrieve_yearly)
    monkeypatch.setattr(populate, "ingest_data_files", ingest_yearly)
    monkeypatch.setattr(populate, "ingest_weekly_data", ingest_weekly)
    monkeypatch.setattr(populate, "geocode_parcels", geocode)
    return calls


async def test_all_steps_run(steps):
    await populate.populate_once()
    assert steps == ["retrieve_yearly", "ingest_yearly", "ingest_weekly", "geocode"]


async def test_yearly_failure_does_not_block_weekly_or_geocode(steps, monkeypatch):
    """A broken yearly download/ingest must not stop new weekly sales arriving."""
    def broken_retrieve():
        raise ConnectionError("county site down")

    monkeypatch.setattr(populate, "retrieve_yearly_data", broken_retrieve)
    await populate.populate_once()
    assert steps == ["ingest_weekly", "geocode"]


async def test_weekly_failure_does_not_block_geocode(steps, monkeypatch):
    async def broken_weekly():
        raise UnicodeDecodeError("utf-8", b"\xa0", 0, 1, "invalid start byte")

    monkeypatch.setattr(populate, "ingest_weekly_data", broken_weekly)
    await populate.populate_once()
    assert steps == ["retrieve_yearly", "ingest_yearly", "geocode"]
