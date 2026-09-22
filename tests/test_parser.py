"""Юніт-тести `parser.py` — головна вимога тікета STR-460:

відсутність ключа в `/api` (частково чи майже цілком) НЕ має валити
розбір жодного поля з §2 контракту: кожна функція повертає ``None``,
ніколи не кидає виняток.
"""

from __future__ import annotations

import parser  # custom_components/strumok/parser.py, див. conftest.py

import pytest

# Кожна функція парсера, яку контракт §2 вимагає для одного з entity —
# перевіряємо їх ВСІ однаково: не падають на жодній фікстурі.
ALL_PARSER_FUNCS = [
    parser.device_id,
    parser.firmware_version,
    parser.uptime_seconds,
    parser.charging_state,
    parser.charging_current_a,
    parser.charging_power,
    parser.charging_allowed,
    parser.car_connected,
    parser.home_battery_soc,
    parser.pv_power_w,
    parser.battery_power_w,
    parser.grid_power_w,
    parser.load_power_w,
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
        assert parser.charging_power(api_full) == 3.68
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
