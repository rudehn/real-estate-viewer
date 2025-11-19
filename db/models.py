from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel
from sqlmodel import Field, SQLModel



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


class Transaction(SQLModel, table=True):
    """Representation of an item"""

    # Years 2001-2002 don't have the fields that are marked as optional (beside the id)
    id: int | None = Field(default=None, primary_key=True, index=True)
    parcel_id: str = Field(description="Parcel Identification Number")
    conv_num: int | None = Field(description="Conveyance Number")
    sale_date: date = Field(description="Sale Date")
    sale_price: float = Field(description="Sale Price")
    old_owner: str = Field(description="Old Owner Name")
    new_owner: str = Field(description="New Owner Name")
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
    neighborhood: str | None = Field(description="Neighborhood Number")

class Parcel(SQLModel, table=True):
    # id: int | None = Field(default=None, primary_key=True, index=True)
    parcel_id: str = Field(description="Parcel Identification Number", primary_key=True, index=True)
    parcel_location: str = Field(description="Parcel Location")
    parcel_class: ParcelClass = Field(description="Parcel Class")
    acres: float = Field(description="Parcel Acreage")
    # owner: str = Field(description="Owner Name")


class DataFile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True, index=True)
    filename: str = Field(description="The ingested file name")
    ingested_at: datetime = Field(description="The time the file was ingested")



class ParcelListModel(BaseModel):
    count: int
    entities: list[Parcel]

class TransactionListModel(BaseModel):
    count: int
    entities: list[Transaction]