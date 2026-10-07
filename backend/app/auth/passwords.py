"""Password hashing with scrypt from the standard library, so there is no extra dependency.

Passwords are never stored, only a salted hash that is slow to compute. Checking one takes
roughly a tenth of a second here, which is nothing for a sign-in and painful for guessing.
"""

import hashlib
import hmac
import os
from base64 import b64decode, b64encode

SALT_BYTES = 16
KEY_BYTES = 32
SCRYPT_COST = 2**14
SCRYPT_BLOCK_SIZE = 8
SCRYPT_PARALLELISM = 1
MIN_PASSWORD_CHARS = 8
PREFIX = "scrypt"


def hash_password(password: str) -> str:
    salt = os.urandom(SALT_BYTES)
    return _encode(salt, _derive(password, salt))


def check_password(password: str, stored: str) -> bool:
    try:
        salt, expected = _decode(stored)
    except (ValueError, TypeError):
        return False
    # Compared in constant time, so the answer cannot be guessed from how long it took.
    return hmac.compare_digest(_derive(password, salt), expected)


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=SCRYPT_COST,
        r=SCRYPT_BLOCK_SIZE,
        p=SCRYPT_PARALLELISM,
        dklen=KEY_BYTES,
    )


def _encode(salt: bytes, key: bytes) -> str:
    return f"{PREFIX}${b64encode(salt).decode()}${b64encode(key).decode()}"


def _decode(stored: str) -> tuple[bytes, bytes]:
    prefix, salt, key = stored.split("$")
    if prefix != PREFIX:
        raise ValueError(f"unknown password format {prefix!r}")
    return b64decode(salt), b64decode(key)
