import hashlib

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("unused-dummy-password")


def verify_password(password: str, encoded: str | None) -> bool:
    try:
        return password_hash.verify(password, encoded or DUMMY_HASH)
    except (ValueError, TypeError, UnknownHashError):
        # The original sample data contains a non-login placeholder.
        password_hash.verify(password, DUMMY_HASH)
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
