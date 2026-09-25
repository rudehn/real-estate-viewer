from datetime import date, datetime
from enum import Enum

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy import Index, text
from sqlmodel import Field, Relationship, SQLModel


class ParcelClass(Enum):
    """Type of Parcel"""
    A="Agricultural"
    C="Commercial"
    E="Exempt"
    I="Industrial"  # noqa: E741 - the county's class code
    R="Residential"
    U="Utilities"

class SaleType(Enum):
    """Type of Sale"""
    LAND = "LAND ONLY"
    BUILDING = "BUILDING ONLY"
    LAND_AND_BUILDING = "LAND AND BUILDING"
    MOBILE_HOME = "MOBILE HOME"

class ParcelBase(SQLModel):
    # id: int | None = Field(default=None, primary_key=True, index=True)
    parcel_id: str = Field(description="Parcel Identification Number", primary_key=True, index=True)
    parcel_location: str = Field(description="Parcel Location")
    parcel_class: ParcelClass = Field(description="Parcel Class")
    acres: float = Field(description="Parcel Acreage")
    # owner: str = Field(description="Owner Name")

    latitude: float | None = Field(default=None, description="Geographic Latitude")
    longitude: float | None = Field(default=None, description="Geographic Longitude")

    neighborhood: str | None = Field(default=None, index=True, description="CAMA neighborhood code")
    tax_district: str | None = Field(default=None, description="Tax district code")
    land_use_code: str | None = Field(default=None, description="Ohio DTE land use code")
    zip: str | None = Field(default=None, description="Situs ZIP code")
    census_tract: str | None = Field(default=None, description="Census block group")
    is_active: bool = Field(
        default=True,
        sa_column_kwargs={"server_default": sa.true()},
        description="False once the parcel disappears from CAMA (retired or combined)",
    )
    coord_source: str | None = Field(default=None, description="county or census")


class Parcel(ParcelBase, table=True):

    # Defines the relationship back to Transaction, referencing the class by string.
    transactions: list["Transaction"] = Relationship(back_populates="parcel")


# A simple model just for the nested lat/long
class ParcelResponse(ParcelBase):
    ...

SOURCE_YEARLY = "yearly"
SOURCE_WEEKLY = "weekly"


class TransactionBase(SQLModel):
    # Years 2001-2002 don't have the fields that are marked as optional (beside the id)
    id: int | None = Field(default=None, primary_key=True, index=True)
    parcel_id: str = Field(
        description="Parcel Identification Number", foreign_key="parcel.parcel_id", index=True
    )
    conv_num: int | None = Field(description="Conveyance Number")
    sale_date: date = Field(description="Sale Date", index=True)
    sale_price: float = Field(description="Sale Price", index=True)
    old_owner: str = Field(description="Old Owner Name", index=True)
    new_owner: str = Field(description="New Owner Name", index=True)
    parcel_location: str = Field(description="Parcel Location")
    mailing_name: str = Field(description="Mailing Name")
    # # mailing_name2: str = Field(description="Mailing Name 2")
    mailing_address: str = Field(description="Mailing Address")
    parcel_class: ParcelClass = Field(description="Parcel Class")
    acres: float = Field(description="Parcel Acreage")
    taxable_land: int = Field(description="35% Taxable Land Value")
    taxable_building: int = Field(description="35% Taxable Building Value")
    taxable_total: int = Field(description="35% Taxable Total Value")
    assessed_land: int | None = Field(description="100% Assessed Land Value")
    assessed_building: int | None = Field(description="100% Assessed Building Value")
    assessed_total: int | None = Field(description="100% Assessed Total Value")
    sale_type: SaleType | None = Field(description="Type of sale")
    sale_validity: str | None = Field(description="Sale Validity")
    # # dayton_credit
    deed_reference: str | None = Field(description="Deed Reference")
    neighborhood: str | None = Field(description="Neighborhood Number", index=True)


class Transaction(TransactionBase, table=True):
    """Representation of an item"""

    # The county has no stable row id and publishes each sale several times:
    # in weekly ZIPs shortly after recording, then in every monthly re-export
    # of the yearly file. Snapshots drift (the weekly OWNERNAME1 is often the
    # owner at export time rather than the buyer), so a sale is identified by
    # its conveyance: parcel, date and conv_num, plus the seller because the
    # county occasionally records two chained same-day conveyances under one
    # conv_num. The 2001-2002 files have no conv_num at all; those rows never
    # drift (the files are final), so they keep the full-row key.
    __table_args__ = (
        Index(
            "uq_transaction_conveyance",
            "parcel_id", "sale_date", "conv_num", "old_owner",
            unique=True,
            sqlite_where=text("conv_num IS NOT NULL"),
            postgresql_where=text("conv_num IS NOT NULL"),
        ),
        Index(
            "uq_transaction_legacy",
            "parcel_id", "sale_date", "sale_price", "old_owner", "new_owner",
            unique=True,
            sqlite_where=text("conv_num IS NULL"),
            postgresql_where=text("conv_num IS NULL"),
        ),
    )

    # Which county export last wrote this row. "yearly" rows are authoritative
    # and overwrite earlier snapshots; "weekly" rows are provisional until the
    # yearly export covering them arrives (see db/ingestors.py).
    source: str = Field(
        default=SOURCE_WEEKLY,
        sa_column_kwargs={"server_default": SOURCE_WEEKLY},
        description="County export that last wrote this row: yearly or weekly",
    )

    # Define the relationship
    parcel: Parcel = Relationship(back_populates="transactions")


class TransactionResponse(TransactionBase):
    parcel: ParcelResponse | None = None


class DataFile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True, index=True)
    filename: str = Field(description="The ingested file name (no directory)")
    ingested_at: datetime = Field(description="The time the file was ingested")
    # SHA-256 of the file's bytes: the current-year file is re-exported under
    # the same name, so a changed hash means new data to ingest.
    content_hash: str | None = Field(default=None, description="SHA-256 of the file")



class ParcelListModel(BaseModel):
    count: int
    entities: list[Parcel]


class TransactionListModel(SQLModel):
    count: int
    entities: list[TransactionResponse]

class OwnerStats(BaseModel):
    owner_name: str
    transaction_count: int
    total_spent: float
    avg_price: float


class NeighborhoodStats(BaseModel):
    neighborhood: str
    transaction_count: int
    total_volume: float
    avg_price: float
    median_price: float
    min_price: float
    max_price: float


class FlipResult(BaseModel):
    parcel_id: str
    parcel_location: str
    buy_date: date
    sell_date: date
    buy_price: float
    sell_price: float
    hold_days: int
    profit: float
    profit_pct: float
    buyer: str
    seller: str


class DistressedSale(BaseModel):
    id: int
    parcel_id: str
    parcel_location: str
    sale_date: date
    sale_price: float
    assessed_total: int
    assessed_ratio: float
    new_owner: str
    neighborhood: str | None
    parcel_class: ParcelClass


class OwnerHoldings(BaseModel):
    owner_name: str
    parcel_count: int
    total_acres: float
    total_assessed_value: float


class NetSellerStats(BaseModel):
    owner_name: str
    buy_count: int
    sell_count: int
    net: int


class NeighborhoodTrend(BaseModel):
    neighborhood: str
    year: int
    median_price: float
    transaction_count: int
    yoy_change_pct: float | None


class StaleParcel(BaseModel):
    parcel_id: str
    parcel_location: str
    parcel_class: ParcelClass
    last_sale_date: date
    last_sale_price: float
    years_since_sale: float


class AcquisitionWave(BaseModel):
    owner_name: str
    window_start: date
    window_end: date
    acquisition_count: int
    total_spent: float


class RelatedOwner(BaseModel):
    owner_name: str
    shared_address: str
    transaction_count: int


class OwnerYearActivity(BaseModel):
    year: int
    buy_count: int
    sell_count: int
    total_spent: float
    total_received: float


class OwnerProfile(BaseModel):
    owner_name: str
    first_activity: date | None
    last_activity: date | None
    total_buys: int
    total_sells: int
    median_hold_days: float | None
    activity: list[OwnerYearActivity]
    related_owners: list[RelatedOwner]


class CompSale(BaseModel):
    parcel_id: str
    parcel_location: str
    sale_date: date
    sale_price: float
    acres: float


class ParcelComps(BaseModel):
    neighborhood: str | None
    parcel_class: ParcelClass | None
    median_price: float | None
    comps: list[CompSale]


class DataHealth(BaseModel):
    total_transactions: int
    total_parcels: int
    latest_sale_date: date | None
    last_ingest_at: datetime | None
    geocoded_pct: float
    market_sale_pct: float


class MarketStatsBucket(BaseModel):
    period: str
    period_start: date
    transaction_count: int
    median_price: float
    avg_price: float
    total_volume: float
    median_price_per_sqft: float | None = None


class OwnerParcel(BaseModel):
    parcel_id: str
    parcel_location: str
    parcel_class: ParcelClass
    acres: float
    last_sale_date: date
    last_sale_price: float
    assessed_total: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    # Parcels acquired in the same conveyance as this one (including itself).
    # >1 means last_sale_price is the whole deal's price, not this parcel's.
    deal_size: int = 1