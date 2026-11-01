"""End-to-end check against the real Plaid sandbox, no browser needed.

Creates a sandbox bank login for Plaid's "user_transactions_dynamic" test user
(realistic history with recurring payments), exchanges the token, pulls every
transaction, runs bill detection and prints what it found.

    cd agents/bills/backend && python -m scripts.sandbox_smoke

Needs PLAID_CLIENT_ID and PLAID_SECRET (sandbox) in agents/bills/backend/.env.
"""

from __future__ import annotations

import sys
import time
from datetime import date

from bills_agent.bank import BankError, PlaidProvider
from bills_agent.config import get_settings
from bills_agent.detection import Severity, detect_bills


def main() -> int:
    bank = PlaidProvider(get_settings())
    print("Creating a sandbox bank login...")
    access_token, item_id = bank.exchange_public_token(bank.create_sandbox_public_token())
    print(f"Connected item {item_id}. Accounts:")
    accounts = {}
    for a in bank.get_accounts(access_token):
        accounts[a["account_id"]] = f"{a['name']} (...{a.get('mask')})"
        print(f"  {accounts[a['account_id']]}")

    transactions: dict[str, dict] = {}
    cursor = None
    for _ in range(30):
        try:
            page = bank.sync_transactions(access_token, cursor)
        except BankError as exc:
            if exc.code != "still_loading":
                raise
            page = None
        if page is not None:
            for tx in page.added + page.modified:
                transactions[tx["transaction_id"]] = tx
            for tx_id in page.removed:
                transactions.pop(tx_id, None)
            cursor = page.next_cursor
            if page.has_more:
                continue
            if page.update_status == "HISTORICAL_UPDATE_COMPLETE":
                break
        print("  Waiting for Plaid to finish loading history...")
        time.sleep(4)
    print(f"Pulled {len(transactions)} transactions.\n")

    result = detect_bills(transactions.values(), date.today(), accounts)
    for bill in result.bills:
        due = bill.next_due.isoformat() if bill.next_due else "-"
        print(
            f"{bill.payee:<32} {bill.frequency.value:<10} {bill.status.value:<9} "
            f"${bill.typical_amount:>9}  next {due}  confidence {bill.confidence}"
        )
        for flag in bill.flags:
            if flag.severity is Severity.REVIEW:
                print(f"    needs attention: {flag.message}")
    for flag in result.flags:
        print(f"needs attention: {flag.message}")
    if not result.bills:
        print("No bills detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
