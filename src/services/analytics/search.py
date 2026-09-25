"""Grouped prefix search over addresses, parcel ids, owners and neighborhoods.

Prefix matching uses [prefix, upper bound) ranges on normalized, indexed
columns so a plain btree index serves it on SQLite and Postgres alike.
"""
import sqlalchemy as sa
from pydantic import BaseModel

from county.text import normalize_search, parcel_id_key, prefix_upper_bound, street_key
from db.county_models import Neighborhood, OwnerIndex, ParcelSummary


class AddressHit(BaseModel):
    parcel_id: str
    address: str | None
    neighborhood: str | None
    neighborhood_name: str | None
    last_sale_price: float | None


class ParcelHit(BaseModel):
    parcel_id: str
    address: str | None


class OwnerHit(BaseModel):
    name: str
    parcel_count: int


class NeighborhoodHit(BaseModel):
    code: str
    name: str
    display_name: str


class SearchResults(BaseModel):
    query: str
    addresses: list[AddressHit] = []
    parcels: list[ParcelHit] = []
    owners: list[OwnerHit] = []
    neighborhoods: list[NeighborhoodHit] = []


def _in_prefix(column, prefix: str):
    return sa.and_(column >= prefix, column < prefix_upper_bound(prefix))


async def search(session, q: str, limit: int = 8) -> SearchResults:
    query = normalize_search(q)
    results = SearchResults(query=query)
    if len(query) < 2:
        return results
    ps, n, oi = ParcelSummary.__table__, Neighborhood.__table__, OwnerIndex.__table__

    address_rows = (await session.exec(
        sa.select(ps.c.parcel_id, ps.c.address, ps.c.neighborhood, ps.c.last_sale_price,
                  n.c.name.label("neighborhood_name"))
        .select_from(ps).outerjoin(n, n.c.code == ps.c.neighborhood)
        .where(sa.or_(_in_prefix(ps.c.address_search, query),
                      _in_prefix(ps.c.street_search, street_key(query))))
        .order_by(ps.c.is_active.desc(), ps.c.address_search)
        .limit(limit)
    )).mappings().all()
    results.addresses = [AddressHit(**r) for r in address_rows]

    key = parcel_id_key(query)
    parcel_rows = (await session.exec(
        sa.select(ps.c.parcel_id, ps.c.address)
        .where(_in_prefix(ps.c.parcel_id_search, key))
        .order_by(ps.c.parcel_id_search).limit(limit)
    )).mappings().all()
    results.parcels = [ParcelHit(**r) for r in parcel_rows]

    owner_rows = (await session.exec(
        sa.select(oi.c.name, oi.c.parcel_count)
        .where(_in_prefix(oi.c.name_search, query))
        .order_by(oi.c.parcel_count.desc(), oi.c.name)
        .limit(limit)
    )).all()
    results.owners = [OwnerHit(name=name, parcel_count=count) for name, count in owner_rows]

    hood_rows = (await session.exec(
        sa.select(n.c.code, n.c.name, n.c.display_name)
        .where(sa.func.upper(n.c.name).contains(query, autoescape=True))
        .order_by(n.c.display_name).limit(limit)
    )).mappings().all()
    results.neighborhoods = [NeighborhoodHit(**r) for r in hood_rows]
    return results
