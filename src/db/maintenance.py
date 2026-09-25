"""Idempotent startup schema repair.

The deployment never runs alembic (init_db's create_all is the only schema
step, and it never alters existing tables), so databases created by older code
are brought up to date here on every startup. Each step checks before it acts,
so an up-to-date database passes straight through.

History this repairs:
- Transactions were once keyed on the full row, then on a natural key that
  included the buyer name. Both let drifting snapshots of one sale pile up as
  duplicates; the key is now the conveyance (see Transaction in db/models.py).
- Transactions had no ``source``, and DataFile had no ``content_hash`` and
  stored yearly files by full path. Forgetting the yearly files makes the next
  population run re-ingest them from disk under the new rules, which relabels
  their rows authoritative and prunes the weekly snapshots they supersede.

The SQL is written to run identically on SQLite and Postgres.
"""
from sqlalchemy import inspect, text

from db.engine import engine
from db.models import SOURCE_WEEKLY, Transaction
from logging_config import get_logger

logger = get_logger(__name__)

RETIRED_INDEXES = ("uq_transaction_natural",)

# Columns added to parcel for the county data platform. DDL is portable:
# SQLite and Postgres both accept BOOLEAN ... DEFAULT TRUE.
PARCEL_COLUMNS = {
    "neighborhood": "neighborhood VARCHAR",
    "tax_district": "tax_district VARCHAR",
    "land_use_code": "land_use_code VARCHAR",
    "zip": "zip VARCHAR",
    "census_tract": "census_tract VARCHAR",
    "is_active": "is_active BOOLEAN NOT NULL DEFAULT TRUE",
    "coord_source": "coord_source VARCHAR",
}

# Keep the oldest row of each group (for yearly-sourced sales the next
# re-ingest overwrites it with the authoritative values anyway). Correlated
# EXISTS rather than "id NOT IN (SELECT MIN(id) ... GROUP BY ...)": Postgres
# can only hash a NOT IN subquery that fits in work_mem, and on a
# production-sized table it falls back to rescanning it per row and never
# finishes. EXISTS plans as a hash semi-join (well under a second).
_DEDUPE_SQL = (
    text(
        """
        DELETE FROM "transaction" WHERE conv_num IS NOT NULL AND EXISTS (
            SELECT 1 FROM "transaction" k
            WHERE k.parcel_id = "transaction".parcel_id
              AND k.sale_date = "transaction".sale_date
              AND k.conv_num = "transaction".conv_num
              AND k.old_owner = "transaction".old_owner
              AND k.id < "transaction".id
        )
        """
    ),
    text(
        """
        DELETE FROM "transaction" WHERE conv_num IS NULL AND EXISTS (
            SELECT 1 FROM "transaction" k
            WHERE k.conv_num IS NULL
              AND k.parcel_id = "transaction".parcel_id
              AND k.sale_date = "transaction".sale_date
              AND k.sale_price = "transaction".sale_price
              AND k.old_owner = "transaction".old_owner
              AND k.new_owner = "transaction".new_owner
              AND k.id < "transaction".id
        )
        """
    ),
)

# Look indexes up by name in the catalog: SQLAlchemy's SQLite reflection
# skips expression-based indexes, so inspect().get_indexes() can miss them.
_INDEX_EXISTS_SQL = {
    "sqlite": text("SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = :name"),
    "postgresql": text("SELECT 1 FROM pg_indexes WHERE indexname = :name"),
}


def _has_index(sync_conn, name: str) -> bool:
    query = _INDEX_EXISTS_SQL[sync_conn.dialect.name]
    return sync_conn.execute(query, {"name": name}).first() is not None


def _add_missing_columns(sync_conn) -> None:
    inspector = inspect(sync_conn)
    txn_columns = {c["name"] for c in inspector.get_columns("transaction")}
    if "source" not in txn_columns:
        logger.info("Adding transaction.source; existing rows start provisional.")
        sync_conn.execute(text(
            f"""ALTER TABLE "transaction" ADD COLUMN source VARCHAR NOT NULL
                DEFAULT '{SOURCE_WEEKLY}'"""
        ))
    if "content_hash" not in {c["name"] for c in inspector.get_columns("datafile")}:
        logger.info("Adding datafile.content_hash.")
        sync_conn.execute(text("ALTER TABLE datafile ADD COLUMN content_hash VARCHAR"))


def _forget_unhashed_yearly_files(sync_conn) -> None:
    # Yearly CSVs recorded before content hashing (weekly ZIPs never change,
    # so their records stay valid).
    result = sync_conn.execute(text(
        "DELETE FROM datafile WHERE content_hash IS NULL AND filename LIKE '%.csv'"
    ))
    if result.rowcount:
        logger.info("Forgot %d yearly file record(s); they re-ingest next run.",
                    result.rowcount)


def _ensure_transaction_keys(sync_conn) -> None:
    # create_all only builds indexes along with a new table, so create any the
    # model declares that an older database lacks. Plain indexes go first: the
    # parcel_id index keeps the dedupe's correlated lookups fast on SQLite.
    missing = [ix for ix in Transaction.__table__.indexes if not _has_index(sync_conn, ix.name)]
    for index in (ix for ix in missing if not ix.unique):
        logger.info("Creating index %s.", index.name)
        index.create(sync_conn)
    if any(ix.unique for ix in missing):
        logger.info("Transaction keys missing; deduplicating...")
        removed = sum(sync_conn.execute(sql).rowcount for sql in _DEDUPE_SQL)
        logger.info("Removed %d duplicate transaction rows.", removed)
        for index in (ix for ix in missing if ix.unique):
            logger.info("Creating index %s.", index.name)
            index.create(sync_conn)
    for name in RETIRED_INDEXES:
        if _has_index(sync_conn, name):
            logger.info("Dropping retired index %s.", name)
            sync_conn.execute(text(f"DROP INDEX {name}"))


def _repair(sync_conn) -> None:
    _add_missing_columns(sync_conn)
    _forget_unhashed_yearly_files(sync_conn)
    _ensure_transaction_keys(sync_conn)


def _add_parcel_columns(sync_conn) -> None:
    existing = {c["name"] for c in inspect(sync_conn).get_columns("parcel")}
    for name, ddl in PARCEL_COLUMNS.items():
        if name not in existing:
            logger.info("Adding parcel.%s.", name)
            sync_conn.execute(text(f"ALTER TABLE parcel ADD COLUMN {ddl}"))
    if not _has_index(sync_conn, "ix_parcel_neighborhood"):
        sync_conn.execute(text("CREATE INDEX ix_parcel_neighborhood ON parcel (neighborhood)"))


def repair_schema(sync_conn) -> None:
    """Every idempotent repair, in order. Safe to run on any database."""
    _add_parcel_columns(sync_conn)
    if inspect(sync_conn).has_table("transaction"):
        _repair(sync_conn)


async def ensure_schema() -> None:
    """Bring a database created by older code up to the current schema."""
    async with engine.begin() as conn:
        await conn.run_sync(repair_schema)
