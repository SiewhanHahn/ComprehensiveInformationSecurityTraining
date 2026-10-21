import secrets
import string

from pwdlib import PasswordHash

_password_hash = PasswordHash.recommended()

ALPHABET = string.ascii_lowercase + string.digits


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _password_hash.verify(password, hashed)


def new_public_id() -> str:
    # Unguessable 26-char id (matches CHAR(26) in schema).
    return "".join(secrets.choice(ALPHABET) for _ in range(26))


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def new_session_id() -> str:
    return secrets.token_urlsafe(32)
