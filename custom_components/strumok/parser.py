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

from .const import CMD_MAX_CURRENT_A, CMD_MIN_CURRENT_A, DEFAULT_MAX_CURRENT_A


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
    """`evse.kw` — потужність заряду, **у ватах**, попри назву ключа.

    Звірено в прошивці, а не вгадано: коментар при `evse::haSnapshot`
    (`device/firmware/src/evse.cpp`) — «`kw` панелі — ватти, не кіловати, попри
    назву ключа: Eveus native powerMeas у Вт, а Svartex-драйвер конвертує kW→W
    ще на вході», звірено на живій платі (233 В × 16.37 А = 3814 Вт). MQTT-місток
    публікує це ж число з `unit_of_measurement: W` (`ha_mqtt.cpp`). У 0.1.0 цей
    сенсор помилково мав одиницю kW — виправлено в 0.2.0.
    """
    return get_path(data, "evse", "kw")


def charging_session_energy_kwh(data: dict) -> float | None:
    """`evse.session_kwh` — енергія поточної сесії заряду, кВт·год.

    🔴 Станом на 24.09.2026 `/api` (`evse::panel`) енергії сесії НЕ віддає — вона
    є лише в телеметрії на сервер (`sessionEnergy`, кВт·год для Eveus за
    `app/Services/EvCharger/EvChargerUnit.php`; для Svartex одиниці не заміряні,
    `evse.cpp` «ВІДКРИТІ ПИТАННЯ» п.4). Поле з явною одиницею в назві має додати
    прошивка (HA-FULL-CONTRACT §2.3); доки його немає — сенсора немає.
    """
    raw = get_path(data, "evse", "session_kwh")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw)


# Словник `evse.status` — `eveus::statusKey` (`device/firmware/src/evse_eveus.h`).
# Той самий і для Svartex: плата переводить його стан у словник Eveus
# (`evsedisp::eveusStateOf`) і кладе в `status` тим самим `eveus::statusKey`.
CHARGING_STATES: tuple[str, ...] = (
    "no_data",
    "ready",
    "waiting",
    "charging",
    "pilot_d",
    "pilot_e",
    "pilot_f",
    "leakage",
    "no_ground",
    "overheat_system",
    "overheat_plug",
    "overheat_relay",
    "overcurrent",
    "overvoltage",
    "undervoltage",
    "limit_time",
    "limit_energy",
    "limit_money",
    "schedule_1",
    "schedule_2",
    "blocked",
    "relay_error",
    "adaptive_limit",
    "unknown",
)


def charging_state_enum(data: dict) -> str | None:
    """`evse.status`, звужений до відомого словника; незнайоме значення → `unknown`."""
    raw = charging_state(data)
    if raw is None:
        return None
    return raw if raw in CHARGING_STATES else "unknown"


def supports_local_control(data: dict) -> bool:
    """Чи вміє прошивка локальні команди (`POST /api/evse/cmd`).

    Ознака — блок `auth` у `/api` (`fillStatus`: `o["auth"]["enabled"]`), який
    з'являється разом із LOCAL-AUTONOMY (HA-FULL-CONTRACT §3).
    """
    return isinstance(get_path(data, "auth"), dict)


def _int_or_none(raw: Any) -> int | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return int(raw)


def current_limits(data: dict) -> tuple[int, int]:
    """Межі уставки струму (А) для команди `current_a`.

    Ті самі правила, що й у сервера (`EvCharger::minCurrentA/maxCurrentA`):
    мінімум — більше з 7 А і `evse.min_a` зарядки; максимум — `evse.max`
    зарядки, якщо він не менший за 7 А, інакше 16 А (найслабша модель). Плата
    сама приймає 7…48 А (`cfg_rules.h`), тож межі ще й обрізаються до цього.
    """
    lo = CMD_MIN_CURRENT_A
    min_a = _int_or_none(get_path(data, "evse", "min_a"))
    if min_a is not None:
        lo = max(lo, min_a)
    hi = _int_or_none(get_path(data, "evse", "max"))
    if hi is None or hi < CMD_MIN_CURRENT_A:
        hi = DEFAULT_MAX_CURRENT_A
    hi = min(hi, CMD_MAX_CURRENT_A)
    lo = min(lo, hi)
    return lo, hi


def mac_from_device_id(dev: str | None) -> str | None:
    """`SK-E89F6DB694F0` → `e8:9f:6d:b6:94:f0`.

    `dev` — це `SK-` + MAC станції Wi-Fi (`provision.cpp`: `esp_read_mac(ESP_MAC_WIFI_STA)`).
    Потрібно для `connections` пристрою: так DHCP-спостерігач HA упізнає плату
    за MAC і оновлює її IP (`registered_devices` у manifest).
    """
    if not isinstance(dev, str) or not dev.upper().startswith("SK-"):
        return None
    hex_part = dev[3:]
    if len(hex_part) != 12 or any(c not in "0123456789abcdefABCDEF" for c in hex_part):
        return None
    hex_part = hex_part.lower()
    return ":".join(hex_part[i : i + 2] for i in range(0, 12, 2))


def device_id_from_mac(mac: str) -> str | None:
    """Зворотне до `mac_from_device_id`: `e89f6db694f0` / `e8:9f:…` → `SK-E89F6DB694F0`."""
    hex_part = "".join(c for c in mac if c not in ":-").upper()
    if len(hex_part) != 12 or any(c not in "0123456789ABCDEF" for c in hex_part):
        return None
    return f"SK-{hex_part}"


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


# = EventDetector::GRID_PRESENT_V на сервері і hamqttd::kGridPresentV у прошивці.
GRID_PRESENT_V = 50.0


def _float_or_none(raw: Any) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw)


def grid_present(data: dict) -> bool | None:
    """Мережа є/нема (STR-561, STR-762) — те саме правило, що й на сервері та в MQTT.

    Плата віддає `live.grid_state` (прошивка зі STR-762) — мережі немає рівно
    тоді, коли стан `absent`. Старіша прошивка — те саме правило тут: НЕ сирий
    `live.m.grid_present`, бо реле розмикається й при живій мережі (дозаряд
    банку, очікування, захист від пере- чи недонапруги). Мережа є, коли реле
    замкнене АБО хоч одна фаза понад 50 В; фази трифазного — L1..L3, де їх
    немає — `grid_voltage_v`; без реле й напруги — ``None`` (unknown).
    """
    state = grid_state(data)
    if state is not None:
        return state != "absent"
    relay = _float_or_none(get_path(data, "live", "m", "grid_present"))
    volts = [_float_or_none(get_path(data, "live", "m", k)) for k in GRID_PHASE_KEYS]
    volts = [v for v in volts if v is not None]
    if not volts:
        single = _float_or_none(get_path(data, "live", "m", "grid_voltage_v"))
        volts = [] if single is None else [single]
    by_volt = None if not volts else any(v > GRID_PRESENT_V for v in volts)
    if relay is not None:
        return relay > 0.5 or by_volt is True
    return by_volt


GRID_PHASE_KEYS = ("grid_voltage_l1_v", "grid_voltage_l2_v", "grid_voltage_l3_v")

# Стан мережі з якістю (STR-762): рівно ті значення, що віддає прошивка
# (gridq::stateKey / reasonKey у device/firmware/src/grid_quality.h).
GRID_STATES = ("absent", "unstable", "normal")
GRID_STATE_REASONS = ("none", "voltage_low", "voltage_high", "phase_missing", "reconnecting", "inverter_off")


def grid_state(data: dict) -> str | None:
    """`live.grid_state.state`: absent / unstable / normal; невідоме — ``None``."""
    raw = get_path(data, "live", "grid_state", "state")
    return raw if raw in GRID_STATES else None


def grid_state_reason(data: dict) -> str | None:
    """`live.grid_state.reason` — чому мережа нестабільна; ``none`` у нормі."""
    if grid_state(data) is None:
        return None
    raw = get_path(data, "live", "grid_state", "reason")
    return raw if raw in GRID_STATE_REASONS else None


def has_grid_state(data: dict) -> bool:
    """Плата віддає стан мережі (прошивка зі STR-762 і мапа з напругами)."""
    return grid_state(data) is not None


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
