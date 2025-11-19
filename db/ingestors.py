import csv
import datetime
import glob

from sqlmodel import Session, select, insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from db.models import Transaction, SaleType, DataFile, Parcel
from db.engine import engine, get_session

def ingest_data_files(directory: str):
    ingest_yearly_files(directory + "/yearly/**/SALES_*.csv")

def ingest_yearly_files(pathname: str):
    csv_files = glob.glob(pathname, recursive=True)
    print("Csv files", csv_files)
    for csv_file in csv_files:
        ingest_yearly_file(csv_file)

def ingest_yearly_file(filename: str):
    # Add safeguards to make sure we don't re-ingest an already processed data file
    print(f"Ingesting {filename}")
    
    with Session(engine) as session:
        datafile = session.exec(select(DataFile).filter(DataFile.filename==filename)).first()
        if datafile:
            print(f"File {filename} has already been processed")
            return
        
        with open(filename, "r") as f:
            reader = csv.DictReader(f)
            mappings = []
            parcels = {}
            for row in reader:
                # Some of the data files have spaces in the headers and records, like "PARID    "
                # So clean up the headers here, and clean up the records below
                cleaned_row = {k.strip():v.strip() for k,v in row.items()}
                # Guard against empty lines of ,,,,,,,,,,
                if not any(cleaned_row.values()):
                    continue
                conv_num = cleaned_row.get("CONVNUM")
                assessed_land = cleaned_row.get("ASMTLAND")
                assessed_building = cleaned_row.get("ASMTBLDG")
                assessed_total = cleaned_row.get("ASMTTOTL")
                sale_type = cleaned_row.get("SALETYPE")
                deed_reference = cleaned_row.get("DEEDREFERENCE")
                neighborhood = cleaned_row.get("NBHD")
                transaction ={
                        "parcel_id": cleaned_row["PARID"],
                        "conv_num": int(conv_num) if conv_num else None,
                        "sale_date": datetime.datetime.strptime(row["SALEDTE"], "%d-%b-%y").date(),
                        "sale_price": float(cleaned_row["PRICE"]),
                        "old_owner": str(cleaned_row["OLDOWN"]),
                        "new_owner": str(cleaned_row["OWNERNAME1"]),
                        "parcel_location": str(cleaned_row["PARCELLOCATION"]),
                        "mailing_name": str(cleaned_row["MAILINGNAME1"]) + " " + str(cleaned_row["MAILINGNAME2"]),
                        "mailing_address": str(cleaned_row["PADDR1"]) + " " + str(cleaned_row["PADDR2"]) + " "+  str(cleaned_row["PADDR3"]),
                        "acres": str(cleaned_row["ACRES"]),
                        "parcel_class": str(cleaned_row["CLS"]),
                        "acres": float(cleaned_row["ACRES"]),
                        "taxable_land": int(cleaned_row["TAXLAND"]),
                        "taxable_building": int(cleaned_row["TAXBLDG"]),
                        "taxable_total": int(cleaned_row["TAXTOTAL"]),
                        "assessed_land": int(assessed_land) if assessed_land else None,
                        "assessed_building": int(assessed_building) if assessed_building else None,
                        "assessed_total": int(assessed_total) if assessed_total else None,
                        "sale_type": SaleType(sale_type.upper()) if sale_type else None,
                        "sale_validity": cleaned_row.get("SALEVALIDITY"),
                        "deed_reference": str(deed_reference) if deed_reference else None,
                        "neighborhood": str(neighborhood) if neighborhood else None,
                    }
                mappings.append(transaction)
                parcels[transaction["parcel_id"]] = {
                    "parcel_id": transaction["parcel_id"],
                    "parcel_location": transaction["parcel_location"],
                    "parcel_class": transaction["parcel_class"],
                    "acres": transaction["acres"],
                }
            session.bulk_insert_mappings(Transaction, mappings)
            # session.bulk_update_mappings
            # session.exec(insert(Transaction).execution_options(render_nulls=True, insertmanyvalues_page_size=10).values(mappings), execution_options={"insertmanyvalues_page_size": 10})
            # session.exec(sqlite_insert(Parcel).on_conflict_do_nothing(index_elements=["parcel_id"]).execution_options(insertmanyvalues_page_size=100).values(list(parcels.values())))
            
            # For some reason the built in batching isn't working, so do it ourselves
            parcel_list = list(parcels.values())
            for i in range(0, len(parcel_list), 100):
                # call our helper to process a sub list
                sublist = parcel_list[i:i+100]
                session.exec(sqlite_insert(Parcel).on_conflict_do_nothing(index_elements=["parcel_id"]).values(sublist))
            

            #session.exec(sqlite_insert(Parcel).on_conflict_do_nothing(index_elements=["parcel_id"]).values(list(parcels.values())), execution_options={"insertmanyvalues_page_size": 100})
            session.add(DataFile(filename=filename, ingested_at=datetime.datetime.now()))
            session.commit()
