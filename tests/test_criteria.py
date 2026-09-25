import datetime as dt

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from db.criteria import market_sale_criteria, plausible_price_criteria, single_parcel_criteria
from db.models import Parcel, ParcelClass, Transaction


async def test_plausible_price_criteria(db_engine):
    async with AsyncSession(db_engine) as s:
        s.add(Parcel(parcel_id="P", parcel_location="X", parcel_class=ParcelClass.R, acres=0))
        for i, (price, value) in enumerate([(1_000, 120_000), (15_000, 120_000), (1_000, None)]):
            s.add(Transaction(
                parcel_id="P", sale_date=dt.date(2025, 1, 1 + i), sale_price=price,
                old_owner="A", new_owner="B", parcel_location="X", mailing_name="B",
                mailing_address="X", parcel_class=ParcelClass.R, acres=0, taxable_land=0,
                taxable_building=0, taxable_total=0, assessed_total=value,
            ))
        await s.commit()
        kept = (await s.exec(
            select(Transaction.sale_price).where(plausible_price_criteria())
        )).all()
    assert sorted(kept) == [1_000, 15_000]  # the $1,000 row with no recorded value passes


async def test_market_sale_query_plan_on_sqlite():
    """SQLite has no value histograms, so it plans from index heuristics alone.

    The price floor keeps most rows, so it must not drive the query
    (walking the sale_price index is several times slower than a scan), and
    the multi-parcel probe must be one lookup in the deal index.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        stmt = sa.select(Transaction.id).where(market_sale_criteria(), single_parcel_criteria())
        sql = stmt.compile(engine.sync_engine, compile_kwargs={"literal_binds": True})
        plan = [row[-1] for row in await conn.execute(sa.text(f"EXPLAIN QUERY PLAN {sql}"))]
    await engine.dispose()
    assert plan[0] == "SCAN transaction"
    assert any("ix_transaction_deal" in step for step in plan), plan


def test_price_floor_workaround_is_sqlite_only():
    sql = str(market_sale_criteria().compile(dialect=postgresql.dialect()))
    assert "sale_price >=" in sql
    assert "+ 0" not in sql
