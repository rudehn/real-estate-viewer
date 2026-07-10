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
from sqlalchemy import and_, or_

from db.models import Transaction

# Below this a recorded price is nominal consideration, not a market price.
MIN_MARKET_PRICE = 1_000

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
