from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel
from sqlmodel import Field, Relationship, SQLModel


class ParcelClass(Enum):
    """Type of Parcel"""
    A="Agricultural"
    C="Commercial"
    E="Exempt"
    I="Industrial"
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


class Parcel(ParcelBase, table=True):

    # Defines the relationship back to Transaction, referencing the class by string.
    transactions: list["Transaction"] = Relationship(back_populates="parcel")


# A simple model just for the nested lat/long
class ParcelResponse(ParcelBase):
    ...

class TransactionBase(SQLModel):
    # Years 2001-2002 don't have the fields that are marked as optional (beside the id)
    id: int | None = Field(default=None, primary_key=True, index=True)
    parcel_id: str = Field(description="Parcel Identification Number", foreign_key="parcel.parcel_id")
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

    # Define the relationship
    parcel: Parcel = Relationship(back_populates="transactions")


class TransactionResponse(TransactionBase):
    parcel: ParcelResponse | None = None


class DataFile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True, index=True)
    filename: str = Field(description="The ingested file name")
    ingested_at: datetime = Field(description="The time the file was ingested")



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
    avg_price: float
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