# CAMA building / physical tables - findings

Parser `cama_parse.py` (stdlib, streams from zip): `iter_table(name)` for DWELL, PARDAT, LAND, AGLAND, OBY, ADDN, PERMIT, COMDAT, COMAPT, COMFEAT, COMINTEXT; `load_lookup(name)`; `load_aedit()` -> {(table, field): {value: desc}} (1,055 decode lists). Column maps: `_work/cama_building_colmaps.md` (bold = differs from PDF). Scripts: `_work/`.

## Format gotchas
- Oracle SQL*Plus spools, CRLF, cp1252. DWELL/OBY records span 3 physical lines (wrapped last date + blank). Record starts on `^[A-Z]\d\d`. 9 PERMIT notes contain CR/LF. `###` = numeric overflow -> None.
- PDF wrong: DWELL heat is 2 wide (everything from grade on = PDF+1); OBY grade 3 wide, obymod 4 wide, cndcmplx 30 (from cline on = PDF+8); OBY card/lline swapped; ADDN trailing dates swapped; PERMIT num = permit number, permdt = permit date.
- Decodes (style, fuel, heatsys, LUC, influence, OBY cond) live in AEDIT.DAT.
- Year built heaping: 1919 (4,096 rows) = "pre-1920" placeholder; 1900 inflated.
- Single snapshot (TY2025): historical sales get today's building characteristics.

## Join (parid rstrip == parcel.parcel_id)
PARDAT covers 97.8% app parcels; LAND 96.7%; DWELL 77.8% of app parcels / 87.5% of residential (193,231 of 214,648 priced residential sales); PERMIT 41.7%; OBY 37.5%; COMDAT 5.3%.

## DWELL (189,390 rows; key parid+card; 99.7% single dwelling)
- sfla quartiles 1,080 / 1,414 / 1,904. Beds 3=55%, 4=20%, 2=20%. Full baths 1=49%, 2=45%. Half 0=66%, 1=32%. Stories 1.0 70%, 2.0 26%.
- Style: Ranch 39.6%, Old Style 11.3%, Cape Cod 10.9%, Colonial 10.1%, Bungalow 8.2%, Condo 5.5%, Split 4.5%, Duplex 3.2%.
- Exterior brick 38%, alum/vinyl 31%. Basement full 43%, none 38%, part 13%, crawl 7%. Central A/C 78%. Gas 86%.
- Grade C 37%, C+ 25%, C- 12%, B-/B ~10%, A ~2%. CDU AV 79%, FR 9%, GD 8.3%.
- Year built peaks 1950s (38k) / 1960s (32k). Remodel fields too sparse.

## ADDN (823k lines; building sketch)
Line 0 main body (area == flr1area). Vector strings drawable (e.g. `A0CU20R45D20L45`). Codes (inferred): living 10/15/16/20; attached garage 13/23; porch/deck 11/12/21/22/24/30/31/33/34/35; roof 29/32; lower 50. Garages: attached 53%, detached 27.8%, basement 4.4%, none 17.3%.

## PARDAT (259,808, 1 per parcel)
LUC 510 SF 157,799; 500 vacant res 21,992; 550 condo 12,184; 511 SF acreage 12,054; 520 two-family 4,749; 401 apartments 3,131. nbhd == transaction.neighborhood. acres 0 on 43% (use LAND). partial flags D new dwelling 1,219, I addition 612, R remodel 202, X demo 27.

## LAND (286k lines)
Frontage median 50 ft, depth 130, lot sf median 8,000, acres median 0.18.

## OBY (135k items / 96k parcels)
Detached garage RG1 54,478; shed 15,518; paving 14,546; pole bldg 5,387; pools RP* 4,293; mobile homes 2,271.

## PERMIT (253,624; 1993-2026; 106k parcels)
- ~7-13k/yr (6.1k 2023 dip; 5.2k 2026 through Aug). Top types: ELECTRIC, AC, DWLG, FURNACE, GAS LINE, ALT, ADDN 11.0k, DEMO 9.6k, REMODEL 8.1k, FENCE, SHED, DECK, DET GAR 3.9k, POOL 2.2k, NEW DWLG 2.5k.
- 1,267 spellings; blank on 55% since 2024 -> normalize from permit-number prefix (MECR/MECC, ELER/ELEC, BLDR/BLDC, GASR, FPR, PLMR, DMG) or note2.
- Amount filled 47% (outliers up to $500M). flag C 92.6% closed, O 7.3% open.
- Uneven coverage: permits/100 parcels since 2015: suburbs 50-154 vs Dayton 14, Kettering 18, Oakwood 17 -> show coverage indicator.

## Commercial / ag
COMDAT 18k cards (garden apts 4,747, warehouse, office, mfg, retail); COMINTEXT gross area; COMFEAT; COMAPT 44,771 units with rent (median $5,640/yr); AGLAND 3,220 CAUV parcels.

## Feature ideas (ranked)
1. House profile card (sfla, beds, baths, basement, year built, style, grade, condition, exterior, A/C, garage, pool, outbuildings, lot). Low effort, very high value.
2. $/sqft everywhere: 2024+ median $142; $74 (2011) -> $147 (2025); 358 nbhds with 10+ sales.
3. Comps engine (nbhd/radius, style, sfla +/-20%, beds, baths, year +/-10, grade, recency).
4. Permit-aware flips: 13.8% of <=2yr 30%+ resales have a permit between vs 5.9% others; cosmetic vs renovation label.
5. Permit activity maps/trends (demo vs new, remodel, pool, solar) with coverage indicator.
6. Housing-stock maps by nbhd (median year built, dominant style, % brick/A/C/basement/attached garage, median sqft).
7. New-construction / teardown tracker (4,616 sales since 2015 within a year of yrblt).
8. Floor-plan footprint SVG from ADDN vectors.
Also: hedonic price index, lot size filters, multifamily rent (COMAPT), condo complexes, search filters (beds/baths/pool/A/C).

## Suggested ingestion shape
`dwelling`, `parcel_feature` (OBY + non-living ADDN), `permit` (normalized category), `parcel_detail` (PARDAT + LAND). Idempotent create, full refresh per snapshot.
