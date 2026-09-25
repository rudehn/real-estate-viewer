"""Cut a small CAMA fixture zip out of a full county export.

Usage:
    uv run python scripts/build_cama_fixture.py SRC.zip DEST.zip PARID [PARID ...]

Copies every physical line (including wrapped and overflow continuation lines)
of each record whose parcel id is listed, for the data tables the ingest uses.
Lookup tables are copied whole. NBHD keeps the codes used by the chosen
parcels plus the first record that has an overflow continuation line, so the
fixture exercises that framing rule. Entry names are kept exactly.
"""
import sys
import zipfile

DATA_TABLES = ("PARDAT", "LAND", "LEGDAT", "DWELL", "ADDN", "OBY", "APRVAL", "ASMT")
WHOLE_TABLES = ("AEDIT", "GRADE", "HEAT", "RCOBY")


def entry_for(names: list[str], table: str) -> str:
    return next(n for n in names if n.replace("\\", "/").endswith(f"/{table}.DAT"))


def records(raw: bytes):
    """Split a spool into records.

    A record starts on a line beginning with a letter (parcel ids start with a
    district letter, NBHD lines with "PARDAT"). Blank-led overflow lines, bare
    DD-MON-YY wrapped-date lines and empty lines belong to the current record.
    """
    record: list[bytes] = []
    for line in raw.split(b"\n"):
        if line[:1].isalpha() and record:
            yield record
            record = []
        record.append(line)
    if record:
        yield record


def main(src: str, dest: str, parids: list[str]) -> None:
    wanted = {p.encode() for p in parids}
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zout:
        names = zin.namelist()
        nbhds: set[bytes] = set()
        for table in DATA_TABLES:
            entry = entry_for(names, table)
            kept: list[bytes] = []
            for record in records(zin.read(entry)):
                if record[0][:30].rstrip() in wanted:
                    kept.extend(record)
                    if table == "PARDAT":
                        nbhds.add(record[0][226:234].rstrip())
            zout.writestr(entry, b"\n".join(kept) + b"\n")
        for table in WHOLE_TABLES:
            entry = entry_for(names, table)
            zout.writestr(entry, zin.read(entry))
        entry = entry_for(names, "NBHD")
        kept, took_overflow = [], False
        for record in records(zin.read(entry)):
            code = record[0][12:21].rstrip()
            has_overflow = any(line.strip() for line in record[1:])
            if code in nbhds or (has_overflow and not took_overflow):
                kept.extend(record)
                took_overflow = took_overflow or has_overflow
        zout.writestr(entry, b"\n".join(kept) + b"\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
