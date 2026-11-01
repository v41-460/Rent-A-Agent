"""Encryption at rest for Plaid access tokens."""

from __future__ import annotations

from cryptography.fernet import Fernet


class TokenVault:
    def __init__(self, key: str) -> None:
        if not key:
            raise RuntimeError(
                "TOKEN_ENCRYPTION_KEY is not set. Generate one with: python -c "
                '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )
        self._fernet = Fernet(key.encode())

    def seal(self, token: str) -> str:
        return self._fernet.encrypt(token.encode()).decode()

    def open(self, sealed: str) -> str:
        return self._fernet.decrypt(sealed.encode()).decode()
