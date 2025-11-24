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