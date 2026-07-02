"""Unit tests for password hashing utility (T5).

Derived from spec AUTH-01 — "criar conta com senha hasheada (bcrypt)" — and the
task contract: ``hash_password(plain) -> str`` and
``verify_password(plain, hashed) -> bool``. verify True/False on match/mismatch
underpins login (AUTH-03) and its rejection path (AUTH-04).
"""

import pytest

from financial_assistant.auth.service import hash_password, verify_password

pytestmark = pytest.mark.unit

PLAIN = "s3nha-forte-do-usuario"


def test_hash_password_returns_str():
    hashed = hash_password(PLAIN)

    assert isinstance(hashed, str)


def test_hash_is_bcrypt_and_not_plaintext():
    hashed = hash_password(PLAIN)

    assert hashed != PLAIN
    # bcrypt hashes carry a $2a$/$2b$/$2y$ modular-crypt prefix.
    assert hashed.startswith(("$2a$", "$2b$", "$2y$"))


def test_verify_password_true_for_matching_plaintext():
    hashed = hash_password(PLAIN)

    assert verify_password(PLAIN, hashed) is True


def test_verify_password_false_for_wrong_plaintext():
    hashed = hash_password(PLAIN)

    assert verify_password("senha-errada", hashed) is False


def test_each_hash_uses_a_fresh_salt():
    first = hash_password(PLAIN)
    second = hash_password(PLAIN)

    # A fresh salt per call means identical inputs produce distinct hashes,
    # yet both still verify against the original password.
    assert first != second
    assert verify_password(PLAIN, first) is True
    assert verify_password(PLAIN, second) is True
