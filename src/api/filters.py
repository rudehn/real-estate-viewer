"""The one filter contract every /v2 list and aggregate endpoint accepts.

Each response reports ``applied_filters``: the active filters the endpoint
actually honored, so the UI can say "not filtered by price" instead of
silently ignoring a filter.
"""
from collections.abc import Iterable
from datetime import date
from typing import Annotated, Literal

import sqlalchemy as sa
from fastapi import Query
from pydantic import BaseModel, Field, ValidationError, model_validator

from api.errors import ApiError
from db.models import ParcelClass

ClassCode = Literal["A", "C", "E", "I", "R", "U"]
OccupancyCode = Literal[
    "owner_occupied", "company", "trust", "government", "absentee_individual", "unknown"
]
SUMMARY_FILTERS = (
    "beds_min", "sqft_min", "sqft_max", "year_built_min", "year_built_max", "occupancy",
    "distress_min", "neighborhood",
)
_RANGES = (
    ("date_from", "date_to"), ("price_min", "price_max"), ("sqft_min", "sqft_max"),
    ("year_built_min", "year_built_max"),
)


class Filters(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    price_min: float | None = Field(None, ge=0)
    price_max: float | None = Field(None, ge=0)
    classes: list[ClassCode] | None = None
    beds_min: int | None = Field(None, ge=0, le=20)
    sqft_min: int | None = Field(None, ge=0)
    sqft_max: int | None = Field(None, ge=0)
    year_built_min: int | None = Field(None, ge=1700)
    year_built_max: int | None = Field(None, ge=1700)
    occupancy: list[OccupancyCode] | None = None
    distress_min: int | None = Field(None, ge=0, le=100)
    neighborhood: str | None = None

    @model_validator(mode="after")
    def _check_ranges(self):
        for low, high in _RANGES:
            a, b = getattr(self, low), getattr(self, high)
            if a is not None and b is not None and a > b:
                raise ValueError(f"{low} must not be greater than {high}")
        latest = date.today().year + 1
        for name in ("year_built_min", "year_built_max"):
            value = getattr(self, name)
            if value is not None and value > latest:
                raise ValueError(f"{name} cannot be after {latest}")
        return self

    def active(self) -> list[str]:
        return [name for name, value in self if value not in (None, [])]


def get_filters(
    date_from: date | None = None,
    date_to: date | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    classes: Annotated[list[str] | None, Query()] = None,
    beds_min: int | None = None,
    sqft_min: int | None = None,
    sqft_max: int | None = None,
    year_built_min: int | None = None,
    year_built_max: int | None = None,
    occupancy: Annotated[list[str] | None, Query()] = None,
    distress_min: int | None = None,
    neighborhood: str | None = None,
) -> Filters:
    try:
        return Filters(
            date_from=date_from, date_to=date_to, price_min=price_min, price_max=price_max,
            classes=classes, beds_min=beds_min, sqft_min=sqft_min, sqft_max=sqft_max,
            year_built_min=year_built_min, year_built_max=year_built_max,
            occupancy=occupancy, distress_min=distress_min, neighborhood=neighborhood,
        )
    except ValidationError as exc:
        message = "; ".join(
            e["msg"].removeprefix("Value error, ")
            if not e["loc"] else f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
            for e in exc.errors()
        )
        raise ApiError(422, "invalid_filters", message) from None


def honored(filters: Filters, names: Iterable[str]) -> list[str]:
    allowed = set(names)
    return [name for name in filters.active() if name in allowed]


def needs_summary(f: Filters) -> bool:
    return any(getattr(f, name) not in (None, []) for name in SUMMARY_FILTERS)


def summary_conditions(f: Filters, ps: sa.Table) -> list:
    c = []
    if f.beds_min is not None:
        c.append(ps.c.beds >= f.beds_min)
    if f.sqft_min is not None:
        c.append(ps.c.living_sqft >= f.sqft_min)
    if f.sqft_max is not None:
        c.append(ps.c.living_sqft <= f.sqft_max)
    if f.year_built_min is not None:
        c.append(ps.c.year_built >= f.year_built_min)
    if f.year_built_max is not None:
        c.append(ps.c.year_built <= f.year_built_max)
    if f.occupancy:
        c.append(ps.c.occupancy.in_(f.occupancy))
    if f.distress_min is not None:
        c.append(ps.c.distress_score >= f.distress_min)
    if f.neighborhood:
        c.append(ps.c.neighborhood == f.neighborhood)
    return c


def sale_conditions(f: Filters, t: sa.Table, ps: sa.Table) -> list:
    """Filters on a transaction row; summary filters need ps joined to t."""
    c = []
    if f.date_from:
        c.append(t.c.sale_date >= f.date_from)
    if f.date_to:
        c.append(t.c.sale_date <= f.date_to)
    if f.price_min is not None:
        c.append(t.c.sale_price >= f.price_min)
    if f.price_max is not None:
        c.append(t.c.sale_price <= f.price_max)
    if f.classes:
        c.append(t.c.parcel_class.in_([ParcelClass[code] for code in f.classes]))
    return c + summary_conditions(f, ps)


def parcel_conditions(f: Filters, ps: sa.Table) -> list:
    """Filters on a parcel_summary row: dates and prices refer to its last sale."""
    c = []
    if f.date_from:
        c.append(ps.c.last_sale_date >= f.date_from)
    if f.date_to:
        c.append(ps.c.last_sale_date <= f.date_to)
    if f.price_min is not None:
        c.append(ps.c.last_sale_price >= f.price_min)
    if f.price_max is not None:
        c.append(ps.c.last_sale_price <= f.price_max)
    if f.classes:
        c.append(ps.c.parcel_class.in_(f.classes))
    return c + summary_conditions(f, ps)
