"""Спільні фікстури тестів інтеграції СтрумОК.

Тести ганяють справжній Home Assistant через
`pytest-homeassistant-custom-component` (див. requirements_test.txt), а HTTP
до плати підміняє `aioclient_mock` — жодного реального мережевого запиту.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.strumok.const import DOMAIN

FIXTURES_DIR = Path(__file__).parent / "fixtures"

HOST = "192.168.1.57"
API_URL = f"http://{HOST}/api"
CMD_URL = f"http://{HOST}/api/evse/cmd"
DEV = "SK-E89F6DB694F0"
API_KEY = "sk_" + "a1" * 24


def load_fixture(name: str) -> dict[str, Any]:
    with open(FIXTURES_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> Generator[None]:
    """Дозволити HA вантажити custom_components/strumok у кожному тесті."""
    yield


@pytest.fixture
def api_full() -> dict:
    """Повна відповідь сьогоднішньої прошивки (без блоку `auth`)."""
    return load_fixture("api_full.json")


@pytest.fixture
def api_partial() -> dict:
    """Типова відповідь одноблочної плати: без `live`, `wifi`, `bus`, без `car`."""
    return load_fixture("api_partial.json")


@pytest.fixture
def api_minimal() -> dict:
    """Найгірший реалістичний випадок: лише `dev`+`fw`."""
    return load_fixture("api_minimal.json")


@pytest.fixture
def api_control() -> dict:
    """Прошивка з LOCAL-AUTONOMY: є блок `auth`, межі струму, енергія сесії."""
    return load_fixture("api_control.json")


def make_entry(*, api_key: str | None = None, options: dict | None = None) -> MockConfigEntry:
    data: dict[str, Any] = {CONF_HOST: HOST, CONF_PORT: 80}
    if api_key:
        data[CONF_API_KEY] = api_key
    return MockConfigEntry(
        domain=DOMAIN,
        title=DEV,
        unique_id=DEV,
        data=data,
        options=options or {},
    )


def clone(data: dict) -> dict:
    return copy.deepcopy(data)
