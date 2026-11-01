"""The edge-case test set.

Each scenario is a deliberately messy, realistic account history plus the exact
behavior we expect from the detector. "Flag it for review" is often the correct
expected outcome.

Expectations are strict: a bill that shows up but isn't listed here, or a review
flag that isn't listed, fails the test. A regression is a bug.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .builder import CHECKING, CREDIT_CARD, SAVINGS, History

AS_OF = date(2026, 9, 28)
SIX_MONTHS_AGO = date(2026, 3, 1)


@dataclass
class ExpectedBill:
    payee: str
    frequency: str
    status: str = "active"
    typical_amount: str | None = None
    next_due: str | None = None
    # Exact set of review-level flags. Anything extra is a failure.
    review_flags: set[str] = field(default_factory=set)
    # Info-level flags that must be present (others are allowed).
    info_flags: set[str] = field(default_factory=set)
    occurrences: int | None = None
    min_confidence: float | None = None
    max_confidence: float | None = None


@dataclass
class Scenario:
    name: str
    story: str
    as_of: date
    transactions: list[dict[str, Any]]
    bills: list[ExpectedBill]
    # Exact set of review-level flags that belong to no single bill.
    global_flags: set[str] = field(default_factory=set)
    # Payees that must not be reported as bills.
    not_bills: set[str] = field(default_factory=set)


EVERYDAY_NOT_BILLS = {"Kroger", "Shell Oil", "Starbucks Store", "Amazon", "Acme Payroll"}


def double_charge(seed: int = 1) -> Scenario:
    h = History(seed=seed)
    h.everyday_spending(SIX_MONTHS_AGO, AS_OF)
    h.monthly(
        "NETFLIX.COM",
        15.49,
        day=5,
        start=(2026, 3),
        count=7,
        merchant="Netflix",
        category="ENTERTAINMENT",
    )
    h.add(date(2026, 9, 5), "NETFLIX.COM", 15.49, merchant="Netflix", category="ENTERTAINMENT")
    return Scenario(
        "double_charge",
        "Netflix charged twice on the same day in September.",
        AS_OF,
        h.txs,
        [
            ExpectedBill(
                "Netflix",
                "monthly",
                typical_amount="15.49",
                next_due="2026-10-05",
                review_flags={"possible_double_charge"},
                occurrences=7,
                min_confidence=0.9,
            )
        ],
        not_bills=EVERYDAY_NOT_BILLS,
    )


def amount_spike(seed: int = 2) -> Scenario:
    h = History(seed=seed)
    h.everyday_spending(SIX_MONTHS_AGO, AS_OF)
    h.monthly(
        "AUSTIN ENERGY ONLINE PMT",
        [89.12, 84.50, 92.30, 101.75, 96.40, 88.90, 247.60],
        day=12,
        start=(2026, 3),
        count=7,
        jitter=2,
        category="RENT_AND_UTILITIES",
    )
    # A gas bill that swings with the seasons but never spikes: must NOT be flagged.
    h.monthly(
        "ATMOS ENERGY",
        [68.20, 55.10, 44.80, 41.25, 39.90, 42.60, 47.15],
        day=20,
        start=(2026, 3),
        count=7,
        jitter=1,
        category="RENT_AND_UTILITIES",
    )
    return Scenario(
        "amount_spike",
        "The electric bill is about $90 for six months, then $247.60.",
        AS_OF,
        h.txs,
        [
            ExpectedBill(
                "Austin Energy",
                "monthly",
                typical_amount="92.30",
                review_flags={"amount_changed"},
                occurrences=7,
            ),
            ExpectedBill("Atmos Energy", "monthly", typical_amount="44.80", occurrences=7),
        ],
        not_bills=EVERYDAY_NOT_BILLS,
    )


def annual_subscription(seed: int = 3) -> Scenario:
    start = date(2024, 8, 1)
    h = History(seed=seed)
    h.everyday_spending(start, AS_OF)
    # Seen twice, a year apart: easy to mistake for two one-off purchases.
    h.add(
        date(2024, 10, 15),
        "AMAZON PRIME*2K4LM0",
        139.00,
        merchant="Amazon Prime",
        category="GENERAL_MERCHANDISE",
        account=CREDIT_CARD,
    )
    h.add(
        date(2025, 10, 15),
        "AMAZON PRIME*8RT21Q",
        139.00,
        merchant="Amazon Prime",
        category="GENERAL_MERCHANDISE",
        account=CREDIT_CARD,
    )
    # Seen only once, but the descriptor says it renews.
    h.add(
        date(2025, 11, 20),
        "MCAFEE*RENEWAL 8MXQ",
        89.99,
        category="GENERAL_SERVICES",
        account=CREDIT_CARD,
    )
    # Genuine one-off purchases of similar size: never bills.
    h.add(date(2025, 3, 8), "BEST BUY 00012345", 649.99, category="GENERAL_MERCHANDISE")
    h.add(date(2026, 6, 2), "DELTA AIR 0062384756", 412.30, category="TRAVEL")
    h.add(date(2025, 12, 14), "MACY'S #0442", 139.00, category="GENERAL_MERCHANDISE")
    return Scenario(
        "annual_subscription",
        "A yearly subscription seen twice in two years, a renewal seen once, and one-off "
        "purchases of similar size.",
        AS_OF,
        h.txs,
        [
            ExpectedBill(
                "Amazon Prime",
                "annual",
                typical_amount="139.00",
                next_due="2026-10-15",
                review_flags={"yearly_charge"},
                occurrences=2,
            ),
            ExpectedBill(
                "Mcafee",
                "annual",
                status="possible",
                typical_amount="89.99",
                next_due="2026-11-20",
                review_flags={"possible_bill_seen_once"},
            ),
        ],
        not_bills=EVERYDAY_NOT_BILLS | {"Best Buy", "Delta Air", "Macy's"},
    )


def forgotten_subscription(seed: int = 4) -> Scenario:
    h = History(seed=seed)
    h.everyday_spending(SIX_MONTHS_AGO, AS_OF)
    h.monthly(
        "PP*MYFITPLAN 4029357733", 9.99, day=17, start=(2026, 3), count=7, accounts=[CREDIT_CARD]
    )
    # A small subscription everyone knows: not "forgotten".
    h.monthly("Spotify USA", 11.99, day=9, start=(2026, 3), count=7, category="ENTERTAINMENT")
    return Scenario(
        "forgotten_subscription",
        "A small monthly charge from an obscure payee, next to a well-known one.",
        AS_OF,
        h.txs,
        [
            ExpectedBill(
                "Myfitplan",
                "monthly",
                typical_amount="9.99",
                review_flags={"possible_forgotten_subscription"},
            ),
            ExpectedBill("Spotify", "monthly", typical_amount="11.99"),
        ],
        not_bills=EVERYDAY_NOT_BILLS,
    )


def near_identical_payees(seed: int = 5) -> Scenario:
    h = History(seed=seed)
    h.everyday_spending(SIX_MONTHS_AGO, AS_OF)
    # Same descriptor, two policies, two amounts, both every month.
    h.monthly(
        "STATE FARM INSURANCE", 142.50, day=3, start=(2026, 3), count=7, category="GENERAL_SERVICES"
    )
    h.monthly(
        "STATE FARM INSURANCE", 88.00, day=18, start=(2026, 3), count=7, category="GENERAL_SERVICES"
    )
    # Descriptors that differ by one word.
    h.monthly(
        "CITY OF SPRINGFIELD UTIL WATER",
        [54.10, 51.80, 57.25, 61.40, 63.10, 58.75, 55.30],
        day=8,
        start=(2026, 3),
        count=7,
        category="RENT_AND_UTILITIES",
    )
    h.monthly(
        "CITY OF SPRINGFIELD UTIL TRASH",
        28.00,
        day=8,
        start=(2026, 3),
        count=7,
        category="RENT_AND_UTILITIES",
    )
    return Scenario(
        "near_identical_payees",
        "Two insurance policies under one identical name; water and trash from the same city.",
        AS_OF,
        h.txs,
        [
            ExpectedBill("State Farm Insurance", "monthly", typical_amount="142.50"),
            ExpectedBill("State Farm Insurance", "monthly", typical_amount="88.00"),
            ExpectedBill("City of Springfield Util Water", "monthly", typical_amount="57.25"),
            ExpectedBill("City of Springfield Util Trash", "monthly", typical_amount="28.00"),
        ],
        not_bills=EVERYDAY_NOT_BILLS,
    )


def two_accounts(seed: int = 6) -> Scenario:
    h = History(seed=seed)
    h.everyday_spending(SIX_MONTHS_AGO, AS_OF)
    # Paid alternately from checking and savings: still one bill.
    h.monthly(
        "COMCAST XFINITY",
        79.99,
        day=22,
        start=(2026, 3),
        count=7,
        accounts=[CHECKING, SAVINGS],
        category="RENT_AND_UTILITIES",
    )
    # Paid from checking every month, and in August also from savings by mistake.
    h.monthly("GEICO *AUTO", 112.00, day=3, start=(2026, 3), count=7, category="GENERAL_SERVICES")
    h.add(date(2026, 8, 5), "GEICO *AUTO", 112.00, account=SAVINGS, category="GENERAL_SERVICES")
    return Scenario(
        "two_accounts",
        "Internet paid alternately from two accounts; car insurance paid from both in one month.",
        AS_OF,
        h.txs,
        [
            ExpectedBill(
                "Xfinity",
                "monthly",
                typical_amount="79.99",
                info_flags={"paid_from_multiple_accounts"},
            ),
            ExpectedBill(
                "GEICO",
                "monthly",
                typical_amount="112.00",
                review_flags={"possible_double_charge"},
                info_flags={"paid_from_multiple_accounts"},
            ),
        ],
        not_bills=EVERYDAY_NOT_BILLS,
    )


def descriptor_drift(seed: int = 7) -> Scenario:
    h = History(seed=seed)
    h.everyday_spending(SIX_MONTHS_AGO, AS_OF)
    h.monthly("SQ *GREENLEAF LAWN", 65.00, day=14, start=(2026, 3), count=4)
    h.monthly("GREENLEAF LAWN CARE LLC", 65.00, day=14, start=(2026, 7), count=3)
    # A rebrand the alias table knows about.
    h.monthly(
        "COMCAST CABLE COMM", 74.99, day=26, start=(2026, 3), count=3, category="RENT_AND_UTILITIES"
    )
    h.monthly(
        "XFINITY INTERNET", 74.99, day=26, start=(2026, 6), count=4, category="RENT_AND_UTILITIES"
    )
    return Scenario(
        "descriptor_drift",
        "The lawn service's bank descriptor changes in July; Comcast becomes Xfinity.",
        AS_OF,
        h.txs,
        [
            ExpectedBill(
                "Greenleaf Lawn Care",
                "monthly",
                typical_amount="65.00",
                occurrences=7,
                info_flags={"payee_name_changed"},
            ),
            ExpectedBill("Xfinity", "monthly", typical_amount="74.99", occurrences=7),
        ],
        not_bills=EVERYDAY_NOT_BILLS | {"Greenleaf Lawn"},
    )


def irregular_cadence(seed: int = 8) -> Scenario:
    h = History(seed=seed)
    h.everyday_spending(SIX_MONTHS_AGO, AS_OF)
    for d in ["2026-03-03", "2026-04-08", "2026-05-09", "2026-06-20", "2026-07-18", "2026-08-27"]:
        h.add(date.fromisoformat(d), "BUGOUT PEST CTRL", 95.00, category="HOME_IMPROVEMENT")
    return Scenario(
        "irregular_cadence",
        "Pest control every 4 to 6 weeks, never on the same day.",
        AS_OF,
        h.txs,
        [
            ExpectedBill(
                "Bugout Pest Ctrl",
                "irregular",
                typical_amount="95.00",
                review_flags={"irregular_schedule"},
                occurrences=6,
            )
        ],
        not_bills=EVERYDAY_NOT_BILLS,
    )


def refund_reversal(seed: int = 9) -> Scenario:
    h = History(seed=seed)
    h.everyday_spending(SIX_MONTHS_AGO, AS_OF)
    h.monthly("PLANET FITNESS", 24.99, day=1, start=(2026, 3), count=7, category="PERSONAL_CARE")
    # Charged twice in August, and the extra one refunded three days later.
    h.add(date(2026, 8, 1), "PLANET FITNESS", 24.99, category="PERSONAL_CARE")
    h.add(date(2026, 8, 4), "PLANET FITNESS", -24.99, category="PERSONAL_CARE")
    # A purchase and its return.
    h.add(date(2026, 7, 10), "TARGET 00012345", 56.23, category="GENERAL_MERCHANDISE")
    h.add(date(2026, 7, 14), "TARGET 00012345", -56.23, category="GENERAL_MERCHANDISE")
    return Scenario(
        "refund_reversal",
        "A double gym charge that was refunded, and a store purchase that was returned.",
        AS_OF,
        h.txs,
        [
            ExpectedBill(
                "Planet Fitness",
                "monthly",
                typical_amount="24.99",
                occurrences=7,
                info_flags={"refund_excluded"},
            )
        ],
        not_bills=EVERYDAY_NOT_BILLS | {"Target"},
    )


def unreadable_dates(seed: int = 10) -> Scenario:
    h = History(seed=seed)
    h.everyday_spending(SIX_MONTHS_AGO, AS_OF)
    h.monthly(
        "DUKE ENERGY",
        [118.40, 109.75, 121.30, 134.80, 141.20, 129.60],
        day=10,
        start=(2026, 3),
        count=6,
        category="RENT_AND_UTILITIES",
    )
    # September's Duke Energy payment arrives with a garbled date.
    h.add("2026-13-45", "DUKE ENERGY", 126.15, category="RENT_AND_UTILITIES")
    # A charge from someone else with no date at all.
    h.add(None, "ACME HOME WARRANTY", 49.00)
    # Money in with no date: not a bill, nothing to flag.
    h.add("", "VENMO CASHOUT", -40.00)
    return Scenario(
        "unreadable_dates",
        "September's electric payment has a garbled date; another charge has no date.",
        AS_OF,
        h.txs,
        [
            ExpectedBill(
                "Duke Energy",
                "monthly",
                typical_amount="125.45",
                occurrences=6,
                review_flags={"unreadable_transaction"},
            )
        ],
        global_flags={"unreadable_transaction"},
        not_bills=EVERYDAY_NOT_BILLS,
    )


def insufficient_history(seed: int = 11) -> Scenario:
    start = date(2026, 9, 14)
    h = History(seed=seed)
    h.everyday_spending(start, AS_OF)
    h.add(date(2026, 9, 15), "OAKWOOD APTS RENT", 1450.00, category="RENT_AND_UTILITIES")
    h.add(date(2026, 9, 20), "NETFLIX.COM", 15.49, merchant="Netflix", category="ENTERTAINMENT")
    h.add(date(2026, 9, 22), "HOME DEPOT #6604", 87.43, category="HOME_IMPROVEMENT")
    return Scenario(
        "insufficient_history",
        "A brand-new connection with only two weeks of history.",
        AS_OF,
        h.txs,
        [
            ExpectedBill(
                "Oakwood Apts Rent",
                "unknown",
                status="possible",
                typical_amount="1450.00",
                review_flags={"possible_bill_seen_once"},
            ),
            ExpectedBill(
                "Netflix",
                "unknown",
                status="possible",
                typical_amount="15.49",
                review_flags={"possible_bill_seen_once"},
            ),
        ],
        global_flags={"not_enough_history"},
        not_bills=EVERYDAY_NOT_BILLS | {"Home Depot"},
    )


def cancelled_bill(seed: int = 12) -> Scenario:
    h = History(seed=seed)
    h.everyday_spending(SIX_MONTHS_AGO, AS_OF)
    # Cancelled after June: should quietly age out.
    h.monthly("HULU 877-8244858", 17.99, day=11, start=(2026, 3), count=4, category="ENTERTAINMENT")
    # Missed only September so far: worth a gentle question.
    h.monthly("DISNEY PLUS", 13.99, day=14, start=(2026, 3), count=6, category="ENTERTAINMENT")
    return Scenario(
        "cancelled_bill",
        "Hulu stopped three months ago; Disney+ missed only this month.",
        AS_OF,
        h.txs,
        [
            ExpectedBill(
                "Hulu",
                "monthly",
                status="stopped",
                typical_amount="17.99",
                info_flags={"expected_charge_missing"},
            ),
            ExpectedBill(
                "Disney+",
                "monthly",
                typical_amount="13.99",
                next_due="2026-09-14",
                review_flags={"expected_charge_missing"},
            ),
        ],
        not_bills=EVERYDAY_NOT_BILLS,
    )


def price_increase(seed: int = 14) -> Scenario:
    h = History(seed=seed)
    h.everyday_spending(SIX_MONTHS_AGO, AS_OF)
    # Not one of the brief's twelve, but found while building them: a fixed-price
    # bill whose price changes must not disappear because its amount "varies".
    h.monthly(
        "NETFLIX.COM",
        [15.49] * 4 + [17.99] * 3,
        day=5,
        start=(2026, 3),
        count=7,
        merchant="Netflix",
        category="ENTERTAINMENT",
    )
    # Price rise on the latest charge only.
    h.monthly(
        "PP*MYFITPLAN 4029357733",
        [9.99] * 6 + [12.99],
        day=17,
        start=(2026, 3),
        count=7,
        accounts=[CREDIT_CARD],
    )
    return Scenario(
        "price_increase",
        "Netflix raises its price in July; another subscription rises this month.",
        AS_OF,
        h.txs,
        [
            ExpectedBill(
                "Netflix",
                "monthly",
                typical_amount="17.99",
                next_due="2026-10-05",
                review_flags={"amount_changed"},
                occurrences=7,
            ),
            ExpectedBill(
                "Myfitplan",
                "monthly",
                typical_amount="9.99",
                review_flags={"amount_changed", "possible_forgotten_subscription"},
            ),
        ],
        not_bills=EVERYDAY_NOT_BILLS,
    )


def typical_household(seed: int = 13) -> Scenario:
    """Not an edge case: a full, ordinary year. Guards against the edge-case rules
    making ordinary bills noisy."""
    start = date(2025, 10, 1)
    h = History(seed=seed)
    h.everyday_spending(start, AS_OF)
    h.monthly(
        "OAKWOOD APTS RENT",
        1450.00,
        day=1,
        start=(2025, 10),
        count=12,
        category="RENT_AND_UTILITIES",
    )
    h.monthly(
        "AUSTIN ENERGY ONLINE PMT",
        [78.10, 92.40, 118.25, 124.60, 109.30, 88.75, 81.20, 95.60, 132.40, 148.90, 151.25, 121.80],
        day=12,
        start=(2025, 10),
        count=12,
        jitter=2,
        category="RENT_AND_UTILITIES",
    )
    h.monthly(
        "VZWRLSS*APOCC VISB",
        85.00,
        day=19,
        start=(2025, 10),
        count=12,
        category="RENT_AND_UTILITIES",
    )
    h.monthly(
        "XFINITY INTERNET", 74.99, day=26, start=(2025, 10), count=12, category="RENT_AND_UTILITIES"
    )
    h.monthly(
        "STATE FARM INSURANCE",
        142.50,
        day=3,
        start=(2025, 10),
        count=12,
        category="GENERAL_SERVICES",
    )
    h.monthly(
        "NETFLIX.COM",
        15.49,
        day=5,
        start=(2025, 10),
        count=12,
        merchant="Netflix",
        category="ENTERTAINMENT",
    )
    h.monthly(
        "PP*MYFITPLAN 4029357733", 9.99, day=17, start=(2025, 10), count=12, accounts=[CREDIT_CARD]
    )
    h.add(
        date(2025, 10, 15),
        "AMAZON PRIME*2K4LM0",
        139.00,
        merchant="Amazon Prime",
        account=CREDIT_CARD,
    )
    h.add(date(2026, 4, 9), "WALGREENS #4471", 23.18, category="MEDICAL")
    return Scenario(
        "typical_household",
        "A full ordinary year of bills alongside everyday spending.",
        AS_OF,
        h.txs,
        [
            ExpectedBill(
                "Oakwood Apts Rent",
                "monthly",
                typical_amount="1450.00",
                next_due="2026-10-01",
                min_confidence=0.95,
            ),
            ExpectedBill("Austin Energy", "monthly", min_confidence=0.8),
            ExpectedBill("Verizon Wireless", "monthly", typical_amount="85.00"),
            ExpectedBill("Xfinity", "monthly", typical_amount="74.99"),
            ExpectedBill("State Farm Insurance", "monthly", typical_amount="142.50"),
            ExpectedBill("Netflix", "monthly", typical_amount="15.49"),
            ExpectedBill(
                "Myfitplan",
                "monthly",
                typical_amount="9.99",
                review_flags={"possible_forgotten_subscription"},
            ),
            # Seen once, 348 days ago, from a subscription service: about to renew.
            ExpectedBill(
                "Amazon Prime",
                "annual",
                status="possible",
                typical_amount="139.00",
                next_due="2026-10-15",
                review_flags={"possible_bill_seen_once"},
            ),
        ],
        not_bills=EVERYDAY_NOT_BILLS | {"Walgreens"},
    )


ALL = [
    double_charge,
    amount_spike,
    annual_subscription,
    forgotten_subscription,
    near_identical_payees,
    two_accounts,
    descriptor_drift,
    irregular_cadence,
    refund_reversal,
    unreadable_dates,
    insufficient_history,
    cancelled_bill,
    price_increase,
    typical_household,
]
