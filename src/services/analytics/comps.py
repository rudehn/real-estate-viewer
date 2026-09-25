"""Comparable sales for a parcel (spec section 6.4)."""
from __future__ import annotations

import math
import statistics
from datetime import date, timedelta

import sqlalchemy as sa
from pydantic import BaseModel

from api.errors import not_found
from db.county_models import Dwelling, ParcelSummary
from db.criteria import market_sale, single_parcel_criteria
from db.models import Parcel, Transaction
from derived.summary import latest_sale_date

STYLE_FAMILIES = {
    "01": "split", "02": "split", "03": "ranch", "04": "attached", "05": "two_story",
    "06": "story_and_half", "07": "two_story", "08": "story_and_half", "09": "two_story",
    "10": "attached", "11": "multi", "12": "multi", "13": "other", "14": "two_story",
    "15": "two_story", "16": "two_story", "17": "manufactured", "18": "manufactured",
    "19": "other", "20": "two_story",
}
MIN_NEIGHBORHOOD_COMPS = 5
RADIUS_MILES = 1.0
LOOKBACK_DAYS = 730


class Subject(BaseModel):
    living_sqft: int | None = None
    beds: int | None = None
    baths: float | None = None
    year_built: int | None = None
    style: str | None = None


class Comp(BaseModel):
    parcel_id: str
    address: str | None
    sale_date: date
    sale_price: float
    price_per_sqft: float | None
    living_sqft: int | None
    beds: int | None
    baths: float | None
    year_built: int | None
    style: str | None
    distance_miles: float | None
    similarity: float


class CompsResult(BaseModel):
    subject: Subject
    basis: str
    message: str | None = None
    median_price: float | None = None
    median_price_per_sqft: float | None = None
    comps: list[Comp] = []


def miles_between(lat1, lng1, lat2, lng2) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _first_card_style(dw):
    inner = Dwelling.__table__.alias("first_card")
    first = sa.select(sa.func.min(inner.c.card)).where(inner.c.parcel_id == dw.c.parcel_id)
    return dw.c.card == first.scalar_subquery()


async def _candidates(session, subject: dict, since: date, where) -> list[dict]:
    t, ps, dw = Transaction.__table__, ParcelSummary.__table__, Dwelling.__table__
    sqft = subject["living_sqft"]
    query = (
        sa.select(t.c.parcel_id, t.c.sale_date, t.c.sale_price, ps.c.address,
                  ps.c.living_sqft, ps.c.beds, ps.c.baths, ps.c.year_built,
                  ps.c.latitude, ps.c.longitude, dw.c.style_code, dw.c.style)
        .select_from(t)
        .join(ps, ps.c.parcel_id == t.c.parcel_id)
        .join(dw, sa.and_(dw.c.parcel_id == t.c.parcel_id, _first_card_style(dw)))
        .where(
            market_sale(), single_parcel_criteria(), t.c.sale_date >= since,
            t.c.parcel_id != subject["parcel_id"],
            ps.c.living_sqft.between(sqft * 0.8, sqft * 1.2),
            where,
        )
    )
    return [dict(r) for r in (await session.exec(query)).mappings().all()]


def _differs(subject: dict, c: dict, key: str, tolerance: float) -> bool:
    a, b = subject[key], c[key]
    return a is not None and b is not None and abs(a - b) > tolerance


def _matches(subject: dict, c: dict) -> bool:
    if STYLE_FAMILIES.get(c["style_code"]) != STYLE_FAMILIES.get(subject["style_code"]):
        return False
    return not (
        _differs(subject, c, "beds", 1)
        or _differs(subject, c, "baths", 1)
        or _differs(subject, c, "year_built", 15)
    )


def _score(subject: dict, c: dict, anchor: date, distance: float | None) -> float:
    score = 100.0
    score -= abs(c["living_sqft"] - subject["living_sqft"]) / subject["living_sqft"] * 100
    if subject["year_built"] and c["year_built"]:
        score -= abs(c["year_built"] - subject["year_built"]) * 0.5
    for key in ("beds", "baths"):
        if subject[key] is not None and c[key] is not None:
            score -= abs(c[key] - subject[key]) * 5
    score -= (anchor - c["sale_date"]).days / 30.4
    if distance is not None:
        score -= distance * 10
    return round(score, 1)


async def get_comps(session, parcel_id: str, limit: int = 10) -> CompsResult:
    ps, dw = ParcelSummary.__table__, Dwelling.__table__
    parcel = (await session.exec(
        sa.select(Parcel.__table__.c.parcel_id).where(Parcel.__table__.c.parcel_id == parcel_id)
    )).first()
    if parcel is None:
        raise not_found(f"Parcel {parcel_id}")
    row = (await session.exec(
        sa.select(ps.c.parcel_id, ps.c.neighborhood, ps.c.living_sqft, ps.c.beds, ps.c.baths,
                  ps.c.year_built, ps.c.latitude, ps.c.longitude, dw.c.style_code, dw.c.style)
        .select_from(ps)
        .join(dw, sa.and_(dw.c.parcel_id == ps.c.parcel_id, _first_card_style(dw)))
        .where(ps.c.parcel_id == parcel_id)
    )).mappings().first()
    if row is None or not row["living_sqft"]:
        return CompsResult(subject=Subject(), basis="none",
                           message="No dwelling on record to compare")
    subject = dict(row)
    subject_out = Subject(living_sqft=subject["living_sqft"], beds=subject["beds"],
                          baths=subject["baths"], year_built=subject["year_built"],
                          style=subject["style"])
    anchor = await latest_sale_date(await session.connection()) or date.today()
    since = anchor - timedelta(days=LOOKBACK_DAYS)

    basis = "neighborhood"
    found = [c for c in await _candidates(session, subject, since,
                                          ps.c.neighborhood == subject["neighborhood"])
             if _matches(subject, c)]
    distances: dict[str, float | None] = {c["parcel_id"]: None for c in found}
    if len(found) < MIN_NEIGHBORHOOD_COMPS and subject["latitude"] is not None:
        basis = "radius"
        dlat = RADIUS_MILES / 69.0
        dlng = RADIUS_MILES / (69.0 * math.cos(math.radians(subject["latitude"])))
        box = sa.and_(
            ps.c.latitude.between(subject["latitude"] - dlat, subject["latitude"] + dlat),
            ps.c.longitude.between(subject["longitude"] - dlng, subject["longitude"] + dlng),
        )
        found = []
        for c in await _candidates(session, subject, since, box):
            miles = miles_between(subject["latitude"], subject["longitude"],
                                  c["latitude"], c["longitude"])
            if miles <= RADIUS_MILES and _matches(subject, c):
                found.append(c)
                distances[c["parcel_id"]] = round(miles, 3)

    comps = sorted(
        (
            Comp(
                parcel_id=c["parcel_id"], address=c["address"], sale_date=c["sale_date"],
                sale_price=c["sale_price"],
                price_per_sqft=c["sale_price"] / c["living_sqft"] if c["living_sqft"] else None,
                living_sqft=c["living_sqft"], beds=c["beds"], baths=c["baths"],
                year_built=c["year_built"], style=c["style"],
                distance_miles=distances.get(c["parcel_id"]),
                similarity=_score(subject, c, anchor, distances.get(c["parcel_id"])),
            )
            for c in found
        ),
        key=lambda comp: comp.similarity, reverse=True,
    )[:limit]
    return CompsResult(
        subject=subject_out, basis=basis if comps else "none",
        message=None if comps else "No comparable sales in the last 24 months",
        median_price=statistics.median([c.sale_price for c in comps]) if comps else None,
        median_price_per_sqft=statistics.median(
            [c.price_per_sqft for c in comps if c.price_per_sqft]) if comps else None,
        comps=comps,
    )
