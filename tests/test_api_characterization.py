import datetime as dt

from db.models import Parcel, ParcelClass, Transaction


def txn(pid, day, price, buyer, seller, mailing="1 LOCAL ST, DAYTON OH 45402"):
    return Transaction(
        parcel_id=pid, sale_date=day, sale_price=price, old_owner=seller, new_owner=buyer,
        parcel_location=f"{pid} ST", mailing_name=buyer, mailing_address=mailing,
        parcel_class=ParcelClass.R, acres=0.1, taxable_land=0, taxable_building=0,
        taxable_total=0, sale_validity="VALID SALE",
    )


async def seed(session):
    for i in range(6):
        session.add(Parcel(parcel_id=f"P{i}", parcel_location=f"P{i} ST",
                           parcel_class=ParcelClass.R, acres=0.1))
    # DUMPER LLC buys 1 and sells 5: a net seller.
    session.add(txn("P0", dt.date(2020, 1, 1), 100_000, "DUMPER LLC", "A"))
    for i in range(1, 6):
        session.add(txn(f"P{i}", dt.date(2021, i, 1), 100_000, f"BUYER {i}", "DUMPER LLC"))
    # FAR AWAY LLC mails out of state.
    session.add(txn("P0", dt.date(2022, 1, 1), 150_000, "FAR AWAY LLC", "DUMPER LLC",
                    mailing="PO BOX 1, AUSTIN TX 78701"))
    await session.commit()


async def test_net_sellers_characterization(client, session):
    await seed(session)
    r = await client.get("/analytics/net-sellers")
    assert r.status_code == 200
    rows = r.json()
    dumper = next(row for row in rows if row["owner_name"] == "DUMPER LLC")
    assert (dumper["buy_count"], dumper["sell_count"]) == (1, 6)


async def test_absentee_owners_characterization(client, session):
    await seed(session)
    r = await client.get("/analytics/absentee-owners")
    assert r.status_code == 200
    assert [row["owner_name"] for row in r.json()] == ["FAR AWAY LLC"]
