"""Deterministic payee normalization.

``"AMZN Mktp US*2K4LM"`` -> key ``AMAZON``, display ``Amazon``.

Two things come out of a raw bank descriptor:

* a grouping *key*: charges with the same key are treated as the same payee;
* a *display name* in plain words for the user.

Grouping is entirely rule-based so the same input always groups the same way.
Distinguishing words are deliberately kept ("VERIZON WIRELESS" and "VERIZON FIOS"
stay separate) because merging two real bills is worse than showing one bill twice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Payee:
    key: str
    display: str
    # A known merchant from the alias table (not an obscure descriptor).
    well_known: bool = False
    # A known merchant whose business is selling subscriptions.
    subscription: bool = False


@dataclass(frozen=True)
class _Alias:
    pattern: re.Pattern[str]
    key: str
    display: str
    subscription: bool


def _alias(pattern: str, display: str, subscription: bool = True) -> _Alias:
    return _Alias(re.compile(pattern), display.upper(), display, subscription)


# Order matters: more specific patterns first (Amazon Prime before Amazon).
ALIASES: list[_Alias] = [
    _alias(r"\bAMZN PRIME\b|\bAMAZON PRIME\b|\bPRIME MEMBERSHIP\b", "Amazon Prime"),
    _alias(r"\bAMZN\b|\bAMAZON\b", "Amazon", subscription=False),
    _alias(r"\bNETFLIX\b", "Netflix"),
    _alias(r"\bSPOTIFY\b", "Spotify"),
    _alias(r"\bHULU\b", "Hulu"),
    _alias(r"\bDISNEY ?(PLUS|\+)|\bDISNEYPLUS\b", "Disney+"),
    _alias(r"\bHBO ?MAX\b|\bMAX\.COM\b", "Max"),
    _alias(r"\bYOUTUBE ?(PREMIUM|TV)\b|\bGOOGLE \*?YOUTUBE", "YouTube"),
    _alias(r"\bGOOGLE \*?(ONE|STORAGE)\b", "Google One"),
    _alias(r"\bAPPLE\.COM/BILL\b|\bAPPLE\.COM BILL\b|\bITUNES\b", "Apple"),
    _alias(r"\bPARAMOUNT\+|\bPARAMOUNT PLUS\b", "Paramount+"),
    _alias(r"\bPEACOCK\b", "Peacock"),
    _alias(r"\bAUDIBLE\b", "Audible"),
    _alias(r"\bSIRIUS ?XM\b", "SiriusXM"),
    _alias(r"\bCOMCAST\b|\bXFINITY\b", "Xfinity"),
    _alias(r"\bVZWRLSS\b|\bVERIZON WIRELESS\b|\bVERIZON WRLS\b", "Verizon Wireless"),
    _alias(r"\bVERIZON FIOS\b|\bFIOS\b", "Verizon Fios"),
    _alias(r"\bT-MOBILE\b|\bTMOBILE\b", "T-Mobile"),
    _alias(r"\bAT&T\b|\bATT\*", "AT&T"),
    _alias(r"\bGEICO\b", "GEICO"),
    _alias(r"\bPROGRESSIVE\b", "Progressive"),
    _alias(r"\bPLANET FITNESS\b|\bPF CLUB\b", "Planet Fitness"),
]

# Payment-processor prefixes that hide the real merchant.
_PREFIXES = re.compile(
    r"^(?:SQ ?\*|TST\* ?|PP\*|PAYPAL ?\*|SP \*|POS |DEBIT CARD PURCHASE |CHECKCARD |"
    r"PURCHASE AUTHORIZED ON \S+ |RECURRING PAYMENT |ACH DEBIT |ACH |ONLINE PAYMENT TO )+"
)
# Reference codes glued to a star, e.g. "NETFLIX.COM*8KJ3".
_STAR_REF = re.compile(r"\*\s*\S*\d\S*")
_NON_WORD = re.compile(r"[^A-Z0-9&' ]+")
# Words that describe *how* or *why* a payment was made, not *who* was paid.
_NOISE_WORDS = frozenset(
    """
    PAYMENT PMT PYMT ONLINE AUTOPAY AUTO PAY BILL BILLPAY WEB ACH DEBIT RECURRING
    PURCHASE POS INC LLC CO CORP CORPORATION LTD COM WWW HTTPS HTTP NET
    REFUND RETURN REVERSAL SUBSCRIPTION MEMBERSHIP RENEWAL
    """.split()
)
_US_STATES = frozenset(
    """
    AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV
    NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC
    """.split()
)
_SMALL_WORDS = frozenset({"OF", "AND", "THE", "FOR", "AT", "IN", "ON"})


def clean_descriptor(raw: str) -> str:
    """Reduce a bank descriptor to the words that identify the payee."""
    text = raw.upper().strip()
    text = _PREFIXES.sub("", text)
    text = _STAR_REF.sub(" ", text)
    text = text.replace(".COM", " ").replace("*", " ")
    text = _NON_WORD.sub(" ", text)
    tokens = [t for t in text.split() if not any(c.isdigit() for c in t)]
    tokens = [t for t in tokens if t not in _NOISE_WORDS]
    if len(tokens) > 2 and tokens[-1] in _US_STATES:
        tokens = tokens[:-1]
    return " ".join(tokens)


def _title(key: str) -> str:
    words = key.split()
    out = []
    for i, w in enumerate(words):
        if i > 0 and w in _SMALL_WORDS:
            out.append(w.lower())
        elif "&" in w:
            out.append(w)
        else:
            out.append(w.capitalize())
    return " ".join(out)


def normalize_payee(name: str, merchant_name: str | None = None) -> Payee:
    for source in (merchant_name, name):
        if not source:
            continue
        upper = source.upper()
        for alias in ALIASES:
            if alias.pattern.search(upper):
                return Payee(
                    alias.key, alias.display, well_known=True, subscription=alias.subscription
                )

    key = clean_descriptor(merchant_name or name) or clean_descriptor(name)
    if not key:
        # Nothing readable survived; fall back to the raw text so it still groups.
        key = (merchant_name or name or "UNKNOWN").upper().strip()
    return Payee(key, _title(key))
