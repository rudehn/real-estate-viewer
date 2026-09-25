"""Listing and downloading files from the county treasurer's download site."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import httpx

INDEX_URL = "https://go.mcohio.org/applications/treasurer/search/fdpopup.cfm"
FILE_URL = "https://go.mcohio.org/applications/treasurer/search/data/{folder}/{filename}"


@dataclass(frozen=True)
class Dataset:
    code: str  # fdpopup.cfm?dtype=
    folder: str  # data/<folder>/
    pattern: re.Pattern  # group(1) is the YYYYMMDD date


DATASETS = {
    "cama": Dataset("CC", "Cama", re.compile(r"Cama_Files_(\d{8})\.zip", re.I)),
    "taxroll": Dataset("TR", "Taxroll", re.compile(r"TAXROLL_(\d{8})\.zip", re.I)),
    "neighborhoods": Dataset(
        "NC", "nbhd_code_monthly", re.compile(r"neighborhood_codes_(\d{8})\.htm", re.I)
    ),
}


def county_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(60.0, read=300.0),
        headers={"User-Agent": "Mozilla/5.0 (real-estate-viewer)"},
        follow_redirects=True,
    )


async def list_files(dataset: str, client: httpx.AsyncClient) -> list[str]:
    spec = DATASETS[dataset]
    response = await client.get(INDEX_URL, params={"dtype": spec.code})
    response.raise_for_status()
    by_name = {m.group(0): m.group(1) for m in spec.pattern.finditer(response.text)}
    return sorted(by_name, key=lambda name: by_name[name])


async def latest_file(dataset: str, client: httpx.AsyncClient) -> str | None:
    files = await list_files(dataset, client)
    return files[-1] if files else None


async def download(
    dataset: str, filename: str, dest_dir: Path, client: httpx.AsyncClient
) -> Path:
    spec = DATASETS[dataset]
    folder = Path(dest_dir) / spec.folder
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / filename
    if target.exists():
        return target
    partial = folder / f".{filename}.part"
    url = FILE_URL.format(folder=spec.folder, filename=filename)
    try:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with partial.open("wb") as out:
                async for chunk in response.aiter_bytes(1 << 20):
                    out.write(chunk)
        partial.rename(target)
    finally:
        partial.unlink(missing_ok=True)
    return target
