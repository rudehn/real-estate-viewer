# CAMA value / ownership / reference tables - findings

Source: Cama_Files_20260831.zip (iasWorld AA407 extract). Parser `cama_values_parse.py` (LAYOUTS with 1-based offsets; `iter_table(name)`; `nbhd_names()`), loader `load_cama_values.py` -> `cama_values.db`, analyses `_ratio.py`, `_occ.py`, code lookups `_aedit_dump.txt`, names `nbhd_names_cama.json`.

## Format gotchas
CRLF records; overflow continuation lines (blank-led, text at field column) in OWNDAT 1,007 / MAILDAT 809 / SALES 578 / NBHD 2,285 - parser merges them. cp1252. DD-MON-YY (pivot <=40 -> 20YY). NBHD repeats codes up to 11x, 249 conflicting names. OWNDAT Jur is 3 chars. PDF PARDAT labels shifted but positions correct.

## Snapshot semantics (no multi-year history)
APRVAL TY2025 values; ASMT 2026 reappraisal (100% and 35%); CHARGE/SASMT/HMSD TY2025; OWNDAT/MAILDAT/LEGDAT current; SALES only 2024-10-29..2025-12-31. Residential market value 31.34B -> 37.40B (+19.3%).

## Tables
- APRVAL 259,584 (join 97.8%): aprtot=aprland+aprbldg (100% value); revreas BOR appeal years B96-B25, TIF 2,932, ABA 984; revcode 1 cost / 3 override / 4 income. mktval is NOT a sale price.
- ASMT 259,959 (3 dup parids - sum): asmt*=0.35*apr*; farmland CAUV 3,304; 117 LUC codes named in AEDIT.
- CHARGE 260,546 (6 dups): annual bill = orgadj+orgrlbk+orghmsd+orghmrb+saorg1+saorg2 (matches nettax within 1.4% for non-delinquent). SF median bill ~$3.5k; effective rate 1.69%-2.98% by district.
- SASMT 568,702 rows / 244,843 parcels + PROJECT 719: delinquent water/sewer 7.8k parcels $2.0M; weeds/nuisance 2.0k $3.1M; TIF 1.95k $29.8M; street lighting 56.9k; Downtown Dayton SID 973.
- HMSD 33,703: H homestead 27,988, D disability 3,558, V veteran 1,598, S/W surviving spouse. PII - aggregate only.
- OWNDAT/MAILDAT/LEGDAT ~260k: owners, mailing (mortco escrow 22.5k; paycode FORC 1,341, BKRP 470), situs; LEGDAT x/y EPSG:3735 on 248,987 parcels (median 32 m from app coords) - can fill 35.9k missing app coords.
- NBHD 1,544 codes, covers 100% of PARDAT.nbhd.
- SALES 22,688: adds deed type (GW 10,344, QC 3,780, SD sheriff 505, ...), instrument no., multi-parcel grouping (transno), value at sale.

## Answers
- (a) Owner-occupied = orghmrb<0 or orghmsd<0 or HMSD row. SF 72.3%; Dayton 57%, Washington Twp 87%; neighborhoods 15-96%. Credit lags new purchases.
- (b) Valid 2025 SF sales: 2026 value/price median 0.906 COD 8.4 (circular - model fit on these sales); 2025 values 0.733. Bottom quintile (<$113k) median 1.06, COD 37.6 - regressive. Dayton COD 23.9.
- (c) Only 2025 vs 2026. SF median +20%; Dayton +32.5%, Trotwood +38%, Huber Heights +11.5%; neighborhoods -17% to +83%. Longer history needs archived snapshots.
- (d) Names from NBHD. District = parcel_id[:3] (letter = jurisdiction: A Butler, B Vandalia, C Clay, D German, E Harrison, F Jackson, G Jefferson, H Trotwood, I Riverside, J Moraine, K Miami Twp/Miamisburg/W Carrollton, L Perry, M Englewood/Union/Clayton, N Kettering, O Washington/Centerville, P Huber Heights, Q Oakwood, R Dayton). District names: static lookup / `tax/txdst_names_from_utility.json`.
- (e) Bill formula above; effective rate = bill / aprtot.

## Feature ideas (ranked)
1. Owner-occupied vs investor share by neighborhood (map + table).
2. LLC/investor buyer share over time.
3. Parcel "county value" panel: 2025 vs 2026 value, % change, appeals, TIF, ratio to last sale.
4. Assessment equity dashboard (value vs price, COD/PRD by decile & district).
5. 2026 reappraisal change map by neighborhood.
6. Tax burden explorer (components, effective rate by district, special assessments).
7. Distress watchlist (weeds/nuisance, delinquent utilities, delinquency, FORC/BKRP, sheriff deeds).
8. Homestead exemption mix; deed-type filter on sales.

## App-side issues found
- transaction.neighborhood NULL on 251k/408k rows (PARDAT/TAXROLL can fill).
- 34,463 parcels latitude=0.0 and 4,366 NULL (LEGDAT fills 35.9k).
- assessed_*/taxable_* column names swapped vs Ohio terms (assessed_total holds 100% value).
- 3,946 retired parcel IDs.
