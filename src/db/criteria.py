"""Shared SQL criteria for filtering to arm's-length (market) sales.

Montgomery County stamps each transaction with a validity code. Codes in
NON_MARKET_VALIDITY mark transfers that carry no market price signal
(family transfers, foreclosures, nominal-consideration deeds). The
2001-2002 yearly files predate the field, so NULL/empty validity is
allowed through and the price floor does the filtering for those years.

Multi-parcel conveyances are real market sales, but the county records
the *total* deal price on every parcel row, so including them inflates
medians and double-counts volume. Price statistics should exclude them
via MULTI_PARCEL_VALIDITY until per-parcel allocation exists.
"""
from sqlalchemy import and_, exists, or_

from db.models import Transaction

# Below this a recorded price is nominal consideration, not a market price.
MIN_MARKET_PRICE = 1_000

# A sale under this share of the county's market value at the time is a
# nominal transfer (the county records many "$1,000" and "$10" deeds), not a
# market price and not a distress price. Rows with no recorded value pass.
NOMINAL_RATIO = 0.10

NON_MARKET_VALIDITY = (
    "RELATED INDIVIDUALS OR CORPORATIONS",
    "NOT OPEN MARKET",
    "EXCESS PERSONAL PP/NOT ARMS LENGTH",
    "LIQUIDATION/FORECLOSURE",
    "PARTIAL  INTEREST",  # sic: two spaces in the county data
    "INVALID DATE ON SALE",
    "Mobile Home",
)

MULTI_PARCEL_VALIDITY = (
    "SALE INVOLVING MULTIPLE PARCELS",
    "VALID MULTI-PCL SALE",
)


def market_sale_criteria(
    include_multi_parcel: bool = False,
    include_distress: bool = False,
) -> object:
    """SQL predicate selecting arm's-length sales with a real price.

    include_multi_parcel: keep multi-parcel conveyances (each row carries
    the whole deal price). Leave False anywhere prices are aggregated.
    include_distress: keep foreclosures/liquidations — real transactions at
    real prices, wanted where distress itself is the subject (distressed
    sales, flip entry points) but excluded from market price statistics.
    """
    excluded = set(NON_MARKET_VALIDITY)
    if include_distress:
        excluded.discard("LIQUIDATION/FORECLOSURE")
    if not include_multi_parcel:
        excluded.update(MULTI_PARCEL_VALIDITY)
    return and_(
        Transaction.sale_price >= MIN_MARKET_PRICE,
        Transaction.new_owner != Transaction.old_owner,
        or_(
            Transaction.sale_validity.is_(None),
            Transaction.sale_validity.notin_(tuple(excluded)),
        ),
    )


def plausible_price_criteria() -> object:
    """A sale priced at or above NOMINAL_RATIO of the county's market value.

    Rows without a recorded value (assessed_total is null or non-positive)
    pass through unfiltered.
    """
    return or_(
        Transaction.assessed_total.is_(None),
        Transaction.assessed_total <= 0,
        Transaction.sale_price >= NOMINAL_RATIO * Transaction.assessed_total,
    )


def single_parcel_criteria() -> object:
    """Not part of a deal covering several parcels (same date, buyer and price).

    The county records the whole deal price on every parcel row and does not
    always flag it, so detect it structurally, as get_market_stats does.
    """
    t = Transaction.__table__
    other = t.alias("same_deal")
    return ~exists().where(
        other.c.sale_date == t.c.sale_date,
        other.c.new_owner == t.c.new_owner,
        other.c.sale_price == t.c.sale_price,
        other.c.parcel_id != t.c.parcel_id,
    )
