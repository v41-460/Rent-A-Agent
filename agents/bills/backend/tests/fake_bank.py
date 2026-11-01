"""A stand-in for Plaid that serves fixture transactions, for API tests."""

from __future__ import annotations

from typing import Any

from bills_agent.bank import BankError, SyncPage

ACCESS_TOKEN = "access-sandbox-0f9e8d7c-secret"


class FakeBank:
    def __init__(self, transactions: list[dict[str, Any]], page_size: int = 200) -> None:
        self.transactions = transactions
        self.page_size = page_size
        self.link_tokens: list[str | None] = []
        self.fail_next_sync: list[BankError] = []
        self.not_ready = False
        self.removed: list[str] = []
        self.calls = 0

    def create_link_token(self, user_id: str, access_token: str | None = None) -> dict[str, str]:
        self.link_tokens.append(access_token)
        return {"link_token": "link-sandbox-123", "expiration": "2026-10-04T10:00:00Z"}

    def exchange_public_token(self, public_token: str) -> tuple[str, str]:
        if public_token != "public-sandbox-ok":
            raise BankError("link_expired", "INVALID_PUBLIC_TOKEN")
        return ACCESS_TOKEN, "item-1"

    def get_accounts(self, access_token: str) -> list[dict[str, Any]]:
        assert access_token == ACCESS_TOKEN
        return [
            {
                "account_id": "acc_checking",
                "name": "Plaid Checking",
                "mask": "1111",
                "type": "depository",
                "subtype": "checking",
            },
            {
                "account_id": "acc_savings",
                "name": "Plaid Saving",
                "mask": "2222",
                "type": "depository",
                "subtype": "savings",
            },
            {
                "account_id": "acc_card",
                "name": "Plaid Credit Card",
                "mask": "3333",
                "type": "credit",
                "subtype": "credit card",
            },
        ]

    def sync_transactions(self, access_token: str, cursor: str | None) -> SyncPage:
        assert access_token == ACCESS_TOKEN
        self.calls += 1
        if self.fail_next_sync:
            raise self.fail_next_sync.pop(0)
        if self.not_ready:
            return SyncPage(next_cursor="", has_more=False, update_status="NOT_READY")
        if cursor == "done":
            return SyncPage(
                removed=self.removed, next_cursor="done", update_status="HISTORICAL_UPDATE_COMPLETE"
            )
        start = int(cursor or 0)
        page = self.transactions[start : start + self.page_size]
        end = start + len(page)
        more = end < len(self.transactions)
        return SyncPage(
            added=page,
            next_cursor=str(end) if more else "done",
            has_more=more,
            update_status="HISTORICAL_UPDATE_COMPLETE",
        )
