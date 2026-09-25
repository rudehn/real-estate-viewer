"""Tests for downloading the county's yearly sales files."""
import io
import zipfile
from datetime import datetime

import httpx

import services.data_retrieval as retrieval


def _zip_response(year: int) -> httpx.Response:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"SALES_{year}_RES.csv", "PARID\n")
    return httpx.Response(200, content=buf.getvalue())


def test_refreshes_current_and_previous_year_only(tmp_path, monkeypatch):
    """The previous year's file on disk was downloaded while that year was
    still current, so it is partial until the county's final export."""
    this_year = datetime.now().year
    yearly = tmp_path / "yearly"
    yearly.mkdir()
    for year in range(2001, this_year + 1):
        (yearly / f"SALES_{year}_RES.csv").write_text("PARID\n")

    fetched: list[int] = []

    def fake_get(url, **_kwargs):
        year = int(url.rsplit("_", 1)[1].removesuffix(".zip"))
        fetched.append(year)
        return _zip_response(year)

    monkeypatch.setattr(retrieval, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(retrieval.httpx, "get", fake_get)
    retrieval.retrieve_yearly_data()

    assert fetched == [this_year, this_year - 1]
