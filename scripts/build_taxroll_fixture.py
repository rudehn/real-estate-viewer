"""Cut a small tax roll fixture zip out of a full county file.

Usage:
    uv run python scripts/build_taxroll_fixture.py SRC.zip DEST.zip PARID [PARID ...]

Keeps the header line and the raw lines of the listed parcels, byte for byte,
under the original entry name.
"""
import sys
import zipfile


def main(src: str, dest: str, parids: list[str]) -> None:
    wanted = {f'"{p:<14}"'.encode() for p in parids}
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zout:
        (entry,) = [n for n in zin.namelist() if n.lower().endswith(".csv")]
        kept = []
        with zin.open(entry) as fh:
            kept.append(fh.readline())
            for line in fh:
                # Column 2 is the quoted, space-padded parcel id.
                if line.split(b",", 2)[1] in wanted:
                    kept.append(line)
        zout.writestr(entry, b"".join(kept))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
