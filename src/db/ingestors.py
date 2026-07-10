import csv
import datetime
import glob
import zipfile
from io import BytesIO, StringIO

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from db.engine import engine
from db.models import DataFile, Parcel, ParcelClass, SaleType, Transaction
from logging_config import get_logger

logger = get_logger(__name__)


def _parcel_upsert_stmt(chunk: list[dict]):
    """INSERT ... ON CONFLICT DO NOTHING for parcels, for the active dialect.

    Works on both Postgres (production) and SQLite (local dev / tests). Reads
    the module-level ``engine`` so tests that monkeypatch it pick the right one.
    """
    insert = pg_insert if engine.dialect.name == "postgresql" else sqlite_insert
    return insert(Parcel).values(chunk).on_conflict_do_nothing(index_elements=["parcel_id"])


async def ingest_data_files(directory: str):
    await ingest_yearly_files(directory + "/yearly/**/SALES_*.csv")


async def ingest_yearly_files(pathname: str):
    csv_files = glob.glob(pathname, recursive=True)
    logger.info("Found %d file(s) to process", len(csv_files))
    for csv_file in csv_files:
        await ingest_yearly_file(csv_file)


async def ingest_yearly_file(filename: str):
    logger.info("Processing %s...", filename)

    # Create a local async session for this task
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 1. Check if file exists
        statement = select(DataFile).where(DataFile.filename == filename)
        result = await session.exec(statement)
        if result.first():
            logger.info("Skipping %s (already processed)", filename)
            return

        # 2. Read CSV (Sync operation, but fast enough for local files)
        # For massive files, we might run this in a thread, but simple read is fine here
        mappings = []
        parcels = {}

        with open(filename, encoding="utf-8-sig") as f:  # utf-8-sig handles BOM
            reader = csv.DictReader(f)
            for row in reader:
                cleaned_row = {k.strip(): v.strip() for k, v in row.items()}
                if not any(cleaned_row.values()):
                    continue

                try:
                    # conversions...
                    s_price = float(cleaned_row.get("PRICE", 0))
                    acres_str = cleaned_row.get("ACRES", "0")
                    acres = float(acres_str) if acres_str else 0.0
                    conv_num = cleaned_row.get("CONVNUM")

                    # Handle Date Parsing safely
                    sale_date_str = row["SALEDTE"]
                    sale_date = datetime.datetime.strptime(sale_date_str, "%d-%b-%y").date()

                    # Safely get Enum
                    p_class_str = cleaned_row.get("CLS", "R")
                    # Simple mapping fallback
                    try:
                        p_class = ParcelClass[p_class_str]
                    except:
                        p_class = ParcelClass.R  # Default or Log error

                    assessed_land = cleaned_row.get("ASMTLAND")
                    assessed_building = cleaned_row.get("ASMTBLDG")
                    assessed_total = cleaned_row.get("ASMTTOTL")
                    sale_type = cleaned_row.get("SALETYPE")
                    deed_reference = cleaned_row.get("DEEDREFERENCE")

                    transaction = Transaction(
                        parcel_id=cleaned_row["PARID"],
                        conv_num=int(conv_num) if conv_num else None,
                        sale_date=sale_date,
                        sale_price=s_price,
                        old_owner=cleaned_row.get("OLDOWN", ""),
                        new_owner=cleaned_row.get("OWNERNAME1", ""),
                        parcel_location=cleaned_row.get("PARCELLOCATION", ""),
                        mailing_name=cleaned_row.get("MAILINGNAME1", ""),
                        mailing_address=cleaned_row.get("PADDR1", ""),
                        parcel_class=p_class,
                        acres=acres,
                        taxable_land=int(cleaned_row.get("TAXLAND", 0)),
                        taxable_building=int(cleaned_row.get("TAXBLDG", 0)),
                        taxable_total=int(cleaned_row.get("TAXTOTAL", 0)),
                        assessed_land=int(assessed_land) if assessed_land else None,
                        assessed_building=int(assessed_building) if assessed_building else None,
                        assessed_total=int(assessed_total) if assessed_total else None,
                        sale_type=SaleType(sale_type.upper()) if sale_type else None,
                        sale_validity=cleaned_row.get("SALEVALIDITY"),
                        deed_reference=cleaned_row.get("DEEDREFERENCE"),
                        neighborhood=cleaned_row.get("NBHD"),
                    )
                    mappings.append(transaction)

                    # Prepare parcel for upsert
                    parcels[transaction.parcel_id] = {
                        "parcel_id": transaction.parcel_id,
                        "parcel_location": transaction.parcel_location,
                        "parcel_class": transaction.parcel_class,
                        "acres": transaction.acres,
                    }
                except Exception as e:
                    logger.warning("Error parsing row: %s", e)
                    continue

        if parcels:
            parcel_values = list(parcels.values())
            # Chunk to stay under per-statement bind-parameter limits.
            chunk_size = 100
            for i in range(0, len(parcel_values), chunk_size):
                chunk = parcel_values[i : i + chunk_size]
                await session.exec(_parcel_upsert_stmt(chunk))

        # 3. Bulk Insert Transactions
        if mappings:
            # SQLModel bulk insert for SQLite isn't fully async optimized,
            # but add_all + commit works well
            session.add_all(mappings)

            # 5. Mark file as ingested
            session.add(DataFile(filename=filename, ingested_at=datetime.datetime.now()))

            await session.commit()
            logger.info("Committed %d transactions from %s", len(mappings), filename)


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

    - Skips ZIPs already tracked in DataFile (file-level dedup).
    - Downloads new ZIPs concurrently, then inserts each batch sequentially.
    - Skips individual rows whose conv_num already exists (row-level dedup).
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
    """Parse one weekly ZIP and insert its transactions, skipping duplicates."""
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
                csv_text = zf.read(csv_name).decode("utf-8-sig")
        except Exception as e:
            logger.warning("Could not read ZIP %s: %s", filename, e)
            return

        transactions, parcels = _parse_csv_rows(csv_text)
        if not transactions:
            logger.info("No rows parsed from %s", filename)
            return

        parcel_values = list(parcels.values())
        chunk_size = 100
        for i in range(0, len(parcel_values), chunk_size):
            chunk = parcel_values[i : i + chunk_size]
            await session.exec(_parcel_upsert_stmt(chunk))

        session.add_all(transactions)

        session.add(DataFile(filename=filename, ingested_at=datetime.datetime.now()))
        await session.commit()
        logger.info("Committed %d transactions from %s", len(transactions), filename)
