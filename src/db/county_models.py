"""Tables loaded from the county's CAMA and tax roll files, plus derived tables.

Snapshot tables are fully replaced on each ingest (see ingest/bulk.py).
"""
from datetime import date, datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

# Prefix search compares against [prefix, prefix with its last character + 1),
# which only holds in byte order. Postgres' default linguistic collations
# (en_US.utf8) ignore spaces and punctuation such as ':' and '[' (the bounds of
# prefixes ending in 9 and Z), so the search keys use the "C" collation there.
SEARCH_KEY = sa.String().with_variant(sa.String(collation="C"), "postgresql")

OCCUPANCY_CATEGORIES = (
    "owner_occupied", "company", "trust", "government", "absentee_individual", "unknown",
)


class ParcelDetail(SQLModel, table=True):
    __tablename__ = "parcel_detail"
    parcel_id: str = Field(primary_key=True)
    land_use_code: str | None = None
    land_use: str | None = None
    living_units: int | None = None
    house_number: int | None = None
    street_direction: str | None = None
    street_name: str | None = None
    street_suffix: str | None = None
    unit: str | None = None
    city: str | None = None
    zip: str | None = None
    lot_sqft: int | None = None
    lot_acres: float | None = None
    frontage_ft: float | None = None
    depth_ft: float | None = None
    snapshot_date: date


class Dwelling(SQLModel, table=True):
    __tablename__ = "dwelling"
    parcel_id: str = Field(primary_key=True)
    card: int = Field(primary_key=True)
    living_sqft: int | None = None
    first_floor_sqft: int | None = None
    finished_basement_sqft: int | None = None
    beds: int | None = None
    full_baths: int | None = None
    half_baths: int | None = None
    stories: float | None = None
    style_code: str | None = None
    style: str | None = None
    year_built: int | None = None
    year_built_is_placeholder: bool = False
    grade: str | None = None
    grade_label: str | None = None
    condition: str | None = None
    exterior: str | None = None
    basement: str | None = None
    heating: str | None = None
    fuel: str | None = None
    has_central_air: bool = False
    fireplaces: int = 0
    attached_garage_sqft: int = 0
    basement_garage_cars: int = 0
    sketch: str | None = Field(default=None, sa_column=sa.Column(sa.Text))
    snapshot_date: date


class ParcelFeature(SQLModel, table=True):
    __tablename__ = "parcel_feature"
    id: int | None = Field(default=None, primary_key=True)
    parcel_id: str = Field(index=True)
    card: int | None = None
    line: int | None = None
    code: str
    description: str | None = None
    year_built: int | None = None
    area_sqft: int | None = None
    width_ft: int | None = None
    length_ft: int | None = None
    condition: str | None = None
    snapshot_date: date


class ParcelValue(SQLModel, table=True):
    __tablename__ = "parcel_value"
    parcel_id: str = Field(primary_key=True)
    land_2025: int | None = None
    building_2025: int | None = None
    total_2025: int | None = None
    land_2026: int | None = None
    building_2026: int | None = None
    total_2026: int | None = None
    change_pct: float | None = None
    value_method: str | None = None
    appeal_year: int | None = None
    tif: bool = False
    abated: bool = False
    reappraisal_reason: str | None = None
    snapshot_date: date


class Neighborhood(SQLModel, table=True):
    __tablename__ = "neighborhood"
    code: str = Field(primary_key=True)
    name: str
    display_name: str
    tax_district: str | None = None


class TaxDistrict(SQLModel, table=True):
    __tablename__ = "tax_district"
    code: str = Field(primary_key=True)
    name: str
    jurisdiction: str
    school_district: str | None = None


class ParcelTax(SQLModel, table=True):
    __tablename__ = "parcel_tax"
    parcel_id: str = Field(primary_key=True)
    tax_year: int
    snapshot_date: date
    annual_bill: float
    gross_rate: float | None = None
    effective_rate: float | None = None
    market_value: float | None = None
    owner_occupied: bool = False
    homestead: bool = False
    rental_registered: bool = False
    foreclosure_date: date | None = None
    cauv: bool = False
    abated: bool = False
    net_delinquent: float | None = None
    balance_due: float | None = None
    census_tract: str | None = None
    zip: str | None = None
    city: str | None = None
    owner_name: str | None = None
    owner_name2: str | None = None
    mailing_name: str | None = None
    mailing_address: str | None = None
    mailing_state: str | None = None
    out_of_state: bool = False
    occupancy: str = "unknown"
    occupancy_reason: str | None = None


class ParcelSummary(SQLModel, table=True):
    """One denormalized row per parcel for the map, search and filters."""

    __tablename__ = "parcel_summary"
    parcel_id: str = Field(primary_key=True)
    parcel_id_search: str | None = Field(default=None, index=True, sa_type=SEARCH_KEY)
    latitude: float | None = None
    longitude: float | None = None
    parcel_class: str
    land_use_code: str | None = None
    neighborhood: str | None = Field(default=None, index=True)
    tax_district: str | None = None
    is_active: bool = True
    address: str | None = None
    address_search: str | None = Field(default=None, index=True, sa_type=SEARCH_KEY)
    street_search: str | None = Field(default=None, index=True, sa_type=SEARCH_KEY)
    owner_name: str | None = None
    last_sale_date: date | None = Field(default=None, index=True)
    last_sale_price: float | None = None
    price_per_sqft: float | None = None
    living_sqft: int | None = None
    beds: int | None = None
    baths: float | None = None
    year_built: int | None = None
    year_built_is_placeholder: bool = False
    market_value: float | None = None
    value_change_pct: float | None = None
    occupancy: str = "unknown"
    out_of_state_owner: bool = False
    distress_score: int = 0
    distress_flags: int = 0
    permit_count_5y: int = 0
    last_permit_date: date | None = None
    annual_tax: float | None = None


class NeighborhoodSummary(SQLModel, table=True):
    __tablename__ = "neighborhood_summary"
    code: str = Field(primary_key=True)
    parcel_count: int = 0
    residential_count: int = 0
    parcels_sold_24m: int = 0
    median_sale_price_24m: float | None = None
    median_price_per_sqft_24m: float | None = None
    owner_occupied_share: float | None = None
    median_year_built: float | None = None
    median_value_change_pct: float | None = None


class OwnerIndex(SQLModel, table=True):
    """One row per distinct owner name seen, current or past, for search.

    parcel_count is how many active parcels in parcel_summary the name
    currently owns; 0 means the name only appears as a past transaction buyer.
    """

    __tablename__ = "owner_index"
    name: str = Field(primary_key=True)
    name_search: str = Field(index=True, sa_type=SEARCH_KEY)
    parcel_count: int = 0


class DataVersion(SQLModel, table=True):
    """Single row (id=1). Bumped by the derived step; keys every cache."""

    __tablename__ = "data_version"
    id: int = Field(default=1, primary_key=True)
    version: int = 0
    updated_at: datetime
