# Greene County ArcGIS REST API Integration

## Summary

Add Greene County, Ohio real estate data by pulling parcel and sales data from their public ArcGIS REST API. Data is mapped into the existing `Transaction` and `Parcel` models and ingested via a new CLI command.

## Data Source

- **Endpoint:** `https://gis.greenecountyohio.gov/webgis2/rest/services/OpenData/OpenData/MapServer/1/query`
- **Format:** JSON (`f=json`)
- **Max records per request:** 2000 (server-enforced)
- **Filter:** `Sale_Price > 0` to skip parcels with no recorded sale
- **Pagination:** `resultOffset` incremented by `resultRecordCount` until `exceededTransferLimit` is false

## Limitations

- The ArcGIS layer provides **one sale per parcel** (the most recent). Historical transaction chains are not available from this source.
- Analytics that depend on transaction history (flip detection, investor buy/sell tracking over time) will have limited depth for Greene County data.

## Architecture

### New file: `src/services/greene_county.py`

Single async function `ingest_greene_county()` that:

1. Checks `DataFile` for an entry named `greene_county_arcgis_YYYY-MM-DD`. If found, skips (already ingested today).
2. Paginates the ArcGIS REST API with `resultOffset` / `resultRecordCount=2000`.
3. For each batch of features, maps ArcGIS attributes to `Transaction` and `Parcel` model instances.
4. Bulk inserts Transactions via `session.add_all()`.
5. Upserts Parcels via `sqlite_insert(...).on_conflict_do_nothing()` in chunks of 100.
6. Records a `DataFile` entry to prevent duplicate ingestion on the same day.

### Field Mapping

| ArcGIS Field         | Transaction / Parcel Field | Notes                              |
|----------------------|----------------------------|------------------------------------|
| `Parcel_Id`          | `parcel_id`                |                                    |
| `Owner_Name`         | `new_owner`                |                                    |
| `Property_Address`   | `parcel_location`          |                                    |
| `Sale_Date`          | `sale_date`                | Unix timestamp in ms -> date       |
| `Sale_Price`         | `sale_price`               |                                    |
| `Class`              | `parcel_class`             | Map to `ParcelClass` enum          |
| `Acres`              | `acres`                    |                                    |
| `Assessed_Land`      | `assessed_land`            |                                    |
| `Assessed_Buildings` | `assessed_building`        |                                    |
| `Assessed_Total`     | `assessed_total`           |                                    |
| `Neighborhood`       | `neighborhood`             |                                    |
| `Valid_Sale`         | `sale_validity`            |                                    |
| (not available)      | `old_owner`                | Set to `""`                        |
| (not available)      | `conv_num`                 | Set to `None`                      |
| (not available)      | `taxable_land/building/total` | Set to `0`                      |
| (not available)      | `sale_type`                | Set to `None`                      |
| (not available)      | `deed_reference`           | Set to `None`                      |
| (not available)      | `mailing_name`             | Set to `""`                        |
| (not available)      | `mailing_address`          | Set to `""`                        |

### New CLI command: `ingest-greene`

Added to `src/cli.py`:

```python
@app.command()
def ingest_greene(log_level: str = ...):
    """Download and ingest Greene County sales from ArcGIS REST API."""
    asyncio.run(ingest_greene_county())
```

### Query Parameters

```
where=Sale_Price>0
outFields=Parcel_Id,Owner_Name,Property_Address,Sale_Date,Sale_Price,Valid_Sale,Class,Acres,Assessed_Land,Assessed_Buildings,Assessed_Total,Neighborhood
returnGeometry=false
f=json
resultRecordCount=2000
resultOffset=<incremented>
orderByFields=Sale_Date DESC
```

## No Model Changes

All data maps to existing `Transaction`, `Parcel`, and `DataFile` models without modification.

## Error Handling

- HTTP errors on individual pages log a warning and stop pagination (partial data is committed).
- Individual record parse failures are logged and skipped (same pattern as Montgomery County ingestor).

## Testing

- Verify pagination works end-to-end by running `python cli.py ingest-greene`.
- Confirm records appear in the database and existing API endpoints return Greene County data alongside Montgomery County data.
