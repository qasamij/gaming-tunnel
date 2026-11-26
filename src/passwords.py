"""Password hashing with no third-party Python packages.

Argon2id is used when the system libargon2 is available (Debian/Ubuntu ship
``libargon2-1``). Otherwise we fall back to scrypt from the Python standard
library, which is also memory-hard and approved by OWASP. Stored values are
self-describing, so an install can be upgraded without a password reset.

Legacy installations stored the plaintext password in ``password``; those
values are still accepted once and transparently re-hashed after a successful
login (see web.py).
"""

from __future__ import annotations

import base64
import ctypes
import ctypes.util
import hashlib
import hmac
import os

_ARGON2 = None
_ARGON2_NAME = ctypes.util.find_library("argon2") or "libargon2.so.1"
try:
    _ARGON2 = ctypes.CDLL(_ARGON2_NAME)
    _FN = _ARGON2.argon2id_hash_raw
    _FN.argtypes = [
        ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
        ctypes.c_char_p, ctypes.c_size_t,
        ctypes.c_char_p, ctypes.c_size_t,
        ctypes.c_void_p, ctypes.c_size_t,
    ]
    _FN.restype = ctypes.c_int
except (OSError, AttributeError):
    _ARGON2 = None


def _enc(raw):
    return base64.b64encode(raw).decode("ascii").rstrip("=")


def _dec(text):
    return base64.b64decode(text + "=" * (-len(text) % 4))


def _argon2(secret, salt, t, m, p, length=32):
    if _ARGON2 is None:
        return None
    try:
        raw = secret.encode("utf-8")
        out = ctypes.create_string_buffer(length)
        rc = _FN(t, m, p, raw, len(raw), salt, len(salt), out, length)
        return out.raw if rc == 0 else None
    except Exception:
        return None


def hash_password(secret, argon2=True):
    """Return a self-describing hash for ``secret``."""
    salt = os.urandom(16)
    if argon2:
        digest = _argon2(secret, salt, 3, 65536, 2)
        if digest:
            return "argon2id$m=65536,t=3,p=2${}${}".format(_enc(salt), _enc(digest))
    n, r, p = 16384, 8, 1
    digest = hashlib.scrypt(secret.encode("utf-8"), salt=salt,
                            n=n, r=r, p=p, dklen=32)
    return "scrypt${}${}${}${}${}".format(n, r, p, _enc(salt), _enc(digest))


def needs_upgrade(encoded):
    value = str(encoded).strip()
    return not (value.startswith("argon2id$") or value.startswith("scrypt$"))


def verify(secret, encoded):
    """Constant-time verification; accepts legacy plaintext for migration."""
    value = str(encoded).strip()
    if needs_upgrade(value):
        return hmac.compare_digest(value, str(secret))
    parts = value.split("$")
    try:
        if parts[0] == "argon2id":
            params = dict(x.split("=", 1) for x in parts[1].split(","))
            salt = _dec(parts[2])
            expected = _dec(parts[3])
            actual = _argon2(secret, salt, int(params["t"]),
                             int(params["m"]), int(params["p"]), len(expected))
            return actual is not None and hmac.compare_digest(actual, expected)
        if parts[0] == "scrypt":
            n, r, p = (int(x) for x in parts[1:4])
            salt, expected = _dec(parts[4]), _dec(parts[5])
            actual = hashlib.scrypt(secret.encode("utf-8"), salt=salt,
                                    n=n, r=r, p=p, dklen=len(expected))
            return hmac.compare_digest(actual, expected)
    except (ValueError, IndexError, KeyError, TypeError):
        return False
    return False
