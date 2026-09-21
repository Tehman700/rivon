"""CHN-07: sealing customer access tokens before they reach the database.

These tokens are other people's credentials. One of them is enough to read and
send messages as that business on WhatsApp, Messenger or Instagram, so the
database is not allowed to hold a usable copy: anyone with a read-only
connection, a leaked backup or a SQL-injection foothold gets ciphertext.

Fernet is AES-128-CBC with an HMAC, so a row someone has edited fails loudly
instead of decrypting into plausible nonsense. The key lives in
`RIVON_CHANNEL_TOKEN_KEY` and never in the database, which is the whole point:
the two would otherwise be stolen together.

Rotation is deliberately unhandled here. When the key changes, existing rows
stop opening and their connections go to `needs_reauth` — the customer
reconnects in one click, and we never hold a token we cannot account for.
"""

from cryptography.fernet import Fernet, InvalidToken


class TokenUnreadable(Exception):
    """The stored token cannot be opened: wrong key, or the row was altered.

    Never contains the ciphertext or the key — this reaches logs.
    """


class TokenCipher:
    """Seals and opens one tenant's channel credentials."""

    def __init__(self, key: str) -> None:
        try:
            self._fernet = Fernet(key)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                "RIVON_CHANNEL_TOKEN_KEY must be a 32-byte urlsafe base64 key "
                "(generate with: python -c \"from cryptography.fernet import "
                'Fernet; print(Fernet.generate_key().decode())")'
            ) from exc

    def seal(self, token: str) -> bytes:
        if not token or not token.strip():
            raise ValueError("refusing to store an empty access token")
        return self._fernet.encrypt(token.encode())

    def open(self, sealed: bytes) -> str:
        try:
            return self._fernet.decrypt(sealed).decode()
        except (InvalidToken, TypeError) as exc:
            raise TokenUnreadable(
                "stored credential could not be decrypted; the connection needs re-authorising"
            ) from exc

    @staticmethod
    def generate_key() -> str:
        """A fresh key, for `.env`. Losing it means every customer reconnects."""
        return Fernet.generate_key().decode()
