import csv
import datetime
import glob
import hashlib
import re
import zipfile
from io import BytesIO, StringIO

from sqlalchemy import Date, bindparam, delete, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from db.engine import engine
from db.models import (
    SOURCE_WEEKLY,
    SOURCE_YEARLY,
    DataFile,
    Parcel,
    ParcelClass,
    SaleType,
    Transaction,
)
from logging_config import get_logger

logger = get_logger(__name__)

# How the county's repeated snapshots of one sale are reconciled:
#
# - Yearly rows are authoritative. The yearly file is re-exported monthly with
#   corrected buyer names, validity codes and the NBHD / DEEDREFERENCE columns
#   that weekly files lack, so yearly rows overwrite whatever is stored.
# - Weekly rows are provisional. They only fill gaps (sales newer than the last
#   yearly export) and never overwrite anything.
# - A weekly row is deleted once a yearly row exists for the same conveyance,
#   which catches snapshots whose seller name drifted and so got its own key.
#
# Keys are the partial unique indexes on Transaction (see db/models.py).
_CONVEYANCE_KEY = ("parcel_id", "sale_date", "conv_num", "old_owner")
_LEGACY_KEY = ("parcel_id", "sale_date", "sale_price", "old_owner", "new_owner")

_PRUNE_SUPERSEDED_SQL = text(
    """
    DELETE FROM "transaction"
    WHERE source = :weekly AND conv_num IS NOT NULL
      AND sale_date BETWEEN :start AND :end
      AND EXISTS (
        SELECT 1 FROM "transaction" y
        WHERE y.source = :yearly AND y.parcel_id = "transaction".parcel_id
          AND y.sale_date = "transaction".sale_date AND y.conv_num = "transaction".conv_num
      )
    """
).bindparams(bindparam("start", type_=Date), bindparam("end", type_=Date))

# Weekly files have no NBHD column. A parcel's neighborhood doesn't change
# between sales, so provisional rows borrow it from the parcel's history until
# the yearly export supplies it. Unscoped by date: the history may arrive after
# the weekly row, in a file for a different period.
_FILL_NEIGHBORHOOD_SQL = text(
    """
    UPDATE "transaction" SET neighborhood = (
        SELECT h.neighborhood FROM "transaction" h
        WHERE h.parcel_id = "transaction".parcel_id AND h.neighborhood IS NOT NULL
        ORDER BY h.sale_date DESC LIMIT 1
    )
    WHERE neighborhood IS NULL AND source = :weekly
      -- Only rows that will change: Postgres rewrites every row an UPDATE
      -- matches, even when the new value is still NULL.
      AND EXISTS (
        SELECT 1 FROM "transaction" h
        WHERE h.parcel_id = "transaction".parcel_id AND h.neighborhood IS NOT NULL
      )
    """
)


def _insert():
    """The dialect-specific INSERT (for ON CONFLICT) of the active engine.

    Reads the module-level ``engine`` so tests that monkeypatch it pick the
    right one.
    """
    return pg_insert if engine.dialect.name == "postgresql" else sqlite_insert


def _parcel_upsert_stmt(chunk: list[dict]):
    """INSERT ... ON CONFLICT DO NOTHING for parcels."""
    return _insert()(Parcel).values(chunk).on_conflict_do_nothing(index_elements=["parcel_id"])


def _transaction_upsert_stmt(chunk: list[dict], key: tuple[str, ...], where, overwrite: bool):
    stmt = _insert()(Transaction).values(chunk)
    if not overwrite:
        return stmt.on_conflict_do_nothing(index_elements=list(key), index_where=where)
    updates = {c: stmt.excluded[c] for c in chunk[0] if c not in key}
    return stmt.on_conflict_do_update(index_elements=list(key), index_where=where, set_=updates)


async def _upsert_transactions(
    session: AsyncSession, transactions: list[Transaction], source: str
) -> None:
    """Write one file's transactions according to the reconciliation rules."""
    by_key: dict[tuple[str, ...], dict[tuple, dict]] = {_CONVEYANCE_KEY: {}, _LEGACY_KEY: {}}
    for t in transactions:
        row = t.model_dump(exclude={"id"}) | {"source": source}
        key = _CONVEYANCE_KEY if row["conv_num"] is not None else _LEGACY_KEY
        # Collapse repeats within the file: Postgres refuses to upsert the same
        # row twice in one statement.
        by_key[key][tuple(row[c] for c in key)] = row

    overwrite = source == SOURCE_YEARLY
    conv_num = Transaction.__table__.c.conv_num
    for key, where in ((_CONVEYANCE_KEY, conv_num.isnot(None)), (_LEGACY_KEY, conv_num.is_(None))):
        rows = list(by_key[key].values())
        # Chunk to stay under per-statement bind-parameter limits (~23 params/row).
        chunk_size = 500
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i : i + chunk_size]
            await session.exec(_transaction_upsert_stmt(chunk, key, where, overwrite))

    if transactions:
        dates = [t.sale_date for t in transactions]
        params = {
            "weekly": SOURCE_WEEKLY, "yearly": SOURCE_YEARLY,
            "start": min(dates), "end": max(dates),
        }
        await session.exec(_PRUNE_SUPERSEDED_SQL, params=params)
        await session.exec(_FILL_NEIGHBORHOOD_SQL, params={"weekly": SOURCE_WEEKLY})


async def _write_file(
    session: AsyncSession, filename: str, content_hash: str,
    transactions: list[Transaction], parcels: dict[str, dict], source: str,
) -> None:
    """Store one file's parcels and transactions and record it as ingested."""
    parcel_values = list(parcels.values())
    # Chunk to stay under per-statement bind-parameter limits.
    chunk_size = 100
    for i in range(0, len(parcel_values), chunk_size):
        await session.exec(_parcel_upsert_stmt(parcel_values[i : i + chunk_size]))

    await _upsert_transactions(session, transactions, source)

    # One DataFile row per file name, describing the latest ingested content.
    await session.exec(delete(DataFile).where(DataFile.filename == filename))
    session.add(DataFile(
        filename=filename, content_hash=content_hash, ingested_at=datetime.datetime.now(),
    ))
    await session.commit()
    logger.info("Committed %d transactions from %s", len(transactions), filename)


def _file_key(path: str) -> str:
    """A data file's identity: its bare name, independent of DATA_DIR.

    The county's yearly ZIPs use backslash separators, which POSIX extracts as
    a literal backslash inside the file name, so split on both.
    """
    return re.split(r"[\\/]", path)[-1]


async def ingest_data_files(directory: str):
    await ingest_yearly_files(directory + "/yearly/**/SALES_*.csv")


async def ingest_yearly_files(pathname: str):
    csv_files = glob.glob(pathname, recursive=True)
    logger.info("Found %d file(s) to process", len(csv_files))
    for csv_file in csv_files:
        await ingest_yearly_file(csv_file)


async def ingest_yearly_file(path: str):
    """Ingest one yearly CSV unless this exact content was already ingested.

    The current-year file is re-exported monthly under the same name, so the
    content hash (not the name) decides whether there is anything new.
    """
    filename = _file_key(path)
    with open(path, "rb") as f:
        raw = f.read()
    content_hash = hashlib.sha256(raw).hexdigest()

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        already = await session.exec(
            select(DataFile).where(
                DataFile.filename == filename, DataFile.content_hash == content_hash
            )
        )
        if already.first():
            logger.info("Skipping %s (already processed)", filename)
            return

        logger.info("Processing %s...", path)
        transactions, parcels = _parse_csv_rows(_decode_csv(raw))
        await _write_file(session, filename, content_hash, transactions, parcels, SOURCE_YEARLY)


def _decode_csv(raw: bytes) -> str:
    """Decode a county sales CSV.

    The exports are usually plain ASCII, but occasionally carry cp1252 bytes -
    e.g. a non-breaking space (0xA0) typed into a mailing name - which are not
    valid UTF-8. Try UTF-8 first (so genuine UTF-8 is never mis-decoded), then
    fall back to cp1252. Non-breaking spaces become plain spaces so owner names
    still match across files.
    """
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    return text.replace("\xa0", " ")


def _parse_csv_rows(csv_text: str) -> tuple[list[Transaction], dict[str, dict]]:
    """Parse a sales CSV string into Transaction objects and a parcel dict.

    Shared by both the yearly (file-based) and weekly (in-memory) ingestors.
    Returns (transactions, parcels_by_id).
    """
    transactions: list[Transaction] = []
    parcels: dict[str, dict] = {}

    reader = csv.DictReader(StringIO(csv_text))
    for row in reader:
        cleaned = {k.strip(): v.strip() for k, v in row.items()}
        if not any(cleaned.values()):
            continue
        try:
            s_price = float(cleaned.get("PRICE", 0))
            acres_str = cleaned.get("ACRES", "0")
            acres = float(acres_str) if acres_str else 0.0
            conv_num = cleaned.get("CONVNUM")
            sale_date = datetime.datetime.strptime(cleaned["SALEDTE"], "%d-%b-%y").date()

            p_class_str = cleaned.get("CLS", "R")
            try:
                p_class = ParcelClass[p_class_str]
            except KeyError:
                p_class = ParcelClass.R

            assessed_land = cleaned.get("ASMTLAND")
            assessed_building = cleaned.get("ASMTBLDG")
            assessed_total = cleaned.get("ASMTTOTL")
            sale_type = cleaned.get("SALETYPE")

            transaction = Transaction(
                parcel_id=cleaned["PARID"],
                conv_num=int(conv_num) if conv_num else None,
                sale_date=sale_date,
                sale_price=s_price,
                old_owner=cleaned.get("OLDOWN", ""),
                new_owner=cleaned.get("OWNERNAME1", ""),
                parcel_location=cleaned.get("PARCELLOCATION", ""),
                mailing_name=cleaned.get("MAILINGNAME1", ""),
                mailing_address=cleaned.get("PADDR1", ""),
                parcel_class=p_class,
                acres=acres,
                taxable_land=int(cleaned.get("TAXLAND", 0)),
                taxable_building=int(cleaned.get("TAXBLDG", 0)),
                taxable_total=int(cleaned.get("TAXTOTAL", 0)),
                assessed_land=int(assessed_land) if assessed_land else None,
                assessed_building=int(assessed_building) if assessed_building else None,
                assessed_total=int(assessed_total) if assessed_total else None,
                sale_type=SaleType(sale_type.upper()) if sale_type else None,
                sale_validity=cleaned.get("SALEVALIDITY"),
                deed_reference=cleaned.get("DEEDREFERENCE"),
                neighborhood=cleaned.get("NBHD"),
            )
            transactions.append(transaction)
            parcels[transaction.parcel_id] = {
                "parcel_id": transaction.parcel_id,
                "parcel_location": transaction.parcel_location,
                "parcel_class": transaction.parcel_class,
                "acres": transaction.acres,
            }
        except Exception as e:
            logger.warning("Error parsing row: %s", e)

    return transactions, parcels


async def ingest_weekly_data() -> None:
    """Download all new weekly sales ZIPs and insert their records into the DB.

    - Skips ZIPs already tracked in DataFile (weekly ZIPs never change).
    - Downloads new ZIPs concurrently, then inserts each batch sequentially.
    - Rows are provisional: sales already stored are left as they are (see the
      reconciliation rules at the top of this module).
    """
    from services.data_retrieval import download_weekly_zips, get_weekly_zip_urls

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # 1. Determine which ZIPs are new (not yet in DataFile)
    async with async_session() as session:
        result = await session.exec(select(DataFile.filename))
        ingested = set(result.all())

    all_urls = await get_weekly_zip_urls()
    new_urls = [u for u in all_urls if u.split("/")[-1] not in ingested]

    if not new_urls:
        logger.info("No new weekly files to ingest.")
        return

    logger.info("%d new weekly ZIP(s) to download and ingest.", len(new_urls))

    # 2. Download all new ZIPs concurrently
    zip_payloads = await download_weekly_zips(new_urls)

    # 3. Insert each ZIP's records sequentially (SQLite write serialisation)
    for url, raw_bytes in zip_payloads:
        filename = url.split("/")[-1]
        await _ingest_weekly_zip(filename, raw_bytes)


async def _ingest_weekly_zip(filename: str, raw_bytes: bytes) -> None:
    """Parse one weekly ZIP and store its transactions as provisional rows."""
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Double-check the file hasn't been ingested in a concurrent run
        if (await session.exec(select(DataFile).where(DataFile.filename == filename))).first():
            logger.info("Skipping %s (already processed)", filename)
            return

        # Extract the single CSV from the ZIP
        try:
            with zipfile.ZipFile(BytesIO(raw_bytes)) as zf:
                csv_name = next(n for n in zf.namelist() if n.endswith(".csv"))
                csv_text = _decode_csv(zf.read(csv_name))
        except Exception as e:
            logger.warning("Could not read ZIP %s: %s", filename, e)
            return

        transactions, parcels = _parse_csv_rows(csv_text)
        if not transactions:
            logger.info("No rows parsed from %s", filename)
            return

        content_hash = hashlib.sha256(raw_bytes).hexdigest()
        await _write_file(session, filename, content_hash, transactions, parcels, SOURCE_WEEKLY)
