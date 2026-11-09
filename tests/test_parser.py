"""Юніт-тести `parser.py` — головна вимога тікета STR-460:

відсутність ключа в `/api` (частково чи майже цілком) НЕ має валити
розбір жодного поля з §2 контракту: кожна функція повертає ``None``,
ніколи не кидає виняток.
"""

from __future__ import annotations

import pytest

from custom_components.strumok import parser

# Кожна функція парсера, яку контракт §2 вимагає для одного з entity —
# перевіряємо їх ВСІ однаково: не падають на жодній фікстурі.
ALL_PARSER_FUNCS = [
    parser.device_id,
    parser.firmware_version,
    parser.uptime_seconds,
    parser.charging_state,
    parser.charging_current_a,
    parser.charging_power,
    parser.charging_session_energy_kwh,
    parser.charging_state_enum,
    parser.charging_allowed,
    parser.car_connected,
    parser.home_battery_soc,
    parser.pv_power_w,
    parser.battery_power_w,
    parser.grid_power_w,
    parser.load_power_w,
    parser.grid_present,
    parser.wifi_online,
    parser.wifi_rssi,
    parser.inverter_bus_connected,
]


class TestGetPath:
    def test_deep_value_present(self):
        assert parser.get_path({"a": {"b": {"c": 5}}}, "a", "b", "c") == 5

    def test_missing_leaf_key_returns_default(self):
        assert parser.get_path({"a": {"b": {}}}, "a", "b", "c") is None

    def test_missing_intermediate_key_returns_default(self):
        assert parser.get_path({"a": {}}, "a", "b", "c") is None

    def test_non_dict_on_path_returns_default_not_exception(self):
        # `a.b` — рядок, а не словник: реальний випадок хибно сформованого
        # чи урізаного JSON не має впасти з AttributeError/TypeError.
        assert parser.get_path({"a": {"b": "oops"}}, "a", "b", "c") is None

    def test_custom_default(self):
        assert parser.get_path({}, "x", default="fallback") == "fallback"

    def test_none_data_returns_default(self):
        assert parser.get_path(None, "a", "b") is None


class TestFullResponse:
    """Усі поля контракту §2 присутні (`api_full.json`) — усе читається."""

    def test_device_identity(self, api_full):
        assert parser.device_id(api_full) == "SK-E89F6DB694F0"
        assert parser.firmware_version(api_full) == "0.15.53"
        assert parser.uptime_seconds(api_full) == 183920

    def test_evse_fields(self, api_full):
        assert parser.charging_state(api_full) == "charging"
        assert parser.charging_current_a(api_full) == 16
        assert parser.charging_power(api_full) == 3680  # Вт, не кВт
        assert parser.charging_allowed(api_full) is True

    def test_car_connected_true_when_units_and_car_present(self, api_full):
        assert parser.car_connected(api_full) is True

    def test_live_metrics(self, api_full):
        assert parser.home_battery_soc(api_full) == 67
        assert parser.pv_power_w(api_full) == 1240
        assert parser.battery_power_w(api_full) == -320
        assert parser.grid_power_w(api_full) == 0
        assert parser.load_power_w(api_full) == 920

    def test_wifi_and_bus(self, api_full):
        assert parser.wifi_online(api_full) is True
        assert parser.wifi_rssi(api_full) == -58
        assert parser.inverter_bus_connected(api_full) is True


class TestPartialResponse:
    """Типова одноблочна плата: `live`, `wifi`, `bus` відсутні; `evse.units[0]`
    є, але без `car` — реальна поведінка прошивки для одного EVSE."""

    @pytest.mark.parametrize("func", ALL_PARSER_FUNCS)
    def test_no_function_raises(self, api_partial, func):
        func(api_partial)  # не має кинути виняток

    def test_device_identity_still_available(self, api_partial):
        assert parser.device_id(api_partial) == "SK-E89F6DB694F0"
        assert parser.uptime_seconds(api_partial) == 512

    def test_evse_present_fields_read(self, api_partial):
        assert parser.charging_state(api_partial) == "idle"
        assert parser.charging_current_a(api_partial) == 0
        assert parser.charging_allowed(api_partial) is False  # 0 → False, не None

    def test_charging_power_missing_is_none_not_zero(self, api_partial):
        # `evse.kw` відсутній у фікстурі — має бути None, а НЕ 0.
        assert parser.charging_power(api_partial) is None

    def test_car_connected_none_when_unit_has_no_car_key(self, api_partial):
        # Ключова знахідка: units[0] існує, але без "car" — unavailable,
        # не False і не виняток.
        assert parser.car_connected(api_partial) is None

    def test_live_metrics_all_none(self, api_partial):
        assert parser.home_battery_soc(api_partial) is None
        assert parser.pv_power_w(api_partial) is None
        assert parser.battery_power_w(api_partial) is None
        assert parser.grid_power_w(api_partial) is None
        assert parser.load_power_w(api_partial) is None

    def test_wifi_and_bus_none(self, api_partial):
        assert parser.wifi_online(api_partial) is None
        assert parser.wifi_rssi(api_partial) is None
        assert parser.inverter_bus_connected(api_partial) is None


class TestMinimalResponse:
    """Лише `dev`+`fw` — усе інше відсутнє. Найгірший реалістичний випадок."""

    @pytest.mark.parametrize("func", ALL_PARSER_FUNCS)
    def test_no_function_raises(self, api_minimal, func):
        func(api_minimal)

    def test_only_identity_available(self, api_minimal):
        assert parser.device_id(api_minimal) == "SK-000000000000"
        assert parser.firmware_version(api_minimal) == "0.15.53"

    def test_everything_else_is_none(self, api_minimal):
        assert parser.uptime_seconds(api_minimal) is None
        assert parser.charging_state(api_minimal) is None
        assert parser.charging_current_a(api_minimal) is None
        assert parser.charging_power(api_minimal) is None
        assert parser.charging_allowed(api_minimal) is None
        assert parser.car_connected(api_minimal) is None
        assert parser.home_battery_soc(api_minimal) is None
        assert parser.wifi_online(api_minimal) is None
        assert parser.inverter_bus_connected(api_minimal) is None


class TestEmptyAndMalformedInput:
    """Плата, що ще не відповіла, порожній словник, чи неочікувана форма."""

    @pytest.mark.parametrize("func", ALL_PARSER_FUNCS)
    def test_empty_dict_no_function_raises(self, func):
        assert func({}) is None

    def test_evse_units_empty_list(self):
        assert parser.car_connected({"evse": {"units": []}}) is None

    def test_evse_units_not_a_list(self):
        # Захист від малоймовірної, але можливої зміни форми відповіді:
        # не впасти, якщо "units" раптом не масив.
        assert parser.car_connected({"evse": {"units": "oops"}}) is None

    def test_evse_missing_entirely(self):
        assert parser.charging_state({}) is None
        assert parser.charging_allowed({}) is None
        assert parser.car_connected({}) is None

    def test_falsy_but_present_values_are_not_treated_as_missing(self):
        # 0 і False — це ЗНАЧЕННЯ, не "відсутньо". get_path не має плутати
        # "ключа немає" з "ключ дорівнює falsy".
        assert parser.get_path({"a": 0}, "a") == 0
        assert parser.get_path({"a": False}, "a") is False
        assert parser.charging_current_a({"evse": {"cur": 0}}) == 0
        assert parser.charging_allowed({"evse": {"on": 0}}) is False


class TestVersion020Fields:
    """Поля компонента 0.2.0: енергія сесії, словник станів, керування, межі струму."""

    def test_session_energy_present(self, api_control):
        assert parser.charging_session_energy_kwh(api_control) == 4.25

    def test_session_energy_absent_on_current_firmware(self, api_full):
        # Сьогоднішній /api (evse::panel) енергії сесії не віддає — сенсора немає.
        assert parser.charging_session_energy_kwh(api_full) is None

    @pytest.mark.parametrize("raw", ["4.2", True, None, [1]])
    def test_session_energy_rejects_non_numbers(self, raw):
        assert parser.charging_session_energy_kwh({"evse": {"session_kwh": raw}}) is None

    def test_state_enum_known_and_unknown(self, api_full, api_partial):
        assert parser.charging_state_enum(api_full) == "charging"
        # "idle" немає в словнику eveus::statusKey → "unknown", а не виняток HA.
        assert parser.charging_state_enum(api_partial) == "unknown"
        assert parser.charging_state_enum({}) is None

    def test_state_dictionary_matches_firmware(self):
        # eveus::statusKey: 23 коди (0..22) + "unknown".
        assert len(parser.CHARGING_STATES) == 24
        assert parser.CHARGING_STATES[0] == "no_data"
        assert parser.CHARGING_STATES[22] == "adaptive_limit"

    def test_local_control_flag(self, api_full, api_control):
        assert parser.supports_local_control(api_full) is False
        assert parser.supports_local_control(api_control) is True
        assert parser.supports_local_control({"auth": True}) is False

    def test_current_limits_from_charger(self, api_control):
        # min_a=6 < 7 (межа команди) → 7; max=32.
        assert parser.current_limits(api_control) == (7, 32)

    def test_current_limits_defaults_like_server(self):
        assert parser.current_limits({}) == (7, 16)
        assert parser.current_limits({"evse": {"max": 0}}) == (7, 16)
        assert parser.current_limits({"evse": {"min_a": 10, "max": 64}}) == (10, 48)

    def test_mac_round_trip(self):
        assert parser.mac_from_device_id("SK-E89F6DB694F0") == "e8:9f:6d:b6:94:f0"
        assert parser.device_id_from_mac("e89f6db694f0") == "SK-E89F6DB694F0"
        assert parser.device_id_from_mac("E8:9F:6D:B6:94:F0") == "SK-E89F6DB694F0"
        assert parser.mac_from_device_id("SK-XYZ") is None
        assert parser.mac_from_device_id(None) is None
        assert parser.device_id_from_mac("nope") is None

    @pytest.mark.parametrize("func", [parser.supports_local_control, parser.current_limits])
    @pytest.mark.parametrize(
        "data", [{}, {"evse": None}, {"evse": {"min_a": "x", "max": None}}, {"auth": None}]
    )
    def test_always_defined_helpers_never_raise(self, func, data):
        # Ці дві функції мають значення й без полів (False / межі за замовчуванням).
        assert func(data) is not None


class TestGridPresent:
    """STR-561: те саме правило, що в прошивці (hamqttd::gridPresent) і на
    сервері (EventDetector::gridPresent): реле АБО напруга вводу > 50 В."""

    @staticmethod
    def _m(**metrics):
        return {"live": {"m": metrics}}

    @pytest.mark.parametrize(
        ("metrics", "want"),
        [
            ({"grid_present": 1}, True),
            ({"grid_present": 0}, False),
            # Реле розімкнене на дозаряді/в очікуванні Deye, напруга є.
            ({"grid_present": 0, "grid_voltage_v": 230.0}, True),
            # Справжнє відключення: напруга вводу падає до 2.5–5 В.
            ({"grid_present": 0, "grid_voltage_v": 4.0}, False),
            ({"grid_present": 1, "grid_voltage_v": 0.0}, True),
            # Трифазний Deye: реле у вбудованій мапі немає, лише напруга.
            ({"grid_voltage_v": 230.0}, True),
            ({"grid_voltage_v": 50.0}, False),
            ({}, None),
            # Нечислове значення = невідомо, не «нема».
            ({"grid_present": "x"}, None),
        ],
    )
    def test_rule(self, metrics, want):
        assert parser.grid_present(self._m(**metrics)) is want

    def test_no_live_block_is_unknown(self):
        assert parser.grid_present({"dev": "SK-1"}) is None

    @pytest.mark.parametrize(
        ("metrics", "want"),
        [
            # STR-762, коробка клієнта 03.11: реле розімкнене, на фазах 256 В —
            # світло Є (до виправлення тут було «нема»).
            ({"grid_present": 0, "grid_voltage_l1_v": 256.1, "grid_voltage_l2_v": 252.9, "grid_voltage_l3_v": 256.6}, True),
            ({"grid_present": 0, "grid_voltage_l1_v": 0.0, "grid_voltage_l2_v": 0.0, "grid_voltage_l3_v": 3.0}, False),
            # Спільна напруга поруч із фазами не голосує.
            ({"grid_present": 0, "grid_voltage_v": 230.0, "grid_voltage_l1_v": 0.0, "grid_voltage_l2_v": 0.0, "grid_voltage_l3_v": 0.0}, False),
        ],
    )
    def test_three_phase(self, metrics, want):
        assert parser.grid_present(self._m(**metrics)) is want

    def test_board_state_wins(self):
        data = {"live": {"m": {"grid_present": 0}, "grid_state": {"state": "unstable", "reason": "inverter_off"}}}
        assert parser.grid_present(data) is True
        data["live"]["grid_state"]["state"] = "absent"
        assert parser.grid_present(data) is False


class TestGridState:
    """STR-762: стан мережі з якістю — рівно те, що віддає плата в `live.grid_state`."""

    def test_values(self):
        data = {"live": {"grid_state": {"state": "unstable", "reason": "voltage_high"}}}
        assert parser.grid_state(data) == "unstable"
        assert parser.grid_state_reason(data) == "voltage_high"
        assert parser.has_grid_state(data) is True

    def test_absent_block_is_unknown(self):
        assert parser.grid_state({"live": {"m": {}}}) is None
        assert parser.grid_state_reason({"live": {"m": {}}}) is None
        assert parser.has_grid_state({"live": {"m": {}}}) is False

    def test_unknown_values_are_not_passed_through(self):
        # HA відкидає стан enum поза переліком — краще unknown, ніж помилка.
        data = {"live": {"grid_state": {"state": "weird", "reason": "voltage_high"}}}
        assert parser.grid_state(data) is None
        assert parser.grid_state_reason(data) is None
        data = {"live": {"grid_state": {"state": "normal", "reason": "weird"}}}
        assert parser.grid_state_reason(data) is None

    def test_options_match_firmware(self):
        # Перелік прошивки — device/firmware/src/ha_mqtt_disc.h (kGridStateOptions,
        # kGridReasonOptions); розійтись — означає unknown у HA на живій платі.
        import pathlib
        import re

        h = (pathlib.Path(__file__).resolve().parents[3] / "device/firmware/src/ha_mqtt_disc.h").read_text(encoding="utf-8")

        def opts(name):
            body = re.search(name + r"\[\] = \{(.*?)\};", h, re.S).group(1)
            return tuple(re.findall(r'"([a-z_]+)"', body))

        assert opts("kGridStateOptions") == parser.GRID_STATES
        assert opts("kGridReasonOptions") == parser.GRID_STATE_REASONS
