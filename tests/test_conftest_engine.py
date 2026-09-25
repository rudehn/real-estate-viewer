from sqlalchemy import inspect


async def test_db_engine_has_all_tables(db_engine):
    async with db_engine.connect() as conn:
        tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
    assert {"parcel", "transaction", "datafile"} <= tables
