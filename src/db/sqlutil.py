"""Dialect-portable SQL date arithmetic.

Postgres has native date math (date - date = days, date + interval), but
SQLite stores dates as TEXT and silently coerces them to numbers under
arithmetic ('2017-10-25' - '2012-05-14' = 5), producing garbage instead of
errors. Production runs Postgres; local dev and the test suite run SQLite,
so analytics must build the right expression for the active dialect.
"""
from datetime import timedelta

from sqlalchemy import Date, cast, func

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
