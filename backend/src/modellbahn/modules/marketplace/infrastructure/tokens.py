"""Encryption of eBay's tokens at rest: whoever reads the database must not sell as the shop."""

from cryptography.fernet import Fernet, InvalidToken


class FernetTokenCipher:
    """AES with an HMAC (Fernet), keyed by ``MB_EBAY_TOKEN_KEY``."""

    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode())

    def encrypt(self, plain: str) -> str:
        return self._fernet.encrypt(plain.encode()).decode() if plain else ""

    def decrypt(self, sealed: str) -> str:
        """The token; empty if there is none or it was sealed with another key."""
        if not sealed:
            return ""
        try:
            return self._fernet.decrypt(sealed.encode()).decode()
        except InvalidToken:
            # A changed key makes the stored tokens useless: eBay then asks for consent again.
            return ""
