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
