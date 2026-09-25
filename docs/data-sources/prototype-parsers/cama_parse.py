"""Streaming parser for the Montgomery County (OH) CAMA fixed-width export.

Usage:
    from cama_parse import iter_table
    for row in iter_table("DWELL"):
        ...

    python3 cama_parse.py DWELL 5      # print the first 5 parsed rows

Layout source: Cama_Data_Layout.pdf ("AA407 Data File Description"), with
corrections verified against the 2026-08-31 export (see FIX notes below and
FINDINGS_cama_building.md).

File framing (verified):
  * The .DAT files are Oracle SQL*Plus spools: CRLF line endings, trailing
    spaces trimmed on every physical line.
  * Records wider than the spool LINESIZE wrap: the trailing column(s) that did
    not fit are emitted on continuation line(s), and wrapped records are then
    separated by an empty line.  Tables affected: DWELL and OBY (the WEN
    date sits on its own line).  All other data tables are one line/record.
  * A few PERMIT notes contain embedded CR/LF, which splits the record; the
    stray tail is attached to the preceding record as row["_overflow"].
  * Numeric values wider than the spool column print as '###' (seen in OBY
    units/meas1, COMDAT bldnum, COMFEAT meas/ofnum); parsed as None.
  * Values are right-aligned numerics / left-aligned text.  Dates are
    DD-MON-YY.  Decimal numbers can have no leading zero (".2900").
  * Encoding: Windows-1252 (smart quotes 0x92/0x94 appear in PERMIT and
    PARDAT notes); decoded as cp1252 with errors='replace'.

Parid format "A01 00101 0001" (14 chars, space padded to 30) matches the app's
parcel.parcel_id directly after rstrip().
"""
from __future__ import annotations

import datetime as _dt
import os
import re
import sys
import zipfile
from typing import Iterator

HERE = os.path.dirname(os.path.abspath(__file__))
ZIP_PATH = os.path.join(HERE, "Cama_Files_20260831.zip")
ENTRY_FMT = "Cama_Files_20260831\\{}.DAT"

A, N, D = "A", "N", "D"  # alpha, numeric, date

# (name, start (1-based), length, type).  The first physical line of a record
# holds every column except those listed in CONTINUATION[table], which appear
# (in order, one per continuation line) on the following lines.
SPECS: dict[str, list[tuple[str, int, int, str]]] = {
    "DWELL": [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("card", 37, 5, N),
        ("taxyr", 42, 5, N), ("seq", 47, 4, N), ("stories", 51, 4, N),
        ("extwall", 55, 2, A), ("style", 57, 2, A), ("yrblt", 59, 5, N),
        ("yrremod", 64, 5, N), ("rmtot", 69, 3, N), ("rmbed", 72, 3, N),
        ("rmfam", 75, 2, N), ("fixbath", 77, 3, N), ("fixhalf", 80, 3, N),
        ("fixaddl", 83, 3, N), ("fixtot", 86, 3, N), ("remkit", 89, 1, A),
        ("rembath", 90, 1, A), ("bsmt", 91, 1, A),
        # FIX (verified vs data + AEDIT decodes): heat is 2 wide, so heatsys
        # is at 94 and fuel at 95 (mostly "2" = GAS).  The PDF's 92/93/94
        # offsets are one short and every later column is PDF start + 1.
        ("heat", 92, 2, A), ("heatsys", 94, 1, A), ("fuel", 95, 1, A),
        ("grade", 96, 3, A),
        ("class", 99, 4, A), ("cddesc", 103, 2, A), ("attic", 105, 1, A),
        ("intext", 106, 1, A), ("unitno", 107, 10, A), ("rectype", 117, 1, A),
        ("flr1area", 118, 8, N), ("mastrimarea", 126, 7, N),
        ("unfinarea", 133, 7, N), ("recromarea", 140, 7, N),
        ("finbsmtarea", 147, 7, N), ("condovw", 154, 3, A),
        ("cndcmplx", 157, 30, A), ("cline", 187, 5, N), ("wbfp_o", 192, 3, N),
        ("wbfp_s", 195, 3, N), ("wbfp_pf", 198, 2, N), ("bsmtcar", 200, 2, N),
        ("msc1des", 202, 2, A), ("msc1num", 204, 3, N), ("msc2des", 207, 2, A),
        ("msc2num", 209, 3, N), ("condolvl", 212, 3, N),
        ("condotyp", 215, 4, A), ("mgfa", 219, 7, N), ("cdpct", 226, 4, N),
        ("cdu", 230, 2, A), ("depr", 232, 4, N), ("addnval", 236, 11, N),
        ("addnarea", 247, 7, N), ("adjarea", 254, 7, N),
        ("areafact", 261, 8, N), ("atticval", 269, 9, N),
        ("bgarval", 278, 9, N), ("bsmtval", 287, 9, N),
        ("cnstfact", 296, 7, N), ("cnstval", 303, 9, N),
        ("cndbaseval", 312, 11, N), ("cndadjval", 323, 11, N),
        ("finbsmtval", 334, 9, N), ("grdfact", 343, 5, N),
        ("heatval", 348, 9, N), ("mktadj", 357, 4, N), ("msc1val", 361, 9, N),
        ("msc2val", 370, 9, N), ("plumval", 379, 9, N),
        ("ufeatval", 388, 9, N), ("wbfpval", 397, 9, N),
        ("exmppct", 406, 7, N), ("exmpval", 413, 11, N), ("rcnld", 424, 11, N),
        ("adjrcnld", 435, 11, N), ("adjfact", 446, 8, N),
        ("rcnval", 454, 11, N), ("recval", 465, 9, N), ("sfla", 474, 7, N),
        ("shfact", 481, 7, N), ("subtval", 488, 10, N),
        ("trimval", 498, 9, N), ("unfinval", 507, 9, N),
        ("grmunits", 516, 4, N), ("grmrent", 520, 7, N),
        ("adjgrmfact", 527, 8, N), ("resgrmval", 535, 11, N),
        ("salekey", 546, 9, N), ("note1", 555, 40, A), ("note2", 595, 40, A),
        ("effyr", 635, 5, N), ("pctcomplete", 640, 4, N),
        ("user1", 644, 20, A), ("user2", 664, 20, A), ("user3", 684, 20, A),
        ("user4", 704, 20, A), ("user5", 724, 20, A), ("user6", 744, 20, A),
        ("user7", 764, 20, A), ("user8", 784, 20, A), ("user9", 804, 20, A),
        ("user10", 824, 20, A), ("deactivat", 844, 9, D),
        ("wen", 853, 9, D),
    ],
    "PARDAT": [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("taxyr", 37, 5, N),
        ("seq", 42, 4, N), ("mappre", 46, 4, A), ("mapsuf", 50, 2, A),
        ("rtepre", 52, 3, A), ("rtesuf", 55, 2, A), ("adrno", 57, 11, N),
        ("adrpre", 68, 2, A), ("adrsuf", 70, 8, A), ("adrsuf2", 78, 8, A),
        ("adrdir", 86, 2, A), ("adrstr", 88, 30, A), ("cityname", 118, 40, A),
        ("unitdesc", 158, 10, A), ("unitno", 168, 10, A), ("loc2", 178, 40, A),
        ("zip1", 218, 5, A), ("zip2", 223, 4, A), ("nbhd", 227, 8, A),
        ("class", 235, 4, A), ("luc", 239, 4, A), ("lucmult", 243, 1, A),
        ("livunit", 244, 4, N), ("tieback", 248, 30, A),
        ("tiebackcd", 278, 2, A), ("tielandpct", 280, 9, N),
        ("tiebldgpct", 289, 9, N), ("landisc", 298, 10, A),
        ("calcacres", 308, 14, N), ("acres", 322, 14, N),
        ("street1", 336, 2, A), ("street2", 338, 2, A), ("traffic", 340, 2, A),
        ("topo1", 342, 1, A), ("topo2", 343, 1, A), ("topo3", 344, 1, A),
        ("location", 345, 2, A), ("fronting", 347, 1, A), ("util1", 348, 2, A),
        ("util2", 350, 2, A), ("util3", 352, 2, A), ("ofcards", 354, 5, N),
        ("partial", 359, 1, A), ("bldgros_d", 360, 21, A),
        ("bldgros_v", 381, 11, N), ("mscbld_n", 392, 3, N),
        ("mscbld_v", 395, 11, N), ("notecd1", 406, 2, A),
        ("notecd2", 408, 2, A), ("note1", 410, 40, A), ("note2", 450, 40, A),
        ("note3", 490, 40, A), ("note4", 530, 40, A), ("rectype", 570, 1, A),
        ("pctown", 571, 9, N), ("chgrsn", 580, 2, A), ("salekey", 582, 9, N),
        ("deactivat", 591, 9, D), ("wen", 600, 9, D),
    ],
    "LAND": [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("lline", 37, 5, N),
        ("taxyr", 42, 5, N), ("seq", 47, 4, N), ("ltype", 51, 1, A),
        ("units", 52, 9, N), ("code", 61, 3, A), ("sf", 64, 11, N),
        ("fronact", 75, 7, N), ("froneff", 82, 5, N), ("depth", 87, 4, N),
        ("class", 91, 4, A), ("agflg", 95, 1, A), ("chgrsn", 96, 2, A),
        ("orate", 98, 11, N), ("brate", 109, 11, N), ("depfact", 120, 5, N),
        ("acres", 125, 15, N), ("exmpval", 140, 11, N), ("infl1", 151, 2, A),
        ("infl2", 153, 2, A), ("influ", 155, 4, N), ("price", 159, 11, N),
        ("exmppct", 170, 7, N), ("salekey", 177, 9, N), ("note1", 186, 40, A),
        ("wen", 226, 9, D),
    ],
    "AGLAND": [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("taxyr", 37, 5, N),
        ("seq", 42, 4, N), ("ca_ll", 46, 5, N), ("class", 51, 4, A),
        ("soil", 55, 5, A), ("use", 60, 5, A), ("acres", 65, 14, N),
        ("soilval", 79, 11, N), ("txsav", 90, 12, N), ("ovrval", 102, 12, N),
        ("info1", 114, 6, A), ("info2", 120, 6, A), ("deactivat", 126, 9, D),
        ("wen", 135, 9, D),
    ],
    "OBY": [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("seq", 37, 4, N),
        # FIX: PDF swaps the descriptions; data shows lline then card.
        ("lline", 41, 5, N), ("card", 46, 5, N), ("taxyr", 51, 5, N),
        ("code", 56, 3, A), ("yrblt", 59, 5, N), ("effyr", 64, 5, N),
        ("rectype", 69, 1, A), ("yrrem", 70, 5, N), ("area", 75, 9, N),
        ("areasum", 84, 11, N),
        # FIX (verified vs data, net +8 vs PDF): grade is 3 wide, obymod1-4
        # are 4 wide each, cndcmplx is 30 wide.  Everything from cline on is
        # PDF start + 8.
        ("grade", 95, 3, A), ("class", 98, 4, A), ("chgrsn", 102, 2, A),
        ("obymod1", 104, 4, A), ("obymod2", 108, 4, A),
        ("obymod3", 112, 4, A), ("obymod4", 116, 4, A), ("cond", 120, 1, A),
        ("cndflag", 121, 1, A), ("cndtype", 122, 4, A),
        ("cndcmplx", 126, 30, A), ("funct", 156, 1, A), ("cline", 157, 5, N),
        ("mktadj", 162, 4, N), ("units", 166, 3, N), ("depr", 169, 4, N),
        ("pctcomp", 173, 4, N), ("rate", 177, 14, N), ("rcn", 191, 11, N),
        ("adjfact", 202, 8, N), ("adjrcnld", 210, 11, N),
        ("exmppct", 221, 7, N), ("exmpval", 228, 11, N),
        ("rateovr", 239, 12, N), ("mhmake", 251, 20, A),
        ("mhmodel", 271, 20, A), ("salekey", 291, 9, N), ("meas1", 300, 4, N),
        ("meas2", 304, 5, N), ("vect", 309, 500, A),
        # wen is wrapped onto its own line by SQL*Plus (see CONTINUATION);
        # deactivat would follow it there but is always null in this export.
        ("deactivat", 809, 9, D), ("wen", 818, 9, D),
    ],
    "ADDN": [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("seq", 37, 4, N),
        ("card", 41, 5, N), ("lline", 46, 5, N), ("taxyr", 51, 5, N),
        ("class", 56, 4, A), ("yrblt", 60, 5, N), ("effyr", 65, 5, N),
        ("lower", 70, 3, A), ("first", 73, 3, A), ("second", 76, 3, A),
        ("third", 79, 3, A), ("grade", 82, 3, A), ("grdfact", 85, 5, N),
        ("cdu", 90, 2, A), ("depr", 92, 4, N), ("pctcomp", 96, 4, N),
        ("area", 100, 9, N), ("areasum", 109, 11, N), ("value", 120, 11, N),
        ("mktadj", 131, 4, N), ("rcnld", 135, 11, N), ("exmppct", 146, 7, N),
        ("exmpval", 153, 11, N), ("salekey", 164, 9, N),
        ("chgrsn", 173, 2, A), ("vect", 175, 500, A),
        # FIX: PDF lists wen then deactivat; the data has them the other way.
        ("deactivat", 675, 9, D), ("wen", 684, 9, D),
    ],
    "PERMIT": [
        ("parid", 1, 30, A), ("jur", 31, 6, A),
        # FIX: PDF descriptions are wrong: num is the permit number, permdt
        # the permit (issue) date.
        ("num", 37, 18, A), ("permdt", 55, 9, D), ("why", 64, 10, A),
        ("adrno", 74, 11, N), ("adradd", 85, 6, A), ("adrdir", 91, 2, A),
        ("adrstr", 93, 30, A), ("adsuf", 123, 8, A), ("adsuf2", 131, 8, A),
        ("id1", 139, 3, A), ("id2", 142, 3, A), ("amount", 145, 11, N),
        ("flag", 156, 1, A), ("note1", 157, 80, A), ("note2", 237, 80, A),
        ("note3", 317, 80, A), ("drawndt", 397, 9, D),
        ("deactivat", 406, 9, D), ("wen", 415, 9, D),
    ],
    "COMDAT": [
        ("parid", 1, 30, A), ("card", 31, 5, N), ("taxyr", 36, 5, N),
        ("seq", 41, 4, N), ("bldnum", 45, 4, A), ("yrblt", 49, 5, N),  # FIX: bldnum has letters (A-T)
        ("effyr", 54, 5, N), ("units", 59, 5, N), ("structure", 64, 3, A),
        ("grade", 67, 3, A), ("gfact", 70, 7, N), ("numident", 77, 3, N),
        ("bldgros_d", 80, 31, A), ("bldgros_v", 111, 11, N),
        ("note1", 122, 40, A), ("note2", 162, 40, A), ("imprname", 202, 30, A),
        ("parkcover", 232, 5, N), ("parkuncov", 237, 5, N),
        ("rcn", 242, 11, N), ("pcg", 253, 4, N), ("rcnld", 257, 11, N),
        ("pctcomp", 268, 4, N), ("bldgval", 272, 11, N),
        ("deactivat", 283, 9, D), ("wen", 292, 9, D),
    ],
    "COMAPT": [
        ("parid", 1, 30, A), ("card", 31, 5, N), ("taxyr", 36, 5, N),
        ("seq", 41, 4, N), ("usetype", 45, 3, A), ("cnt", 48, 7, N),
        ("bed", 55, 3, N), ("bath", 58, 3, N), ("half", 61, 3, N),
        ("other", 64, 3, N), ("rent", 67, 7, N), ("income", 74, 11, N),
        ("deactivat", 85, 9, D), ("wen", 94, 9, D),
    ],
    "COMFEAT": [
        ("parid", 1, 30, A), ("card", 31, 5, N), ("taxyr", 36, 5, N),
        ("lline", 41, 5, N), ("seq", 46, 4, N), ("struct", 50, 3, A),
        ("ofsign", 53, 1, A), ("meas1", 54, 7, N), ("meas2", 61, 7, N),
        ("stops", 68, 3, N), ("ofnum", 71, 3, N), ("price", 74, 11, N),
        ("vect", 85, 500, A), ("deactivat", 585, 9, D), ("wen", 594, 9, D),
    ],
    "COMINTEXT": [
        ("parid", 1, 30, A), ("card", 31, 5, N), ("taxyr", 36, 5, N),
        ("lline", 41, 5, N), ("seq", 46, 4, N), ("sect", 50, 3, A),
        ("flrfrom", 53, 2, A), ("flrto", 55, 2, A), ("width", 57, 5, N),
        ("lngth", 62, 5, N), ("area", 67, 10, N), ("perim", 77, 6, N),
        ("usetype", 83, 3, A), ("wallhgt", 86, 3, N), ("extwall", 89, 2, A),
        ("constr", 91, 2, A), ("intfin", 93, 4, N), ("heat", 97, 1, A),
        ("air", 98, 1, A), ("plumb", 99, 1, A), ("phycond", 100, 1, A),
        ("functutil", 101, 1, A), ("rcn", 102, 11, N), ("pctg", 113, 4, N),
        ("price", 117, 11, N), ("lineval", 128, 11, N),
        ("featval", 139, 11, N), ("stories", 150, 3, N), ("sf", 153, 10, N),
        ("rentpct", 163, 4, N), ("vect", 167, 500, A),
        ("deactivat", 667, 9, D), ("wen", 676, 9, D),
    ],
    # Lookup tables (ATTIC, BSMT, EXTWALL, GRADE, HEAT, SHFACT, RCOBY, CICDU,
    # CIEXT, CIFEAT, CINTEXT, CISTRUCT) and AEDIT: use load_lookup()/load_aedit().
}

# Columns that SQL*Plus wrapped onto continuation lines (in order).
CONTINUATION: dict[str, list[str]] = {
    "DWELL": ["wen"],
    "OBY": ["wen"],
}

_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def parse_date(s: str) -> _dt.date | None:
    """DD-MON-YY -> date.  YY pivot: >= 50 -> 19YY (Oracle RR-style)."""
    s = s.strip()
    if len(s) != 9 or s[2] != "-" or s[6] != "-":
        return None
    try:
        yy = int(s[7:9])
        year = 1900 + yy if yy >= 50 else 2000 + yy
        return _dt.date(year, _MONTHS[s[3:6]], int(s[0:2]))
    except (KeyError, ValueError):
        return None


def parse_num(s: str):
    s = s.strip()
    if not s or set(s) == {"#"}:
        # '###' is SQL*Plus's overflow marker (value wider than the column);
        # the real value is lost, so treat it as unknown.
        return None
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return s  # keep raw so bad data is visible rather than hidden


_DATE_LINE = re.compile(r"^\d\d-[A-Z]{3}-\d\d$")
# Every parid starts with a district code: letter + 2 digits ("A01", "R72").
_RECORD_START = re.compile(r"^[A-Z]\d\d")


def _records(table: str, zip_path: str) -> Iterator[list[str]]:
    """Yield the physical lines that make up each logical record.

    A record starts on a line beginning with a parid district code
    ("A01", "R72", ...).
    Following bare-date lines are SQL*Plus-wrapped columns (see
    CONTINUATION); any other following lines are overflow produced by
    embedded CR/LF inside a text column (seen in PERMIT notes) and are
    returned too so callers can inspect them (row["_overflow"]).
    """
    with zipfile.ZipFile(zip_path) as z, z.open(ENTRY_FMT.format(table)) as fh:
        buf: list[str] = []
        for raw in fh:
            line = raw.decode("cp1252", errors="replace").rstrip("\r\n")
            starts_record = bool(_RECORD_START.match(line))
            if starts_record:
                if buf:
                    yield buf
                buf = [line]
            elif buf and line:
                buf.append(line)
        if buf:
            yield buf


def iter_table(table: str, zip_path: str = ZIP_PATH, raw: bool = False) -> Iterator[dict]:
    """Yield one dict per logical record of ``table`` (e.g. "DWELL").

    Numeric columns -> int/float/None, dates -> datetime.date/None, text ->
    stripped str ('' when blank).  raw=True returns unconverted stripped text.
    """
    table = table.upper()
    spec = SPECS[table]
    cont = CONTINUATION.get(table, [])
    main = [c for c in spec if c[0] not in cont]
    by_name = {c[0]: c for c in spec}
    for lines in _records(table, zip_path):
        first = lines[0]
        out = {}
        for name, start, length, typ in main:
            out[name] = first[start - 1:start - 1 + length]
        dates = [ln for ln in lines[1:] if _DATE_LINE.match(ln)]
        overflow = [ln for ln in lines[1:] if not _DATE_LINE.match(ln)]
        for name in cont:
            out[name] = dates.pop(0) if dates else ""
        if overflow:
            out["_overflow"] = " | ".join(x.strip() for x in overflow)
        for name, val in out.items():
            if name == "_overflow":
                continue
            typ = by_name[name][3]
            if raw:
                out[name] = val.strip()
            elif typ == N:
                out[name] = parse_num(val)
            elif typ == D:
                out[name] = parse_date(val)
            else:
                out[name] = val.strip()
        yield out


# --------------------------------------------------------------------------
# Code lookups
# --------------------------------------------------------------------------
_LOOKUP_RE = {
    # DWELDAT lookups carry a leading "1" (cost-table number) before the code
    # that appears in DWELL, e.g. "11" -> bsmt "1" = NONE, "110" -> 1.0 story.
    "DWELDAT": re.compile(r"^DWELDAT (\S+) +(\S.{3})(.*)$"),
    "CISTRUCT": re.compile(r"^COMDAT EXTWALL (\d{3})(.*)$"),
    "CINTEXT": re.compile(r"^COMINTEXT USE TYPE (\d{3})(.*)$"),
}


def load_lookup(table: str, zip_path: str = ZIP_PATH) -> dict[str, str]:
    """Return {code: description} for one of the small lookup files.

    Codes are returned exactly as they appear in the data tables:
      ATTIC/BSMT/EXTWALL/HEAT -> "1".."9"; GRADE -> "A", "C+", "XX-";
      SHFACT -> "10" (1 story), "15", "20" ...; CISTRUCT -> COMDAT.structure;
      CINTEXT -> COMINTEXT/COMAPT usetype; CIEXT -> "0101" (extwall+constr);
      CIFEAT -> COMFEAT.struct; RCOBY -> OBY.code; CICDU -> "C11 0" -> "UN".
    """
    table = table.upper()
    with zipfile.ZipFile(zip_path) as z:
        text = z.read(ENTRY_FMT.format(table)).decode("cp1252", errors="replace")
    lines = [ln.rstrip() for ln in text.splitlines()]
    out: dict[str, str] = {}
    if table in ("ATTIC", "BSMT", "EXTWALL", "GRADE", "HEAT", "SHFACT"):
        for ln in lines:
            m = _LOOKUP_RE["DWELDAT"].match(ln)
            if m:
                out[m.group(2).strip()[1:]] = m.group(3).strip()
    elif table in ("CISTRUCT", "CINTEXT"):
        for ln in lines:
            m = _LOOKUP_RE[table].match(ln)
            if m:
                out[m.group(1)] = m.group(2).strip()
    elif table in ("CIEXT", "CIFEAT"):
        # Two physical lines per entry: "<labels> <code>" then "<descr>".
        ne = [ln for ln in lines if ln.strip()]
        for head, desc in zip(ne[0::2], ne[1::2]):
            out[head.split()[-1]] = desc.strip()
    elif table == "CICDU":
        for ln in lines:
            if ln.startswith("COMDAT CDU "):
                out[ln[11:16]] = ln[16:].strip()
    elif table == "RCOBY":
        for ln in lines:
            if ln.strip():
                out[ln[:3].strip()] = ln[3:].strip()
    else:
        raise KeyError(table)
    return out


def load_aedit(zip_path: str = ZIP_PATH) -> dict[tuple[str, str], dict[str, str]]:
    """{(table, field): {value: description}} from AEDIT.DAT.

    This is the richest decode source: DWELDAT STYLE/FUEL/HEATSYS/CDU/INTEXT,
    OBY COND/FUNCT, LAND LTYPE/INFL/CODE, PARDAT LOCATION/FRONT/TOPO/UTIL/
    STREET/PARTIAL/NOTECD, ASMT LUC/CLASS ...  Layout: tble 1-20, fld 21-40,
    val 41-60, msg 61-100, wen 101-109.
    """
    with zipfile.ZipFile(zip_path) as z:
        text = z.read(ENTRY_FMT.format("AEDIT")).decode("cp1252", errors="replace")
    out: dict[tuple[str, str], dict[str, str]] = {}
    for ln in text.splitlines():
        if len(ln) < 41:
            continue
        key = (ln[0:20].strip(), ln[20:40].strip())
        out.setdefault(key, {})[ln[40:60].strip()] = ln[60:100].strip()
    return out


if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else "DWELL"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    for i, r in enumerate(iter_table(t)):
        if i >= n:
            break
        print({k: v for k, v in r.items() if v not in ("", None)})
