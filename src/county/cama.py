"""Montgomery County CAMA export (monthly Cama_Files_YYYYMMDD.zip).

Layouts come from the county's "AA407 Data File Description" PDF with the
corrections verified against the 2026-08-31 export (see
docs/data-sources/cama-building-column-maps.md). Only the tables the ingest
uses are defined here.
"""
from __future__ import annotations

import datetime as dt
import re
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from county.fixedwidth import ALPHA as A
from county.fixedwidth import DATE as D
from county.fixedwidth import NUM as N
from county.fixedwidth import Column, Layout, SpoolReader, decode_lines


def _layout(table: str, spec: list[tuple[str, int, int, str]], wrapped=()) -> Layout:
    return Layout(table, tuple(Column(*c) for c in spec), tuple(wrapped))


LAYOUTS: dict[str, Layout] = {
    "DWELL": _layout("DWELL", [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("card", 37, 5, N),
        ("taxyr", 42, 5, N), ("seq", 47, 4, N), ("stories", 51, 4, N),
        ("extwall", 55, 2, A), ("style", 57, 2, A), ("yrblt", 59, 5, N),
        ("yrremod", 64, 5, N), ("rmtot", 69, 3, N), ("rmbed", 72, 3, N),
        ("rmfam", 75, 2, N), ("fixbath", 77, 3, N), ("fixhalf", 80, 3, N),
        ("fixaddl", 83, 3, N), ("fixtot", 86, 3, N), ("remkit", 89, 1, A),
        ("rembath", 90, 1, A), ("bsmt", 91, 1, A),
        # The PDF says heat is 1 wide; the data has 2, shifting all later columns by 1.
        ("heat", 92, 2, A), ("heatsys", 94, 1, A), ("fuel", 95, 1, A),
        ("grade", 96, 3, A), ("class", 99, 4, A), ("cddesc", 103, 2, A),
        ("attic", 105, 1, A), ("intext", 106, 1, A), ("unitno", 107, 10, A),
        ("rectype", 117, 1, A), ("flr1area", 118, 8, N), ("mastrimarea", 126, 7, N),
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
        ("user10", 824, 20, A), ("deactivat", 844, 9, D), ("wen", 853, 9, D),
    ], wrapped=("wen",)),
    "PARDAT": _layout("PARDAT", [
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
    ]),
    "LAND": _layout("LAND", [
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
    ]),
    "OBY": _layout("OBY", [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("seq", 37, 4, N),
        # The PDF swaps these two descriptions; the data has line then card.
        ("lline", 41, 5, N), ("card", 46, 5, N), ("taxyr", 51, 5, N),
        ("code", 56, 3, A), ("yrblt", 59, 5, N), ("effyr", 64, 5, N),
        ("rectype", 69, 1, A), ("yrrem", 70, 5, N), ("area", 75, 9, N),
        ("areasum", 84, 11, N),
        # From grade on, every column sits 8 bytes later than the PDF says.
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
        ("deactivat", 809, 9, D), ("wen", 818, 9, D),
    ], wrapped=("wen",)),
    "ADDN": _layout("ADDN", [
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
        # The PDF lists wen then deactivat; the data has them the other way round.
        ("deactivat", 675, 9, D), ("wen", 684, 9, D),
    ]),
    "LEGDAT": _layout("LEGDAT", [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("taxyr", 37, 5, N), ("seq", 42, 4, N),
        ("adrpre", 46, 2, A), ("adrno", 48, 11, N), ("adradd", 59, 6, A),
        ("adrsuf", 65, 8, A), ("adrdir", 73, 2, A), ("adrstr", 75, 30, A),
        ("adrsuf2", 105, 8, A), ("cityname", 113, 40, A), ("zip1", 153, 5, A),
        ("zip2", 158, 4, A), ("unitdesc", 162, 10, A), ("unitno", 172, 10, A),
        ("loc2", 182, 40, A), ("taxdist", 222, 5, A), ("acres", 227, 14, N),
        ("compct", 241, 11, N), ("convyn", 252, 10, N), ("xcoord", 262, 11, N),
        ("ycoord", 273, 11, N), ("zcoord", 284, 11, N), ("lotdim", 295, 40, A),
        ("subdiv", 335, 40, A), ("subdnum", 375, 10, A), ("sublot", 385, 8, A),
        ("subblck", 393, 8, A), ("subcode", 401, 1, A), ("condbdg", 402, 8, A),
        ("condunt", 410, 10, A), ("legal1", 420, 60, A), ("legal2", 480, 60, A),
        ("legal3", 540, 60, A), ("note1", 600, 40, A), ("note2", 640, 40, A),
        ("deactivat", 680, 9, D), ("wen", 689, 9, D),
    ]),
    "ASMT": _layout("ASMT", [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("taxyr", 37, 5, N), ("seq", 42, 4, N),
        ("aprland", 46, 11, N), ("aprbldg", 57, 11, N), ("asmtland", 68, 11, N),
        ("asmtbldg", 79, 11, N), ("farmland", 90, 11, N), ("forland", 101, 11, N),
        ("hmsdland", 112, 11, N), ("hmsdbldg", 123, 11, N), ("ppval", 134, 11, N),
        ("abate", 145, 11, N), ("abateland", 156, 11, N), ("noticval", 167, 11, N),
        ("specval", 178, 11, N), ("exmpcode", 189, 6, A), ("noticedate", 195, 9, D),
        ("reascd", 204, 2, A), ("class", 206, 4, A), ("taxclass", 210, 4, A),
        ("luc", 214, 4, A), ("flag2", 218, 6, A), ("note1", 224, 40, A),
        ("note2", 264, 40, A), ("deactivat", 304, 9, D), ("wen", 313, 9, D),
    ]),
    "APRVAL": _layout("APRVAL", [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("taxyr", 37, 5, N), ("seq", 42, 4, N),
        ("reascd", 46, 2, A), ("aprland", 48, 11, N), ("aprbldg", 59, 11, N),
        ("aprtot", 70, 11, N), ("landval", 81, 11, N), ("bldgval", 92, 11, N),
        ("costval", 103, 11, N), ("assmkt", 114, 11, N), ("dwelval", 125, 11, N),
        ("obyval", 136, 11, N), ("revreas", 147, 3, A), ("revland", 150, 11, N),
        ("revbldg", 161, 11, N), ("revtot", 172, 11, N), ("resgrmval", 183, 11, N),
        ("adjbldfact", 194, 8, N), ("adjlandfact", 202, 8, N), ("revwho", 210, 10, A),
        ("revcode", 220, 2, A), ("comval", 222, 11, N), ("comincval", 233, 11, N),
        ("exmpland", 244, 11, N), ("exmpbldg", 255, 11, N), ("exmpval", 266, 11, N),
        ("exmppct", 277, 7, N), ("areasum", 284, 11, N), ("rolltype", 295, 10, A),
        ("note1", 305, 40, A), ("note2", 345, 40, A), ("income", 385, 11, N),
        ("mktval", 396, 11, N), ("mktdt", 407, 9, D), ("lastupd", 416, 9, D),
        ("revdt", 425, 9, D), ("costdt", 434, 9, D), ("deactivat", 443, 9, D),
        ("wen", 452, 9, D),
    ]),
    # NBHD.DAT lines look like 'PARDAT NBHD 98010000 S E WASHINGTON TWP'.
    "NBHD": _layout("NBHD", [
        ("tbl", 1, 7, A), ("label", 8, 5, A), ("nbhd", 13, 9, A), ("describ", 22, 44, A),
    ]),
}

_ENTRY_DATE = re.compile(r"Cama_Files_(\d{8})", re.IGNORECASE)


def _entry(zf: zipfile.ZipFile, table: str) -> str:
    suffix = f"{table.upper()}.DAT"
    for name in zf.namelist():
        # Entry names use backslashes ("Cama_Files_20260831\\DWELL.DAT").
        if re.split(r"[\\/]", name)[-1].upper() == suffix:
            return name
    raise KeyError(f"{table}.DAT not found in CAMA zip")


def snapshot_date(zip_path: Path) -> dt.date:
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            m = _ENTRY_DATE.search(name)
            if m:
                return dt.datetime.strptime(m.group(1), "%Y%m%d").date()
    raise ValueError(f"no snapshot date in {zip_path}")


def table_lines(zip_path: Path, table: str) -> Iterator[str]:
    with zipfile.ZipFile(zip_path) as zf, zf.open(_entry(zf, table)) as fh:
        yield from decode_lines(fh)


def read_table(zip_path: Path, table: str) -> tuple[SpoolReader, Iterator[dict]]:
    """Return the reader (for bad-row stats and ``check()``) and its row iterator.

    Call ``reader.check()`` after consuming the iterator.
    """
    reader = SpoolReader(LAYOUTS[table.upper()])
    return reader, reader.records(table_lines(zip_path, table))


_LOOKUP_LINE = re.compile(r"^DWELDAT (\S+) +(\S.{3})(.*)$")


@dataclass
class Decodes:
    aedit: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)
    grades: dict[str, str] = field(default_factory=dict)
    heats: dict[str, str] = field(default_factory=dict)
    outbuildings: dict[str, str] = field(default_factory=dict)

    def label(self, table: str, field_name: str, code: str | None) -> str | None:
        if code is None:
            return None
        return self.aedit.get((table, field_name), {}).get(code)

    def grade(self, code: str | None) -> str | None:
        return self.grades.get(code) if code else None

    def heat(self, code: str | None) -> str | None:
        # HEAT.DAT has GEOTHERMAL, which the AEDIT list lacks.
        return self.heats.get(code) if code else None

    def outbuilding(self, code: str | None) -> str | None:
        return self.outbuildings.get(code) if code else None


def _read_text(zip_path: Path, table: str) -> list[str]:
    return list(table_lines(zip_path, table))


def _dweldat_lookup(lines: list[str]) -> dict[str, str]:
    out = {}
    for line in lines:
        m = _LOOKUP_LINE.match(line.rstrip())
        if m:
            # Codes carry a leading cost-table digit: "11" is bsmt "1".
            out[m.group(2).strip()[1:]] = m.group(3).strip()
    return out


def load_decodes(zip_path: Path) -> Decodes:
    decodes = Decodes()
    for line in _read_text(zip_path, "AEDIT"):
        if len(line) < 41 or line[0] == " ":
            continue
        key = (line[0:20].strip(), line[20:40].strip())
        decodes.aedit.setdefault(key, {})[line[40:60].strip()] = line[60:100].strip()
    decodes.grades = _dweldat_lookup(_read_text(zip_path, "GRADE"))
    decodes.heats = _dweldat_lookup(_read_text(zip_path, "HEAT"))
    for line in _read_text(zip_path, "RCOBY"):
        if line.strip():
            decodes.outbuildings[line[:3].strip()] = line[3:].strip()
    return decodes


def neighborhood_names(zip_path: Path) -> dict[str, str]:
    """Code to name from NBHD.DAT.

    Codes repeat up to 11 times and 249 carry conflicting names. Prefer a name
    without "NOT USED", then the most frequent, then the longest.
    """
    seen: dict[str, Counter] = defaultdict(Counter)
    reader, rows = read_table(zip_path, "NBHD")
    for row in rows:
        if row["nbhd"] and row["describ"]:
            seen[row["nbhd"]][row["describ"]] += 1
    reader.check()
    out = {}
    for code, counts in seen.items():
        ranked = max(counts.items(), key=lambda kv: ("NOT USED" not in kv[0], kv[1], len(kv[0])))
        out[code] = ranked[0]
    return out
