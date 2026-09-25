"""Property profile and timeline for one parcel."""
from __future__ import annotations

import datetime as dt
import json
import statistics
from datetime import date
from typing import Literal

import sqlalchemy as sa
from pydantic import BaseModel

from api.cache import cache, data_version
from api.errors import not_found
from db.county_models import (
    Dwelling,
    Neighborhood,
    NeighborhoodSummary,
    ParcelDetail,
    ParcelFeature,
    ParcelSummary,
    ParcelTax,
    ParcelValue,
    TaxDistrict,
)
from db.criteria import market_sale_criteria
from db.models import Parcel, Transaction

REAPPRAISAL_DATE = date(2026, 1, 1)


class NeighborhoodRef(BaseModel):
    code: str
    name: str | None = None
    display_name: str | None = None


class DistrictRef(BaseModel):
    code: str
    name: str | None = None
    school_district: str | None = None


class Facts(BaseModel):
    living_sqft: int | None
    beds: int | None
    baths: float | None
    full_baths: int | None
    half_baths: int | None
    stories: float | None
    style: str | None
    year_built: int | None
    year_built_is_placeholder: bool
    grade: str | None
    grade_label: str | None
    condition: str | None
    exterior: str | None
    basement: str | None
    finished_basement_sqft: int | None
    heating: str | None
    fuel: str | None
    has_central_air: bool
    fireplaces: int
    attached_garage_sqft: int
    detached_garage_sqft: int
    basement_garage_cars: int
    has_pool: bool


class Lot(BaseModel):
    land_use: str | None
    living_units: int | None
    lot_sqft: int | None
    lot_acres: float | None
    frontage_ft: float | None
    depth_ft: float | None


class SketchLine(BaseModel):
    line: int
    codes: list[str]
    area: int | None
    vector: str | None


class DwellingOut(BaseModel):
    card: int
    living_sqft: int | None
    year_built: int | None
    style: str | None
    sketch: list[SketchLine]


class FeatureOut(BaseModel):
    code: str
    description: str | None
    year_built: int | None
    area_sqft: int | None
    width_ft: int | None
    length_ft: int | None
    condition: str | None


class ValueOut(BaseModel):
    last_sale_date: date | None = None
    last_sale_price: float | None = None
    price_per_sqft: float | None = None
    neighborhood_median_price_per_sqft: float | None = None
    market_value_2025: int | None = None
    market_value_2026: int | None = None
    change_pct: float | None = None
    ratio_to_last_sale: float | None = None
    value_method: str | None = None
    appeal_year: int | None = None
    tif: bool = False
    abated: bool = False


class TaxOut(BaseModel):
    tax_year: int
    annual_bill: float
    effective_rate_pct: float | None
    district_median_effective_rate_pct: float | None
    gross_rate: float | None
    owner_occupied: bool
    homestead: bool
    rental_registered: bool
    foreclosure_date: date | None
    net_delinquent: float | None
    balance_due: float | None
    cauv: bool
    abated: bool


class OwnerOut(BaseModel):
    name: str | None
    name2: str | None
    mailing_address: str | None
    out_of_state: bool
    occupancy: str
    occupancy_reason: str | None


class ParcelProfile(BaseModel):
    parcel_id: str
    address: str | None
    is_active: bool
    parcel_class: str
    latitude: float | None
    longitude: float | None
    neighborhood: NeighborhoodRef | None
    tax_district: DistrictRef | None
    facts: Facts | None
    lot: Lot | None
    dwellings: list[DwellingOut]
    features: list[FeatureOut]
    value: ValueOut
    tax: TaxOut | None
    owner: OwnerOut | None
    badges: list[str]


class TimelineEvent(BaseModel):
    date: dt.date  # a field named "date" needs the module-qualified type
    kind: Literal["sale", "built", "reappraisal"]
    title: str
    amount: float | None = None
    detail: dict[str, object] = {}


_OCCUPANCY_BADGES = {
    "owner_occupied": "owner_occupied", "company": "company_owned", "trust": "trust_owned",
    "government": "government_owned", "absentee_individual": "absentee_owner",
}


async def _one(session, table, **where):
    stmt = sa.select(table).where(*[table.c[k] == v for k, v in where.items()])
    return (await session.exec(stmt)).mappings().first()


async def _district_median_rate(session, district: str) -> float | None:
    s = ParcelSummary.__table__

    async def compute():
        rows = (await session.exec(
            sa.select(s.c.annual_tax, s.c.market_value).where(
                s.c.tax_district == district, s.c.parcel_class == "R",
                s.c.annual_tax > 0, s.c.market_value > 0,
            )
        )).all()
        rates = [tax / value * 100 for tax, value in rows]
        return statistics.median(rates) if rates else None

    version = await data_version(session)
    return await cache.get_or_compute(("district-rate", district), version, compute)


def _facts(dwellings: list, features: list) -> Facts | None:
    if not dwellings:
        return None
    primary = max(dwellings, key=lambda d: (d["living_sqft"] or 0, -d["card"]))
    total = lambda key: sum(d[key] or 0 for d in dwellings)  # noqa: E731
    return Facts(
        living_sqft=total("living_sqft") or None,
        beds=total("beds") or None,
        baths=total("full_baths") + 0.5 * total("half_baths"),
        full_baths=total("full_baths"),
        half_baths=total("half_baths"),
        stories=primary["stories"],
        style=primary["style"],
        year_built=primary["year_built"],
        year_built_is_placeholder=primary["year_built_is_placeholder"],
        grade=primary["grade"],
        grade_label=primary["grade_label"],
        condition=primary["condition"],
        exterior=primary["exterior"],
        basement=primary["basement"],
        finished_basement_sqft=primary["finished_basement_sqft"],
        heating=primary["heating"],
        fuel=primary["fuel"],
        has_central_air=any(d["has_central_air"] for d in dwellings),
        fireplaces=total("fireplaces"),
        attached_garage_sqft=total("attached_garage_sqft"),
        detached_garage_sqft=sum(
            f["area_sqft"] or 0 for f in features if (f["code"] or "").startswith("RG")
        ),
        basement_garage_cars=total("basement_garage_cars"),
        has_pool=any((f["code"] or "").startswith("RP") for f in features),
    )


async def get_profile(session, parcel_id: str) -> ParcelProfile:
    parcel = await _one(session, Parcel.__table__, parcel_id=parcel_id)
    if parcel is None:
        raise not_found(f"Parcel {parcel_id}")
    summary = await _one(session, ParcelSummary.__table__, parcel_id=parcel_id)
    detail = await _one(session, ParcelDetail.__table__, parcel_id=parcel_id)
    value = await _one(session, ParcelValue.__table__, parcel_id=parcel_id)
    tax = await _one(session, ParcelTax.__table__, parcel_id=parcel_id)
    dw, ft = Dwelling.__table__, ParcelFeature.__table__
    dwellings = (await session.exec(
        sa.select(dw).where(dw.c.parcel_id == parcel_id).order_by(dw.c.card)
    )).mappings().all()
    features = (await session.exec(
        sa.select(ft).where(ft.c.parcel_id == parcel_id).order_by(ft.c.card, ft.c.line)
    )).mappings().all()

    neighborhood = None
    if parcel["neighborhood"]:
        hood = await _one(session, Neighborhood.__table__, code=parcel["neighborhood"])
        neighborhood = NeighborhoodRef(code=parcel["neighborhood"], **(
            {"name": hood["name"], "display_name": hood["display_name"]} if hood else {}))
    district = None
    if parcel["tax_district"]:
        row = await _one(session, TaxDistrict.__table__, code=parcel["tax_district"])
        district = DistrictRef(code=parcel["tax_district"], **(
            {"name": row["name"], "school_district": row["school_district"]} if row else {}))

    hood_summary = None
    if parcel["neighborhood"]:
        hood_summary = await _one(session, NeighborhoodSummary.__table__,
                                  code=parcel["neighborhood"])
    last_price = summary["last_sale_price"] if summary else None
    total_2026 = value["total_2026"] if value else None
    value_out = ValueOut(
        last_sale_date=summary["last_sale_date"] if summary else None,
        last_sale_price=last_price,
        price_per_sqft=summary["price_per_sqft"] if summary else None,
        neighborhood_median_price_per_sqft=(
            hood_summary["median_price_per_sqft_24m"] if hood_summary else None),
        market_value_2025=value["total_2025"] if value else None,
        market_value_2026=total_2026,
        change_pct=value["change_pct"] if value else None,
        ratio_to_last_sale=(total_2026 / last_price) if total_2026 and last_price else None,
        value_method=value["value_method"] if value else None,
        appeal_year=value["appeal_year"] if value else None,
        tif=bool(value["tif"]) if value else False,
        abated=bool(value["abated"]) if value else False,
    )

    tax_out = owner_out = None
    badges: list[str] = []
    if tax:
        rate = (tax["annual_bill"] / tax["market_value"] * 100) if tax["market_value"] else None
        tax_out = TaxOut(
            tax_year=tax["tax_year"], annual_bill=tax["annual_bill"], effective_rate_pct=rate,
            district_median_effective_rate_pct=(
                await _district_median_rate(session, parcel["tax_district"])
                if parcel["tax_district"] else None),
            gross_rate=tax["gross_rate"], owner_occupied=tax["owner_occupied"],
            homestead=tax["homestead"], rental_registered=tax["rental_registered"],
            foreclosure_date=tax["foreclosure_date"], net_delinquent=tax["net_delinquent"],
            balance_due=tax["balance_due"], cauv=tax["cauv"], abated=tax["abated"],
        )
        owner_out = OwnerOut(
            name=tax["owner_name"], name2=tax["owner_name2"],
            mailing_address=tax["mailing_address"], out_of_state=tax["out_of_state"],
            occupancy=tax["occupancy"], occupancy_reason=tax["occupancy_reason"],
        )
        if tax["occupancy"] in _OCCUPANCY_BADGES:
            badges.append(_OCCUPANCY_BADGES[tax["occupancy"]])
        if tax["out_of_state"]:
            badges.append("out_of_state_owner")
        if (tax["net_delinquent"] or 0) > 0:
            badges.append("tax_delinquent")
        if tax["foreclosure_date"]:
            badges.append("foreclosure_filed")
    if value_out.tif:
        badges.append("tif")
    if not parcel["is_active"]:
        badges.append("retired_parcel")

    return ParcelProfile(
        parcel_id=parcel_id,
        address=parcel["parcel_location"],
        is_active=bool(parcel["is_active"]),
        parcel_class=parcel["parcel_class"].name,
        latitude=summary["latitude"] if summary else None,
        longitude=summary["longitude"] if summary else None,
        neighborhood=neighborhood,
        tax_district=district,
        facts=_facts(dwellings, features),
        lot=Lot(
            land_use=detail["land_use"], living_units=detail["living_units"],
            lot_sqft=detail["lot_sqft"], lot_acres=detail["lot_acres"],
            frontage_ft=detail["frontage_ft"], depth_ft=detail["depth_ft"],
        ) if detail else None,
        dwellings=[
            DwellingOut(card=d["card"], living_sqft=d["living_sqft"], year_built=d["year_built"],
                        style=d["style"], sketch=json.loads(d["sketch"]) if d["sketch"] else [])
            for d in dwellings
        ],
        features=[FeatureOut(**{k: f[k] for k in FeatureOut.model_fields}) for f in features],
        value=value_out,
        tax=tax_out,
        owner=owner_out,
        badges=badges,
    )


def _built_title(year: int, placeholder: bool) -> str:
    if placeholder and year == 1919:
        return "Built before 1920"
    if placeholder:
        return "Built around 1900"
    return "Built"


async def get_timeline(session, parcel_id: str) -> list[TimelineEvent]:
    if await _one(session, Parcel.__table__, parcel_id=parcel_id) is None:
        raise not_found(f"Parcel {parcel_id}")
    t = Transaction.__table__
    sales = (await session.exec(
        sa.select(
            t.c.sale_date, t.c.sale_price, t.c.new_owner, t.c.old_owner, t.c.sale_validity,
            t.c.deed_reference,
            sa.case((market_sale_criteria(include_multi_parcel=True), True), else_=False)
            .label("is_market"),
        ).where(t.c.parcel_id == parcel_id)
    )).mappings().all()
    events = [
        TimelineEvent(
            date=s["sale_date"], kind="sale",
            title="Sold" if s["is_market"] else "Transferred",
            amount=s["sale_price"],
            detail={"buyer": s["new_owner"], "seller": s["old_owner"],
                    "is_market_sale": bool(s["is_market"]), "validity": s["sale_validity"],
                    "deed_reference": s["deed_reference"]},
        )
        for s in sales
    ]
    dw = Dwelling.__table__
    primary = (await session.exec(
        sa.select(dw.c.year_built, dw.c.year_built_is_placeholder)
        .where(dw.c.parcel_id == parcel_id, dw.c.year_built.isnot(None))
        .order_by(sa.func.coalesce(dw.c.living_sqft, 0).desc(), dw.c.card).limit(1)
    )).first()
    if primary:
        events.append(TimelineEvent(
            date=date(primary.year_built, 1, 1), kind="built",
            title=_built_title(primary.year_built, primary.year_built_is_placeholder),
        ))
    value = await _one(session, ParcelValue.__table__, parcel_id=parcel_id)
    if value and value["total_2026"] is not None:
        events.append(TimelineEvent(
            date=REAPPRAISAL_DATE, kind="reappraisal", title="2026 reappraisal",
            amount=value["total_2026"],
            detail={"previous": value["total_2025"], "change_pct": value["change_pct"]},
        ))
    return sorted(events, key=lambda e: e.date, reverse=True)
