"""Key derivation, password verifier and report encryption (RF-2.5, RF-2.6, RF-3.3, RNF-1).

Plan, section 2.4: one random 16-byte salt per agent, PBKDF2-HMAC-SHA256 to a
32-byte Fernet key, and a Fernet-encrypted constant (``key_check``) to verify
the password. Neither the password nor the derived key is ever stored.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
import unicodedata

from cryptography.fernet import Fernet, InvalidToken

from mi6.core.errors import AuthenticationError

DEFAULT_ITERATIONS = 600_000
SALT_SIZE = 16
KEY_CHECK_PLAINTEXT = b"mi6:key-check:v1"
_KEY_SIZE = 32


def new_salt() -> bytes:
    """Return a fresh random salt of SALT_SIZE bytes."""
    return secrets.token_bytes(SALT_SIZE)


def encode_salt(salt: bytes) -> str:
    """Return the salt as standard Base64 text, as stored in ``kdf.salt``."""
    _check_salt(salt)
    return base64.b64encode(salt).decode("ascii")


def decode_salt(text: str) -> bytes:
    """Return the salt bytes stored in ``kdf.salt``. Raises ValueError if malformed."""
    try:
        salt = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError, TypeError) as exc:
        raise ValueError("salt is not valid Base64") from exc
    _check_salt(salt)
    return salt


def derive_key(password: str, salt: bytes, iterations: int = DEFAULT_ITERATIONS) -> bytes:
    """Derive the agent's Fernet key from the NFC-normalized password."""
    _check_salt(salt)
    if type(iterations) is not int or iterations < 1:
        raise ValueError("iterations must be a positive integer")
    secret = unicodedata.normalize("NFC", password).encode("utf-8")
    raw_key = hashlib.pbkdf2_hmac("sha256", secret, salt, iterations, dklen=_KEY_SIZE)
    return base64.urlsafe_b64encode(raw_key)


def make_key_check(key: bytes) -> str:
    """Return the password verifier: the Fernet encryption of KEY_CHECK_PLAINTEXT."""
    return Fernet(key).encrypt(KEY_CHECK_PLAINTEXT).decode("ascii")


def verify_key(key: bytes, key_check: str) -> None:
    """Raise AuthenticationError unless ``key`` decrypts ``key_check`` to the constant."""
    plaintext = _decrypt(key, key_check)
    if not hmac.compare_digest(plaintext, KEY_CHECK_PLAINTEXT):
        raise AuthenticationError()


def encrypt_report(key: bytes, report: str) -> str:
    """Return the Fernet token of the UTF-8 encoded report."""
    return Fernet(key).encrypt(report.encode("utf-8")).decode("ascii")


def decrypt_report(key: bytes, token: str) -> str:
    """Return the report in ``token``. Wrong key or tampered token: AuthenticationError."""
    plaintext = _decrypt(key, token)
    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuthenticationError() from exc


def _decrypt(key: bytes, token: str) -> bytes:
    fernet = Fernet(key)
    try:
        return fernet.decrypt(token)
    except (InvalidToken, TypeError, ValueError) as exc:
        raise AuthenticationError() from exc


def _check_salt(salt: bytes) -> None:
    if not isinstance(salt, bytes) or len(salt) != SALT_SIZE:
        raise ValueError(f"salt must be exactly {SALT_SIZE} bytes")
