import datetime as dt

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from db.criteria import plausible_price_criteria
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
