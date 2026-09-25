"""Neighborhood list, multi-neighborhood trends and single-neighborhood report."""
from __future__ import annotations

import sqlalchemy as sa
from pydantic import BaseModel

from api.errors import not_found
from api.filters import Filters
from db.county_models import Neighborhood, NeighborhoodSummary, TaxDistrict
from services.analytics.market import market_sale_rows, medians_by_group
from services.analytics.parcels import DistrictRef
from services.analytics.sales import SaleRow, list_sales

_STATIC = ("parcel_count", "owner_occupied_share", "median_year_built", "median_value_change_pct")


class NeighborhoodRow(BaseModel):
    code: str
    name: str | None
    display_name: str | None
    tax_district: str | None
    sales: int
    median_price: float | None
    median_price_per_sqft: float | None
    total_volume: float | None
    parcel_count: int | None = None
    owner_occupied_share: float | None = None
    median_year_built: float | None = None
    median_value_change_pct: float | None = None


class TrendRow(BaseModel):
    neighborhood: str
    name: str | None
    year: int
    sales: int
    median_price: float | None


class YearStats(BaseModel):
    year: int
    sales: int
    median_price: float | None
    median_price_per_sqft: float | None


class NeighborhoodReport(BaseModel):
    code: str
    name: str
    display_name: str
    tax_district: DistrictRef | None
    summary: dict | None
    trend: list[YearStats]
    recent_sales: list[SaleRow]


async def _names(session) -> dict[str, dict]:
    n, ns = Neighborhood.__table__, NeighborhoodSummary.__table__
    rows = (await session.exec(
        sa.select(n.c.code, n.c.name, n.c.display_name, n.c.tax_district,
                  *[ns.c[c] for c in _STATIC]).select_from(n)
        .outerjoin(ns, ns.c.code == n.c.code)
    )).mappings().all()
    return {r["code"]: dict(r) for r in rows}


async def list_neighborhoods(session, f: Filters) -> list[NeighborhoodRow]:
    rows = market_sale_rows(f)
    prices = await medians_by_group(session, rows, ["neighborhood"], "sale_price")
    ppsf = await medians_by_group(session, rows, ["neighborhood"], "ppsf")
    names = await _names(session)
    out = []
    for (code,), stats in prices.items():
        if code is None:
            continue
        meta = names.get(code, {})
        out.append(NeighborhoodRow(
            code=code, name=meta.get("name"), display_name=meta.get("display_name"),
            tax_district=meta.get("tax_district"), sales=stats.count,
            median_price=stats.median, total_volume=stats.total,
            median_price_per_sqft=ppsf.get((code,)).median if (code,) in ppsf else None,
            **{k: meta.get(k) for k in _STATIC},
        ))
    return sorted(out, key=lambda r: (-r.sales, r.code))


async def neighborhood_trends(session, f: Filters, codes: list[str] | None, limit: int,
                              min_sales: int) -> list[TrendRow]:
    rows = market_sale_rows(f)
    stats = await medians_by_group(session, rows, ["neighborhood", "year"], "sale_price")
    if not codes:
        totals: dict[str, int] = {}
        for (code, _year), s in stats.items():
            if code:
                totals[code] = totals.get(code, 0) + s.count
        codes = [c for c, _ in sorted(totals.items(), key=lambda kv: -kv[1])[:limit]]
    names = await _names(session)
    wanted = set(codes)
    return sorted(
        (TrendRow(neighborhood=code, name=names.get(code, {}).get("name"), year=year,
                  sales=s.count, median_price=s.median)
         for (code, year), s in stats.items() if code in wanted and s.count >= min_sales),
        key=lambda r: (r.neighborhood, r.year),
    )


async def neighborhood_report(session, code: str) -> NeighborhoodReport:
    names = await _names(session)
    if code not in names:
        raise not_found(f"Neighborhood {code}")
    meta = names[code]
    f = Filters(neighborhood=code)
    rows = market_sale_rows(f)
    prices = await medians_by_group(session, rows, ["year"], "sale_price")
    ppsf = await medians_by_group(session, rows, ["year"], "ppsf")
    trend = [
        YearStats(year=year, sales=s.count, median_price=s.median,
                  median_price_per_sqft=ppsf[(year,)].median if (year,) in ppsf else None)
        for (year,), s in sorted(prices.items())
    ]
    district = None
    if meta["tax_district"]:
        districts = TaxDistrict.__table__
        row = (await session.exec(
            sa.select(districts).where(districts.c.code == meta["tax_district"])
        )).mappings().first()
        if row:
            district = DistrictRef(code=row["code"], name=row["name"],
                                   school_district=row["school_district"])
    summaries = NeighborhoodSummary.__table__
    summary = (await session.exec(
        sa.select(summaries).where(summaries.c.code == code)
    )).mappings().first()
    recent = await list_sales(session, f, sort="sale_date", order="desc", page=1, page_size=10,
                              market_only=True)
    return NeighborhoodReport(
        code=code, name=meta["name"], display_name=meta["display_name"], tax_district=district,
        summary=dict(summary) if summary else None, trend=trend, recent_sales=recent.rows,
    )
