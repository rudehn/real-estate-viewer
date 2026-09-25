"""End-to-end check of the data platform against real county files.

Usage:
    uv run python scripts/verify_real_data.py [--db database.db] [--county-dir /tmp/county]

Copies the local database (so the real one is untouched), downloads the
newest CAMA, tax roll and neighborhood files into --county-dir (reusing any
already there), runs every ingest step and the derived rebuild, then prints
coverage and timing, and calls the main /v2 endpoints through the ASGI app.
Exits 1 when a threshold fails.
"""
import argparse
import asyncio
import gzip
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

THRESHOLDS = {
    "active parcels": 250_000,
    "dwellings": 180_000,
    "parcel_tax rows": 250_000,
    "coordinates (% of active)": 95.0,
    "sales with a parcel neighborhood (%)": 97.0,
    "map binary gzip MB (max)": 8.0,
    "endpoint p95 ms (max)": 300.0,
}


async def main(db: Path, county_dir: Path) -> int:
    work = Path(tempfile.mkdtemp())
    copy = work / "verify.db"
    shutil.copy(db, copy)
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{copy}"
    os.environ["DATA_DIR"] = str(work)

    import sqlalchemy as sa
    from httpx import ASGITransport, AsyncClient

    from county import sources
    from db.engine import engine, init_db
    from db.maintenance import ensure_schema
    from derived import mapbinary
    from derived.summary import rebuild_derived
    from ingest.cama_ingest import ingest_cama
    from ingest.neighborhood_ingest import ingest_neighborhood_names
    from ingest.taxroll_ingest import ingest_taxroll
    from main import app

    mapbinary.DERIVED_DIR = work / "derived"
    await init_db()
    await ensure_schema()

    timings: dict[str, float] = {}
    async with sources.county_client() as client:
        paths = {}
        for dataset in ("cama", "taxroll", "neighborhoods"):
            name = await sources.latest_file(dataset, client)
            paths[dataset] = await sources.download(dataset, name, county_dir, client)
            print(f"{dataset}: {paths[dataset]}")
    for label, step in (
        ("cama", lambda: ingest_cama(paths["cama"])),
        ("neighborhoods", lambda: ingest_neighborhood_names(paths["neighborhoods"])),
        ("taxroll", lambda: ingest_taxroll(paths["taxroll"])),
        ("derived", rebuild_derived),
    ):
        start = time.perf_counter()
        await step()
        timings[label] = time.perf_counter() - start
        print(f"{label}: {timings[label]:.1f}s")

    async with engine.connect() as conn:
        def scalar(sql):
            return conn.execute(sa.text(sql))

        active = (await scalar("SELECT count(*) FROM parcel WHERE is_active")).scalar_one()
        located = (await scalar(
            "SELECT count(*) FROM parcel WHERE is_active AND latitude IS NOT NULL "
            "AND latitude != 0")).scalar_one()
        dwellings = (await scalar("SELECT count(*) FROM dwelling")).scalar_one()
        taxes = (await scalar("SELECT count(*) FROM parcel_tax")).scalar_one()
        with_hood = (await scalar(
            'SELECT count(*) FROM "transaction" t JOIN parcel p ON p.parcel_id = t.parcel_id '
            "WHERE p.neighborhood IS NOT NULL")).scalar_one()
        sales = (await scalar('SELECT count(*) FROM "transaction"')).scalar_one()

    _, path = mapbinary.latest_map_binary()
    gz_mb = len(gzip.compress(path.read_bytes())) / 1e6

    latencies: list[float] = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://v") as client:
        calls = ["/v2/meta", "/v2/market/summary", "/v2/market/trends?granularity=month",
                 "/v2/sales?page_size=50", "/v2/sales?sort=price_per_sqft&neighborhood=48150000",
                 "/v2/search?q=main", "/v2/search?q=smith", "/v2/neighborhoods",
                 "/v2/owners/top", "/v2/parcels/A01 00101 0001",
                 "/v2/parcels/A01 00101 0001/comps", "/v2/distress/distressed-sales"]
        for _ in range(3):  # the first pass warms caches
            for url in calls:
                start = time.perf_counter()
                r = await client.get(url)
                latencies.append((time.perf_counter() - start) * 1000)
                if r.status_code != 200:
                    print(f"FAIL {url}: {r.status_code} {r.text[:200]}")
                    return 1
    p95 = statistics.quantiles(latencies[len(calls):], n=20)[-1]

    results = {
        "active parcels": active,
        "dwellings": dwellings,
        "parcel_tax rows": taxes,
        "coordinates (% of active)": located / active * 100,
        "sales with a parcel neighborhood (%)": with_hood / sales * 100,
        "map binary gzip MB (max)": gz_mb,
        "endpoint p95 ms (max)": p95,
    }
    failed = False
    for name, value in results.items():
        limit = THRESHOLDS[name]
        ok = value <= limit if "(max)" in name else value >= limit
        failed |= not ok
        print(f"{'ok  ' if ok else 'FAIL'} {name}: {value:,.1f} (threshold {limit:,})")
    print(f"Work dir kept for inspection: {work}")
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("database.db"))
    parser.add_argument("--county-dir", type=Path, default=Path("/tmp/county"))
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.db, args.county_dir)))
