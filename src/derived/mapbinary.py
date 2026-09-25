"""Columnar binary of every mapped parcel, decoded by the frontend's Web Worker.

See the Task 13 table in docs/superpowers/plans/2026-09-24-phase-1a-data-platform-and-api.md
for the column list; the frontend decoder must match it.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
import struct
import sys
from array import array
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from db.county_models import OCCUPANCY_CATEGORIES, ParcelSummary

MAGIC = b"RPB1"
EPOCH = date(1970, 1, 1)
CLASS_LABELS = ["A", "C", "E", "I", "R", "U"]
DERIVED_DIR = Path(os.getenv("DATA_DIR", "data")) / "derived"
_NAME = re.compile(r"parcels-v(\d+)\.bin$")
_TYPECODES = {"float32": "f", "uint16": "H", "uint8": "B"}

if sys.byteorder != "little":  # array() writes native byte order
    raise RuntimeError("map binary encoding assumes a little-endian host")

FLOAT_COLUMNS = ("last_sale_price", "price_per_sqft", "market_value", "value_change_pct",
                 "annual_tax")


def _pad4(data: bytes, fill: bytes = b"\0") -> bytes:
    return data + fill * (-len(data) % 4)


def _clamp(value, top: int, missing: int) -> int:
    if value is None:
        return missing
    return max(0, min(int(round(value)), top))


def encode_map_binary(rows: Sequence[Mapping], version: int) -> bytes:
    neighborhoods = sorted({r["neighborhood"] for r in rows if r["neighborhood"]})
    nbhd_index = {code: i for i, code in enumerate(neighborhoods)}
    columns: list[tuple[str, str, array, list | None]] = [
        ("lng", "float32", array("f", (r["longitude"] for r in rows)), None),
        ("lat", "float32", array("f", (r["latitude"] for r in rows)), None),
    ]
    for name in FLOAT_COLUMNS:
        columns.append((name, "float32", array(
            "f", (math.nan if r[name] is None else r[name] for r in rows)), None))
    columns += [
        ("last_sale_day", "uint16", array("H", (
            (r["last_sale_date"] - EPOCH).days if r["last_sale_date"] else 0 for r in rows)), None),
        ("living_sqft", "uint16", array("H", (_clamp(r["living_sqft"], 65535, 0) for r in rows)),
         None),
        ("year_built", "uint16", array("H", (_clamp(r["year_built"], 65535, 0) for r in rows)),
         None),
        ("beds", "uint8", array("B", (_clamp(r["beds"], 254, 255) for r in rows)), None),
        ("baths_x2", "uint8", array("B", (
            _clamp(None if r["baths"] is None else r["baths"] * 2, 254, 255) for r in rows)), None),
        ("parcel_class", "uint8", array("B", (
            CLASS_LABELS.index(r["parcel_class"]) if r["parcel_class"] in CLASS_LABELS
            else CLASS_LABELS.index("R") for r in rows)), CLASS_LABELS),
        ("occupancy", "uint8", array("B", (
            OCCUPANCY_CATEGORIES.index(r["occupancy"]) for r in rows)), list(OCCUPANCY_CATEGORIES)),
        ("neighborhood", "uint16", array("H", (
            nbhd_index.get(r["neighborhood"], 65535) for r in rows)), neighborhoods),
        ("distress_score", "uint8", array("B", (
            _clamp(r["distress_score"], 255, 0) for r in rows)), None),
        ("permit_count_5y", "uint8", array("B", (
            _clamp(r["permit_count_5y"], 255, 0) for r in rows)), None),
        ("flags", "uint8", array("B", (
            (1 if r["year_built_is_placeholder"] else 0) | (2 if r["out_of_state_owner"] else 0)
            for r in rows)), None),
    ]
    ids = "\n".join(r["parcel_id"] for r in rows).encode()
    buffers = [_pad4(col[2].tobytes()) for col in columns] + [_pad4(ids)]

    def header_bytes(base: int) -> bytes:
        offset = base
        meta = []
        for (name, kind, values, labels), buf in zip(columns, buffers, strict=False):
            entry = {"name": name, "type": kind, "offset": offset,
                     "byteLength": len(values) * values.itemsize}
            if labels is not None:
                entry["labels"] = labels
            meta.append(entry)
            offset += len(buf)
        header = {"version": version, "rows": len(rows), "columns": meta,
                  "ids": {"offset": offset, "byteLength": len(ids)}}
        return _pad4(json.dumps(header, separators=(",", ":")).encode(), b" ")

    # The header's length depends on the offsets it contains; iterate until stable.
    header = header_bytes(8)
    while len(header_bytes(8 + len(header))) != len(header):
        header = header_bytes(8 + len(header))
    header = header_bytes(8 + len(header))
    return MAGIC + struct.pack("<I", len(header)) + header + b"".join(buffers)


def decode_map_binary(data: bytes) -> dict:
    if data[:4] != MAGIC:
        raise ValueError("not a parcel map binary")
    (header_len,) = struct.unpack_from("<I", data, 4)
    header = json.loads(data[8 : 8 + header_len])
    columns, labels = {}, {}
    for col in header["columns"]:
        values = array(_TYPECODES[col["type"]])
        values.frombytes(data[col["offset"] : col["offset"] + col["byteLength"]])
        columns[col["name"]] = values
        if "labels" in col:
            labels[col["name"]] = col["labels"]
    ids_meta = header["ids"]
    ids_raw = data[ids_meta["offset"] : ids_meta["offset"] + ids_meta["byteLength"]]
    return {"version": header["version"], "header": header, "columns": columns,
            "labels": labels, "ids": ids_raw.decode().split("\n") if ids_raw else []}


async def build_map_binary(conn: AsyncConnection, version: int) -> bytes:
    """Reads on the async connection; encodes in a worker thread."""
    s = ParcelSummary.__table__
    result = await conn.execute(
        sa.select(s)
        .where(s.c.is_active.is_(True), s.c.latitude.isnot(None), s.c.longitude.isnot(None))
        .order_by(s.c.parcel_id)
    )
    rows = result.mappings().all()
    return await asyncio.to_thread(encode_map_binary, rows, version)


def map_binary_path(version: int) -> Path:
    return DERIVED_DIR / f"parcels-v{version}.bin"


def write_map_binary(data: bytes, version: int) -> Path:
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    target = map_binary_path(version)
    partial = target.with_suffix(".part")
    partial.write_bytes(data)
    partial.replace(target)
    for old in DERIVED_DIR.glob("parcels-v*.bin"):
        if old != target:
            old.unlink(missing_ok=True)
    return target


def latest_map_binary() -> tuple[int, Path] | None:
    found = [
        (int(m.group(1)), p)
        for p in DERIVED_DIR.glob("parcels-v*.bin")
        if (m := _NAME.search(p.name))
    ]
    return max(found) if found else None
