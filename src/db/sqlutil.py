"""Dialect-portable SQL: date arithmetic and planner hints.

Postgres has native date math (date - date = days, date + interval), but
SQLite stores dates as TEXT and silently coerces them to numbers under
arithmetic ('2017-10-25' - '2012-05-14' = 5), producing garbage instead of
errors. Production runs Postgres; local dev and the test suite run SQLite,
so analytics must build the right expression for the active dialect.
"""
from datetime import timedelta

from sqlalchemy import Date, cast, func
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ColumnElement
from sqlalchemy.sql.visitors import InternalTraversal

from db.engine import engine


def _is_sqlite() -> bool:
    return engine.dialect.name == "sqlite"


def date_add_days(col, days: int):
    """SQL expression for `col + days`, as a date."""
    if _is_sqlite():
        return func.date(col, f"+{days} days")
    return cast(col + timedelta(days=days), Date)


def days_between(later, earlier):
    """SQL expression for whole days from `earlier` to `later`."""
    if _is_sqlite():
        return func.julianday(later) - func.julianday(earlier)
    return later - earlier


class NoIndex(ColumnElement):
    """A column the SQLite planner must not pick an index for.

    SQLite plans from index heuristics alone (no value histograms), so a
    range predicate on an indexed column makes it walk that index even when
    the range keeps most of the table, which is several times slower than a
    scan. SQLite renders ``(col + 0)``, which no index matches; other
    dialects render the plain column and keep their histogram estimates.
    """

    inherit_cache = True
    _traverse_internals = [("column", InternalTraversal.dp_clauseelement)]

    def __init__(self, column):
        self.column = column
        self.type = column.type


def no_index(column) -> NoIndex:
    return NoIndex(column)


@compiles(NoIndex)
def _compile_no_index(element, compiler, **kw):
    return compiler.process(element.column, **kw)


@compiles(NoIndex, "sqlite")
def _compile_no_index_sqlite(element, compiler, **kw):
    return f"({compiler.process(element.column, **kw)} + 0)"
