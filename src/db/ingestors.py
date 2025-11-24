import csv
import datetime
import glob
import asyncio

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from db.models import Transaction, SaleType, DataFile, Parcel, ParcelClass
from db.engine import engine

async def ingest_data_files(directory: str):
    await ingest_yearly_files(directory + "/yearly/**/SALES_*.csv")

async def ingest_yearly_files(pathname: str):
    csv_files = glob.glob(pathname, recursive=True)
    print(f"Found files: {csv_files}")
    for csv_file in csv_files:
        await ingest_yearly_file(csv_file)

async def ingest_yearly_file(filename: str):
    print(f"Processing {filename}...")
    
    # Create a local async session for this task
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # 1. Check if file exists
        statement = select(DataFile).where(DataFile.filename == filename)
        result = await session.exec(statement)
        if result.first():
            print(f"Skipping {filename} (Already Processed)")
            return

        # 2. Read CSV (Sync operation, but fast enough for local files)
        # For massive files, we might run this in a thread, but simple read is fine here
        mappings = []
        parcels = {}
        
        with open(filename, "r", encoding="utf-8-sig") as f: # utf-8-sig handles BOM
            reader = csv.DictReader(f)
            for row in reader:
                cleaned_row = {k.strip():v.strip() for k,v in row.items()}
                if not any(cleaned_row.values()):
                    continue
                
                try:
                    # conversions...
                    s_price = float(cleaned_row.get("PRICE", 0))
                    acres_str = cleaned_row.get("ACRES", "0")
                    acres = float(acres_str) if acres_str else 0.0
                    conv_num = cleaned_row.get("CONVNUM")
                    
                    # Handle Date Parsing safely
                    sale_date_str = row["SALEDTE"]
                    sale_date = datetime.datetime.strptime(sale_date_str, "%d-%b-%y").date()
                    
                    # Safely get Enum
                    p_class_str = cleaned_row.get("CLS", "R")
                    # Simple mapping fallback
                    try:
                        p_class = ParcelClass[p_class_str]
                    except:
                        p_class = ParcelClass.R # Default or Log error

                    assessed_land = cleaned_row.get("ASMTLAND")
                    assessed_building = cleaned_row.get("ASMTBLDG")
                    assessed_total = cleaned_row.get("ASMTTOTL")
                    sale_type = cleaned_row.get("SALETYPE")
                    deed_reference = cleaned_row.get("DEEDREFERENCE")

                    transaction = Transaction(
                        parcel_id=cleaned_row["PARID"],
                        conv_num=int(conv_num) if conv_num else None,
                        sale_date=sale_date,
                        sale_price=s_price,
                        old_owner=cleaned_row.get("OLDOWN", ""),
                        new_owner=cleaned_row.get("OWNERNAME1", ""),
                        parcel_location=cleaned_row.get("PARCELLOCATION", ""),
                        mailing_name=cleaned_row.get("MAILINGNAME1", ""),
                        mailing_address=cleaned_row.get("PADDR1", ""),
                        parcel_class=p_class,
                        acres=acres,
                        taxable_land=int(cleaned_row.get("TAXLAND", 0)),
                        taxable_building=int(cleaned_row.get("TAXBLDG", 0)),
                        taxable_total=int(cleaned_row.get("TAXTOTAL", 0)),
                        
                        assessed_land=int(assessed_land) if assessed_land else None,
                        assessed_building=int(assessed_building) if assessed_building else None,
                        assessed_total=int(assessed_total) if assessed_total else None,
                        sale_type=SaleType(sale_type.upper()) if sale_type else None,
                        sale_validity=cleaned_row.get("SALEVALIDITY"),
                        deed_reference=cleaned_row.get("DEEDREFERENCE"),
                        neighborhood=cleaned_row.get("NBHD")
                    )
                    mappings.append(transaction)
                    
                    # Prepare parcel for upsert
                    parcels[transaction.parcel_id] = {
                        "parcel_id": transaction.parcel_id,
                        "parcel_location": transaction.parcel_location,
                        "parcel_class": transaction.parcel_class,
                        "acres": transaction.acres
                    }
                except Exception as e:
                    print(f"Error parsing row: {e}")
                    continue

        # 3. Bulk Insert Transactions
        if mappings:
             # SQLModel bulk insert for SQLite isn't fully async optimized, 
             # but add_all + commit works well
            session.add_all(mappings)
            
            # 4. Upsert Parcels
            parcel_values = list(parcels.values())
            # Chunking for SQLite limits
            chunk_size = 100
            for i in range(0, len(parcel_values), chunk_size):
                chunk = parcel_values[i:i+chunk_size]
                stmt = sqlite_insert(Parcel).values(chunk)
                stmt = stmt.on_conflict_do_nothing(index_elements=["parcel_id"])
                await session.exec(stmt)

            # 5. Mark file as ingested
            session.add(DataFile(filename=filename, ingested_at=datetime.datetime.now()))
            
            await session.commit()
            print(f"Committed {len(mappings)} transactions from {filename}")

