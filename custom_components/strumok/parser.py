"""Безпечний розбір відповіді `/api` плати СтрумОК.

Цей модуль НЕ залежить від `homeassistant` навмисно — уся логіка "як
дістати значення з JSON, не впавши на відсутньому ключі" винесена сюди у
вигляді чистих функцій, щоб її можна було юніт-тестувати без піднятого
Home Assistant (`tests/test_parser.py`).

🔴 Головне правило контракту (docs/HOME-ASSISTANT-DEVICE-INTEGRATION.md §1,
розділ "Критично важливо"): дуже багато полів `/api` **відсутні в JSON**,
коли неактуальні (а не `null`/`0`) — наприклад `live.m` цілком відсутній,
якщо плата не впізнала карту регістрів інвертора, а `evse.units[i].car`
з'являється лише в певних гілках прошивки (див. нижче). Тому кожна функція
тут повертає ``None``, коли поля немає, і НІКОЛИ не кидає виняток і не
підставляє 0 замість "невідомо".
"""

from __future__ import annotations

from typing import Any


def get_path(data: dict | None, *keys: str, default: Any = None) -> Any:
    """Пройти вкладені ключі `data[keys[0]][keys[1]]...`, толерантно до відсутності.

    Повертає ``default`` (типово ``None``), щойно на шляху трапляється
    нема-словник або відсутній ключ — ніколи не кидає ``KeyError``/``TypeError``.
    """
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def device_id(data: dict) -> str | None:
    """Ідентифікатор плати (`dev`, напр. ``SK-E89F6DB694F0``) — основа unique_id."""
    return get_path(data, "dev")


def firmware_version(data: dict) -> str | None:
    return get_path(data, "fw")


def uptime_seconds(data: dict) -> int | None:
    return get_path(data, "up")


def charging_state(data: dict) -> str | None:
    """Нормалізований ключ стану заряду (`evse.status`).

    Контракт §2 явно каже: перелік можливих значень цього enum ще не
    перевірено емпірично на живій платі — тут ми лише прокидаємо сире
    значення, не звужуючи його до заздалегідь вигаданого списку.
    """
    return get_path(data, "evse", "status")


def charging_current_a(data: dict) -> float | None:
    return get_path(data, "evse", "cur")


def charging_power(data: dict) -> float | None:
    """`evse.kw` — потужність заряду.

    🔴 Одиниця виміру НЕ підтверджена коментарем у коді прошивки (контракт
    §2). Назва поля (`kw`) натякає на кіловати, але це поле водночас лежить
    поруч із `evse.cur` (струм у А) і формується тим самим шляхом, що й
    `live.m.*_power_w` (Вт) в іншому блоці тієї ж відповіді — а побутова
    зарядка на кількох-десятках А при 230/400 В дає одиниці кВт, тобто
    значення "у ватах" виглядало б як 4-5-значне число, "у кВт" — як число з
    дробовою частиною близько одиниці. Ми повертаємо сире число як є (без
    перерахунку), а одиницю вимірювання HA-сенсор (`sensor.py`) виставляє
    як `kW` — це НАЙБІЛЬШ ЙМОВІРНЕ припущення, а не перевірений факт.
    Обов'язково звірити емпірично на живій платі (порівняти зі струмом ×
    напругою) і записати результат у ``.sync/ha-hacs-integration.md`` /
    контракт, перш ніж вважати це підтвердженим.
    """
    return get_path(data, "evse", "kw")


def charging_allowed(data: dict) -> bool | None:
    """`evse.on` (0/1) → нормалізований прапорець "заряд дозволено"."""
    raw = get_path(data, "evse", "on")
    if raw is None:
        return None
    return bool(raw)


def car_connected(data: dict) -> bool | None:
    """`evse.units[0].car` — авто підключене до КЕРОВАНОЇ (першої) коробки.

    🔴 Знахідка під час розробки (не вигадка, з коду `evse.cpp::panel`,
    задокументувати в `.sync/`): поле `car` у `evse.units[i]` заповнюється
    ЛИШЕ коли на платі керуються ДВІ й більше зарядки одночасно
    (`evse.cpp`, `if (slotsLive() > 1) { ... e["car"] = u.carPresent; ... }`
    перезаписує весь масив `units` іншим набором полів). У типовому
    домашньому встановленні з ОДНІЄЮ зарядкою (саме той випадок, який
    контракт називає "плата з одним керованим EVSE") перший блок
    заповнення `units` (`n/live/ip/id/vendor/st/ok/...`) ключа `car` не
    містить ВЗАГАЛІ. Тобто для найпоширенішої конфігурації цей сенсор
    сьогодні майже завжди буде `unavailable` — це не помилка парсера, а
    чесне відображення того, що плата фактично не публікує це поле в
    такому режимі. Обробка нижче саме тому не кидає виняток: відсутність
    ключа — очікуваний і документований стан, а не збій.
    """
    units = get_path(data, "evse", "units")
    if not isinstance(units, list) or not units:
        return None
    first = units[0]
    if not isinstance(first, dict) or "car" not in first:
        return None
    return bool(first["car"])


def home_battery_soc(data: dict) -> float | None:
    return get_path(data, "live", "m", "batt_soc_pct")


def pv_power_w(data: dict) -> float | None:
    return get_path(data, "live", "m", "pv_power_w")


def battery_power_w(data: dict) -> float | None:
    """`live.m.batt_power_w`.

    Знак (+заряд/-розряд чи навпаки) контракт §2 явно позначає як
    неперевірений — тут значення прокидається як є, без інверсії.
    """
    return get_path(data, "live", "m", "batt_power_w")


def grid_power_w(data: dict) -> float | None:
    return get_path(data, "live", "m", "grid_power_w")


def load_power_w(data: dict) -> float | None:
    return get_path(data, "live", "m", "load_power_w")


def wifi_online(data: dict) -> bool | None:
    raw = get_path(data, "wifi", "on")
    if raw is None:
        return None
    return bool(raw)


def wifi_rssi(data: dict) -> int | None:
    return get_path(data, "wifi", "rssi")


def inverter_bus_connected(data: dict) -> bool | None:
    raw = get_path(data, "bus", "connected")
    if raw is None:
        return None
    return bool(raw)
