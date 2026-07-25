"""Compatibility shim for the legacy `jwt` import used by the test suite.

This project uses `python-jose` for JWT handling, but the existing tests
import the top-level `jwt` module directly. Re-export the public exceptions and
helpers from `jose` so the tests can keep their current expectations.
"""

from jose.exceptions import ExpiredSignatureError, JWTError
from jose.jwt import decode, encode, get_unverified_header


class InvalidTokenError(JWTError):
    """Compatibility alias for the legacy jwt API used in tests."""


__all__ = [
    "ExpiredSignatureError",
    "InvalidTokenError",
    "JWTError",
    "get_unverified_header",
    "encode",
    "decode",
]
