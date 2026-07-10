"""Idempotent startup data repair.

The deployment never runs alembic (init_db's create_all is the only schema
step), so databases created before the transaction natural-key index exist
with duplicate rows: the weekly sales ZIPs overlap each other and the yearly
files, and ingest had no row-level dedup. This module brings such databases
up to date on startup — delete duplicates, then add the unique index so the
problem cannot recur. Fresh databases get the index from create_all and skip
straight through.

The SQL is written to run identically on SQLite and Postgres.
"""
from sqlalchemy import inspect, text

from db.engine import engine
from logging_config import get_logger

logger = get_logger(__name__)

NATURAL_KEY_INDEX = "uq_transaction_natural"

_DEDUPE_SQL = text(
    """
    DELETE FROM "transaction" WHERE id NOT IN (
        SELECT MIN(id) FROM "transaction"
        GROUP BY parcel_id, sale_date, sale_price, old_owner, new_owner,
                 COALESCE(conv_num, -1)
    )
    """
)

_CREATE_INDEX_SQL = text(
    f"""
    CREATE UNIQUE INDEX IF NOT EXISTS {NATURAL_KEY_INDEX}
    ON "transaction" (parcel_id, sale_date, sale_price, old_owner, new_owner,
                      COALESCE(conv_num, -1))
    """
)


def _has_natural_key_index(sync_conn) -> bool:
    indexes = inspect(sync_conn).get_indexes("transaction")
    return any(ix["name"] == NATURAL_KEY_INDEX for ix in indexes)


async def ensure_transaction_dedup() -> None:
    """Delete duplicate transactions and add the unique natural-key index.

    No-op when the index already exists (fresh DBs, or repaired ones).
    """
    async with engine.begin() as conn:
        if await conn.run_sync(_has_natural_key_index):
            return
        logger.info("Transaction natural-key index missing; deduplicating...")
        result = await conn.execute(_DEDUPE_SQL)
        await conn.execute(_CREATE_INDEX_SQL)
        logger.info(
            "Removed %s duplicate transaction rows; created %s.",
            result.rowcount, NATURAL_KEY_INDEX,
        )
