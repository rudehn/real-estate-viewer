# Montgomery County data sources

All data comes from the Montgomery County Treasurer file downloads page:
https://go.mcohio.org/applications/treasurer/search/filedownloads.cfm

Files are served from `https://go.mcohio.org/applications/treasurer/search/data/<Folder>/<file>`.
Each dataset's popup listing is `fdpopup.cfm?dtype=<code>`.

| Dataset | Popup code | Folder | Cadence | Example file |
|---|---|---|---|---|
| Weekly sales | WS | `Weekly` | Weekly | `SALES_20260913_TO_20260919.zip` |
| Monthly sales | MS | `Monthly` | Monthly | `SALES_20260801_TO_20260831.zip` |
| Yearly sales | YS | `Yearly` | Yearly | `SALES_2025.zip` |
| Tax roll | TR | `Taxroll` | Daily since 2022 | `TAXROLL_20260923.zip` |
| Delinquent taxes | DQ | `Delq` | Monthly since 2021, sparse back to 2005 | `Delq_20260831.zip` |
| District listings | ST | `Asmt` | Monthly | `Dist_Listing_20260831.zip` |
| CAMA characteristics | CC | `Cama` | Monthly | `Cama_Files_20260831.zip` |
| Available tax refunds | RF | `Taxref` | Daily | `TAXREF_20260923.zip` |
| Neighborhood codes | NC | `nbhd_code_monthly` | Monthly since 2025-05 | `neighborhood_codes_20260901.htm` |

## Findings

These reports come from profiling the 2026-08/09 snapshots.
They record schemas, join rates to our `parcel` table, value distributions, data quality problems, and feature ideas.

- [tax-roll-and-delinquency.md](tax-roll-and-delinquency.md): TAXROLL, Delq, TAXREF, district listings, neighborhood codes.
- [cama-values-and-ownership.md](cama-values-and-ownership.md): APRVAL, ASMT, CHARGE, SASMT, PROJECT, HMSD, OWNDAT, MAILDAT, LEGDAT, NBHD, SALES.
- [cama-buildings-and-permits.md](cama-buildings-and-permits.md): DWELL, ADDN, PARDAT, LAND, OBY, PERMIT, commercial and agricultural tables.
- [cama-building-column-maps.md](cama-building-column-maps.md): byte offsets for the building tables, including corrections where the county's layout PDF is wrong.

## Prototype parsers

`prototype-parsers/` holds the stdlib-only parsers written during profiling.
They stream fixed-width CAMA tables straight from the zip and handle wrapped records, overflow lines, cp1252, and `###` numeric overflow.
They are reference material for the production ingestors, not production code.
`ZIP_PATH` points next to the script; pass a path explicitly when using them.

## Lookups

- `lookups/neighborhood_names_20260901.json`: official neighborhood code to name map (1,284 codes).
- `lookups/tax_district_names.json`: tax district names scraped from utility rows of the tax roll (73 of about 100 districts).
