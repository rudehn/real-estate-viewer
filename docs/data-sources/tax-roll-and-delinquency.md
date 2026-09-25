# Tax data findings (TAXROLL, Delq, TAXREF, District listings, Neighborhood codes)

Artifacts: `tax/tax.db` (tables taxroll, delq, taxref, dist; view `tr` with computed bill), loaders, `nbhd_county_20260901.json`, `txdst_names_from_utility.json`, `delq_ts.json`.

## TAXROLL (most valuable)
- 254,693 rows, 1 per parcel, 82 cols, TXYR 2025, cp1252. All classes (R 214,547 / C 19,636 / E 13,942 / A 3,738 / I 2,656 / U 174).
- Undocumented extra cols: CITYNAME (postal), OWNOCC, PARCEL LOCATION ZIP, CENSUS TRACT (block group, 153 tracts).
- Annual net bill = sum over halves of ADJ+RLBK+HMSD+HMRB+SPASMTS+DAYCRDT (verified vs rates 99.97%). FULLYRAMTDUE is remaining balance, not the bill.
- County total $1.078B; residential median bill $2,639 (p90 $6,656). Residential tax per $1,000 market value 15-31 by district.
- OWNOCC=Y 135,887 (69% of dwellings). HMSDFLAG 33,157. RENTALREG: only 13.1k of 53.5k non-owner-occupied dwellings registered.
- FRCLSR (foreclosure date) 1,086 parcels (374 in 2026). Abated/TIF 2,560. CAUV 3,221.
- YRBL and SQ. FT. >99.8% filled for single-family (median 1,314 sqft). Outliers: YRBL 1790/2048/2103.
- LAST SALE: 14,376 parcels newer than app's latest sale (2026-03-13); price matches 97.3% when dates match; PRICE blank for 77,619.
- MORTCO: 91% blank; 99xx are status codes; no lender lookup - mortgage concentration not feasible.
- Snapshots: daily since 2022 (25-36 MB zip each).
- Trend across snapshots: owner-occ 140,319 -> 136,065 -> 135,887; homestead 40,766 -> 35,062 -> 33,157; rental reg 24,708 -> 21,088 -> 17,325; foreclosure-dated 288 -> 519 -> 1,086.
- Single-family median value $83.7k -> $142.2k, median bill $2,265 -> $2,962 (TY2018 -> TY2025).

## Delq
- 25,568 parcels (177 name spill lines). $213M NETDELQ over 13,353 parcels; 692 owe >$50k.
- CERTDLQYR 1957-2025. No payment-plan field; MORTCO 9999 = delinquent no agreement (inferred), 992x = likely payment plans (inferred).
- Residential delinquency: Trotwood 27.5%, Dayton 24%, suburbs 2-4%.
- Time series feasible: same 62-col schema 2005-2026; monthly Sep 2021-Aug 2026 (Dec 2022 missing, 20220331 empty zip) + 9 older points; ~400 MB total. Compare same month per year (2024-25 inclusion change).
- Sample series (date: delinquent parcels, NETDELQ, foreclosures): 2005-01 21,052 $59M 450; 2014-05 27,012 $163M; 2021-09 28,806 $212M 244; 2024-09 24,692 $224M 825; 2026-08 13,353 $213M 1,078.

## TAXREF
- 381 unclaimed refunds, $391k, TY 2014-2023. Low value.

## District listings
- Same data as TAXROLL split into 86 district files, no assessment amounts. Adds nothing.

## Neighborhood codes
- 1,284 code->name pairs. App JSON (1,193) misses 93 (35 MH* parks), 39 names differ, 2 stale.
- 61.6% of app transactions have NULL neighborhood (all of 2001-2018); TAXROLL NBHD matches 99.8% where set -> backfill.

## Join rates (after stripping whitespace)
- app parcel -> TAXROLL 96.8% (misses: 1,281 manufactured-home IDs, ~4.4k retired/split). TAXROLL -> app 68% (~81k never sold in window). Delq -> app 62%.

## Top feature ideas
1. Parcel "Taxes & status" panel (bill breakdown, effective rate vs district, owner-occ/homestead/rental/abated/CAUV/appeal/delinquent/foreclosure badges, year built, sqft, LUC, census tract).
2. Distress / pre-foreclosure watchlist + heat map (FRCLSR, years delinquent, NETDELQ, status codes), linked to subsequent sales.
3. Owner-occupancy / investor map (OWNOCC, HMSD, entity names, out-of-state mail, rental registration gap).
4. Delinquency time series (county, neighborhood, parcel).
5. Effective tax rate map by district + "taxes on a $X home" calculator.
6. Refresh neighborhood names; backfill NULL transaction neighborhoods.
7. Full parcel coverage (81k never-sold parcels), $/sqft, catch missed sales.
8. Value and tax history per parcel from one TAXROLL snapshot per year.

## Gotchas
cp1252, CRLF, padded quoted strings, zero-padded signed numbers, some quoted/blank numerics, DD-MON-YY dates spanning 1964-2026 (%y pivot wrong), name spill lines in Delq/district files, January snapshots have zeroed current charges, empty zip, CITYNAME is postal city, district names not published (73/100 scrapeable from U-class rows).
