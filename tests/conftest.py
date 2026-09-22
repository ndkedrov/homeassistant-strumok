"""Фікстури: завантажують приклади JSON з `/api` (без піднятого Home Assistant).

Ці тести перевіряють ЛИШЕ `custom_components/strumok/parser.py` — чисті
функції без залежності від пакета `homeassistant` (він не встановлюється
для цих тестів навмисно: повний HA-рантайм важкий і не потрібен, щоб
довести головну вимогу тікета STR-460 — "відсутність ключа в `/api` не
валить парсер").
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# `custom_components/strumok/parser.py` не імпортує homeassistant, тож
# додаємо теку пакета в sys.path і імпортуємо файл напряму — без потреби
# ставити homeassistant тільки заради цього тесту.
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "strumok"))


def _load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def api_full() -> dict:
    """Повна відповідь: усі поля контракту §2 присутні, `evse.units[0].car` теж є."""
    return _load_fixture("api_full.json")


@pytest.fixture
def api_partial() -> dict:
    """Реалістична типова відповідь одноблочної плати ("Мій дім"):

    - `live` відсутній цілком (карту інвертора ще/не впізнано);
    - `wifi` і `bus` відсутні;
    - `evse.units[0]` є, але БЕЗ ключа `car` — так насправді поводиться
      прошивка для однієї керованої зарядки (`evse.cpp::panel`, перший
      блок заповнення `units`, не має поля `car` взагалі — воно зʼявляється
      лише в гілці `slotsLive() > 1`). Див. docstring
      `parser.car_connected`.
    """
    return _load_fixture("api_partial.json")


@pytest.fixture
def api_minimal() -> dict:
    """Найгірший реалістичний випадок: лише `dev`+`fw`, решта відсутнє."""
    return _load_fixture("api_minimal.json")
