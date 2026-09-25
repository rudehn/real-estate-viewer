"""Fixed-width parser for Montgomery County (OH) CAMA value/ownership/reference tables.

Layouts come from Cama_Data_Layout.pdf (AA407 Data File Description).
Positions are 1-based start + length, exactly as printed in the PDF, and were
verified against real rows of Cama_Files_20260831.zip (record length = last
field end, lines terminated by CRLF).

Usage:
    from cama_values_parse import iter_table
    for row in iter_table("APRVAL"):
        ...

Types:
    A = alpha (stripped str, '' -> None)
    N = numeric (int if no '.', else float; blank -> None)
    D = date 'DD-MON-YY' -> 'YYYY-MM-DD' (2-digit year pivot: <= PIVOT -> 20YY)
"""

from __future__ import annotations

import io
import os
import zipfile
from datetime import date
from typing import Iterator

HERE = os.path.dirname(os.path.abspath(__file__))
ZIP_PATH = os.path.join(HERE, "Cama_Files_20260831.zip")
ENTRY_FMT = "Cama_Files_20260831\\{}.DAT"
PIVOT = 40  # 2-digit years 00..40 -> 2000s, 41..99 -> 1900s

A, N, D = "A", "N", "D"

# (name, start_1based, length, type)
LAYOUTS: dict[str, list[tuple[str, int, int, str]]] = {
    "OWNDAT": [
        ("parid", 1, 30, A), ("jur", 31, 3, A), ("taxyr", 34, 5, N), ("seq", 39, 4, N),
        ("own1", 43, 40, A), ("own2", 83, 40, A),
        ("paddr1", 123, 121, A), ("paddr2", 244, 80, A), ("paddr3", 324, 123, A),
        ("ownum", 447, 6, A), ("partial", 453, 1, A), ("addrtype", 454, 1, A),
        ("postal_ind", 455, 10, A), ("pctown", 465, 9, N), ("salekey", 474, 9, N),
        ("owntype1", 483, 3, A), ("owntype2", 486, 3, A), ("owntype3", 489, 3, A),
        ("owntype4", 492, 3, A), ("fedid", 495, 10, A), ("stateid", 505, 15, A),
        ("grpflag", 520, 6, A), ("notecd", 526, 2, A), ("note1", 528, 40, A),
        ("note2", 568, 40, A), ("link", 608, 15, A), ("deactivat", 623, 9, D),
        ("wen", 632, 9, D),
    ],
    "MAILDAT": [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("taxyr", 37, 5, N), ("seq", 42, 4, N),
        ("addrtype", 46, 1, A), ("mail1", 47, 40, A), ("mail2", 87, 40, A),
        ("paddr1", 127, 121, A), ("paddr2", 248, 80, A), ("paddr3", 328, 123, A),
        ("mownnum", 451, 6, A), ("carrier_rt", 457, 4, A), ("parlink", 461, 15, A),
        ("postal_ind", 476, 10, A), ("reasmail", 486, 1, A), ("landcontr", 487, 1, A),
        ("paycode", 488, 4, A), ("mortco", 492, 6, A), ("mortno", 498, 20, A),
        ("ltrcode", 518, 1, A), ("chgdate", 519, 9, D), ("note1", 528, 40, A),
        ("note2", 568, 40, A), ("status", 608, 1, A), ("who", 609, 10, A),
        ("wen", 619, 9, D), ("deactivat", 628, 9, D),
    ],
    "LEGDAT": [
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
    ],
    "ASMT": [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("taxyr", 37, 5, N), ("seq", 42, 4, N),
        ("aprland", 46, 11, N), ("aprbldg", 57, 11, N), ("asmtland", 68, 11, N),
        ("asmtbldg", 79, 11, N), ("farmland", 90, 11, N), ("forland", 101, 11, N),
        ("hmsdland", 112, 11, N), ("hmsdbldg", 123, 11, N), ("ppval", 134, 11, N),
        ("abate", 145, 11, N), ("abateland", 156, 11, N), ("noticval", 167, 11, N),
        ("specval", 178, 11, N), ("exmpcode", 189, 6, A), ("noticedate", 195, 9, D),
        ("reascd", 204, 2, A), ("class", 206, 4, A), ("taxclass", 210, 4, A),
        ("luc", 214, 4, A), ("flag2", 218, 6, A), ("note1", 224, 40, A),
        ("note2", 264, 40, A), ("deactivat", 304, 9, D), ("wen", 313, 9, D),
    ],
    "APRVAL": [
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
    ],
    "PARDAT": [  # only used here for nbhd/class/luc per parcel; descriptions in PDF are shifted
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("taxyr", 37, 5, N), ("seq", 42, 4, N),
        ("adrno", 57, 11, N), ("adrstr", 88, 30, A), ("cityname", 118, 40, A),
        ("zip1", 218, 5, A), ("nbhd", 227, 8, A), ("class", 235, 4, A), ("luc", 239, 4, A),
        ("livunit", 244, 4, N), ("acres", 322, 14, N), ("location", 345, 2, A),
        ("rectype", 570, 1, A), ("chgrsn", 580, 2, A), ("salekey", 582, 9, N),
        ("wen", 600, 9, D),
    ],
    "SALES": [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("transno", 37, 9, A), ("oldyr", 46, 5, N),
        ("oldseq", 51, 4, N), ("newyr", 55, 5, N), ("newseq", 60, 4, N),
        ("salekey", 64, 9, N), ("book", 73, 8, A), ("page", 81, 8, A),
        ("oldown", 89, 40, A), ("own1", 129, 40, A), ("saledt", 169, 9, D),
        ("price", 178, 11, N), ("source", 189, 1, A), ("saletype", 190, 1, A),
        ("instruno", 191, 14, A), ("instrtyp", 205, 2, A), ("imageno", 207, 12, A),
        ("adjprice", 219, 11, N), ("adjreas", 230, 3, A), ("recorddt", 233, 9, D),
        ("aprtot", 242, 11, N), ("saleval", 253, 2, A), ("note1", 255, 40, A),
        ("note2", 295, 40, A), ("transdt", 335, 9, D), ("wen", 344, 9, D),
    ],
    "SASMT": [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("projno", 37, 6, A), ("taxyr", 43, 5, N),
        ("seq", 48, 4, N), ("acrebne", 52, 12, N), ("amount", 64, 12, N),
        ("base", 76, 12, N), ("tax1", 88, 12, N), ("tax2", 100, 12, N),
        ("fee1", 112, 12, N), ("fee2", 124, 12, N), ("pen1", 136, 12, N),
        ("pen2", 148, 12, N), ("dlq", 160, 12, N), ("dlqint", 172, 12, N),
        ("caccd", 184, 1, A), ("cyclgrp", 185, 5, A), ("ditch", 190, 3, A),
        ("principal", 193, 12, N), ("interest", 205, 12, N), ("calcamt", 217, 10, N),
        ("ovramt", 227, 12, N), ("futcred", 239, 12, N), ("deincr", 251, 12, N),
        ("fee", 263, 12, N), ("val1", 275, 9, N), ("val2", 284, 9, N),
        ("remain", 293, 12, N), ("intrem", 305, 12, N), ("payoff", 317, 12, N),
        ("rolltype", 329, 10, A), ("note1", 339, 40, A), ("note2", 379, 40, A),
        ("deactivat", 419, 9, D), ("wen", 428, 9, D),
    ],
    "PROJECT": [
        ("projno", 1, 6, A), ("yrbeg", 7, 5, N), ("yrend", 12, 5, N), ("projnam", 17, 30, A),
        ("accode", 47, 2, A), ("bonddt", 49, 9, D), ("calcd", 58, 1, A),
        ("roundcent", 59, 6, N), ("category", 65, 3, A), ("altprojno", 68, 15, A),
        ("unittyp", 83, 2, A), ("delflg", 85, 1, A), ("ditch", 86, 6, N),
        ("intmos", 92, 3, N), ("intrate", 95, 12, N), ("min1st", 107, 8, N),
        ("minhalf", 115, 8, N), ("ordcode", 123, 6, A), ("note1", 129, 40, A),
        ("note2", 169, 40, A), ("deactivat", 209, 9, D), ("wen", 218, 9, D),
    ],
    "HMSD": [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("taxyr", 37, 5, N), ("seq", 42, 4, N),
        ("rolltype", 46, 10, A), ("hmsdappl", 56, 7, N), ("hmsdcode", 63, 1, A),
        ("name1", 64, 40, A), ("addr1", 104, 80, A), ("addr2", 184, 80, A),
        ("addr3", 264, 80, A), ("cityname", 344, 40, A), ("statecode", 384, 2, A),
        ("zip1", 386, 5, A), ("zip2", 391, 4, A), ("hmsdland", 395, 11, N),
        ("hmsdbldg", 406, 11, N), ("redland", 417, 11, N), ("redbldg", 428, 11, N),
        ("note1", 439, 80, A), ("note2", 519, 80, A), ("deactivat", 599, 9, D),
        ("wen", 608, 9, D),
    ],
    "CHARGE": [
        ("parid", 1, 30, A), ("jur", 31, 6, A), ("taxyr", 37, 5, N), ("stub", 42, 9, N),
        ("taxdist", 51, 10, A),
        ("orgchg", 61, 12, N), ("orgred", 73, 12, N), ("orgadj", 85, 12, N),
        ("orgrlbk", 97, 12, N), ("orghmsd", 109, 12, N), ("orghmrb", 121, 12, N),
        ("orgint", 133, 12, N), ("orgdelq", 145, 12, N),
        ("curchg1", 157, 12, N), ("curchg2", 169, 12, N), ("curred1", 181, 12, N),
        ("curred2", 193, 12, N), ("curadj1", 205, 12, N), ("curadj2", 217, 12, N),
        ("currlbk1", 229, 12, N), ("currlbk2", 241, 12, N), ("curhmsd1", 253, 12, N),
        ("curhmsd2", 265, 12, N), ("curhmrb1", 277, 12, N), ("curhmrb2", 289, 12, N),
        ("curint", 301, 12, N), ("curpen1", 313, 12, N), ("curpen2", 325, 12, N),
        ("curdelq", 337, 12, N), ("sanetd", 349, 12, N), ("sanet1", 361, 12, N),
        ("sanet2", 373, 12, N), ("saorgd", 385, 12, N), ("saorg1", 397, 12, N),
        ("saorg2", 409, 12, N), ("nettax", 421, 12, N), ("netdue", 433, 12, N),
        ("netdelq", 445, 12, N), ("net1st", 457, 12, N), ("net2nd", 469, 12, N),
        ("wen", 481, 9, D),
    ],
    "AEDIT": [
        ("tble", 1, 20, A), ("fld", 21, 20, A), ("val", 41, 20, A), ("msg", 61, 40, A),
        ("wen", 101, 9, D),
    ],
    # NBHD.DAT is variable length (trailing blanks trimmed): 'PARDAT NBHD 98010000 S E WASHINGTON TWP'
    "NBHD": [
        ("tbl", 1, 7, A), ("label", 8, 5, A), ("nbhd", 13, 9, A), ("describ", 22, 44, A),
    ],
}

RECLEN = {t: max(s + l - 1 for _, s, l, _ in cols) for t, cols in LAYOUTS.items()}

_MON = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def parse_date(s: str) -> str | None:
    s = s.strip()
    if not s:
        return None
    try:
        dd, mon, yy = s.split("-")
        y = int(yy)
        if len(yy) == 2:
            y += 2000 if y <= PIVOT else 1900
        return date(y, _MON[mon.upper()], int(dd)).isoformat()
    except (ValueError, KeyError):
        return "BAD:" + s


def parse_num(s: str):
    s = s.strip()
    if not s:
        return None
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return "BAD:" + s


def make_row_parser(table: str):
    cols = LAYOUTS[table]
    specs = [(name, s - 1, s - 1 + l, t) for name, s, l, t in cols]

    def parse(line: str) -> dict:
        out = {}
        for name, a, b, t in specs:
            raw = line[a:b]
            if t == A:
                v = raw.strip()
                out[name] = v or None
            elif t == N:
                out[name] = parse_num(raw)
            else:
                out[name] = parse_date(raw)
        return out

    return parse


def _iter_raw_records(table: str, zip_path: str) -> Iterator[bytes]:
    """Split the entry on CRLF only (streaming)."""
    with zipfile.ZipFile(zip_path) as z:
        with z.open(ENTRY_FMT.format(table)) as fh:
            buf = b""
            while True:
                chunk = fh.read(1 << 20)
                if not chunk:
                    break
                buf += chunk
                parts = buf.split(b"\r\n")
                buf = parts.pop()
                yield from parts
            if buf:
                yield buf


def iter_lines(table: str, zip_path: str = ZIP_PATH) -> Iterator[tuple[str, list[str]]]:
    """Yield (record_line, continuation_lines).

    Gotcha: when a field value is longer than its fixed width, the export writes
    the overflow on a *continuation line* right after the record: a CRLF-terminated
    line that starts with blanks and carries the overflow text at the same column
    offset as the field (often followed by an empty line). Real records always
    start with a non-blank key (parid / projno / table name), so any line that is
    empty or starts with a blank is treated as a continuation of the previous record.
    """
    cur: str | None = None
    conts: list[str] = []
    for raw in _iter_raw_records(table, zip_path):
        # files are ASCII except 1 cp1252 byte (0x92 right quote) in OWNDAT;
        # cp1252 is 1 byte/char so fixed-width offsets are preserved
        line = raw.decode("cp1252", errors="replace")
        if not line.strip():
            continue
        if line[0] == " ":
            if cur is not None:
                conts.append(line)
            continue
        if cur is not None:
            yield cur, conts
        cur, conts = line, []
    if cur is not None:
        yield cur, conts


def iter_table(table: str, zip_path: str = ZIP_PATH, strict_len: bool = False,
               merge_overflow: bool = True) -> Iterator[dict]:
    """Parse rows; overflow text from continuation lines is appended to the field
    whose byte span contains the first non-blank column of the continuation line.
    Rows that had overflow get '_overflow' = number of continuation lines."""
    parse = make_row_parser(table)
    reclen = RECLEN[table]
    cols = LAYOUTS[table]
    for line, conts in iter_lines(table, zip_path):
        if strict_len and len(line) != reclen:
            raise ValueError(f"{table}: record length {len(line)} != {reclen}: {line[:60]!r}")
        row = parse(line.ljust(reclen))
        if conts:
            row["_overflow"] = len(conts)
            if merge_overflow:
                for c in conts:
                    col = len(c) - len(c.lstrip(" ")) + 1
                    for name, s, l, t in cols:
                        if s <= col < s + l and t == A:
                            # keep blanks between field start and overflow text
                            # (they are a real word break, e.g. 'SETTLERS' + ' WALK')
                            row[name] = ((row[name] or "") + c[s - 1:].rstrip()).strip()
                            break
        yield row


def nbhd_names(zip_path: str = ZIP_PATH) -> dict[str, str | None]:
    """NBHD.DAT repeats each code many times (1..11x) and 249 codes carry more than
    one description (e.g. 'X' and 'X-DAYTON CSD', or a stale 'CURRENTLY NOT USED').
    Pick a non-null description, avoiding 'NOT USED', then most frequent, then longest."""
    from collections import Counter, defaultdict
    seen: dict[str, Counter] = defaultdict(Counter)
    for r in iter_table("NBHD", zip_path):
        seen[r["nbhd"]][r["describ"]] += 1
    out = {}
    for code, c in seen.items():
        cands = [("NOT USED" not in d, n, len(d), d) for d, n in c.items() if d]
        out[code] = max(cands)[3] if cands else None
    return out


def normalize_parid(p: str | None) -> str | None:
    """CAMA parid is left-justified in a 30-char field, same format as parcel.parcel_id."""
    return p.strip() if p else p


if __name__ == "__main__":
    import sys
    t = sys.argv[1].upper()
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    for i, r in enumerate(iter_table(t)):
        if i >= n:
            break
        print({k: v for k, v in r.items() if v not in (None, 0, 0.0)})
