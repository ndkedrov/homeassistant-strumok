"""Ключ API (docs/LOCAL-AUTONOMY-CONTRACT.md §4): без ключа — жодного
заголовка (поведінка як до появи входу), з ключем — Bearer."""

from __future__ import annotations

from custom_components.strumok import auth


def test_no_key_sends_no_header():
    assert auth.auth_headers(None) == {}
    assert auth.auth_headers("") == {}
    assert auth.auth_headers("   ") == {}


def test_key_goes_as_bearer():
    assert auth.auth_headers(" sk_ha_123 ") == {"Authorization": "Bearer sk_ha_123"}


def test_unauthorized_code_is_401():
    assert auth.HTTP_UNAUTHORIZED == 401
