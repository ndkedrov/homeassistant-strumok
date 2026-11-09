"""Завантаження запису, координатор (401 → reauth, мережа → UpdateFailed), сутності, діагностика."""

from __future__ import annotations

from datetime import timedelta

import aiohttp
import pytest

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.strumok.const import DOMAIN

from .conftest import API_KEY, API_URL, DEV, HOST, clone, make_entry


async def _setup(hass: HomeAssistant, entry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _device(hass: HomeAssistant, entry) -> dr.DeviceEntry:
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert len(devices) == 1
    assert devices[0].identifiers == {(DOMAIN, DEV)}
    return devices[0]


def _entity_id(hass: HomeAssistant, domain: str, key: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"strumok_ske89f6db694f0_{key}")


async def test_setup_and_unload(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_full) -> None:
    aioclient_mock.get(API_URL, json=api_full)
    entry = make_entry()
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED

    # Сенсори з 0.1.0 — ті самі unique_id (сутності користувачів не осиротіють).
    power = _entity_id(hass, "sensor", "charging_power")
    assert power is not None
    state = hass.states.get(power)
    assert state.state == "3680"
    assert state.attributes["unit_of_measurement"] == "W"  # не kW, як у 0.1.0

    status = hass.states.get(_entity_id(hass, "sensor", "charging_state"))
    assert status.state == "charging"
    assert "adaptive_limit" in status.attributes["options"]

    # Сьогоднішня прошивка не віддає енергію сесії і не має локальних команд.
    assert _entity_id(hass, "sensor", "charging_session_energy") is None
    assert _entity_id(hass, "switch", "charging_enabled") is None
    assert _entity_id(hass, "number", "charging_current") is None
    assert _entity_id(hass, "button", "phase_reset") is None

    device = _device(hass, entry)
    assert device.configuration_url == f"http://{HOST}/"
    assert (dr.CONNECTION_NETWORK_MAC, "e8:9f:6d:b6:94:f0") in device.connections
    assert device.sw_version == "0.15.53"
    assert device.serial_number == DEV

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_401_starts_reauth(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(API_URL, status=401, json={"error": "auth"})
    entry = make_entry()
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == SOURCE_REAUTH
    assert flows[0]["context"]["entry_id"] == entry.entry_id


async def test_setup_unreachable_retries(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(API_URL, exc=aiohttp.ClientError())
    entry = make_entry()
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.parametrize(
    "failure", [{"exc": aiohttp.ClientError()}, {"exc": TimeoutError()}, {"status": 500}, {"text": "oops"}]
)
async def test_update_failure_marks_unavailable_then_recovers(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_full, failure
) -> None:
    aioclient_mock.get(API_URL, json=api_full)
    entry = make_entry()
    await _setup(hass, entry)
    power = _entity_id(hass, "sensor", "charging_power")

    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, **failure)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=16))
    await hass.async_block_till_done()
    assert entry.runtime_data.last_update_success is False
    assert hass.states.get(power).state == STATE_UNAVAILABLE
    assert entry.state is ConfigEntryState.LOADED  # мережа — не привід вивантажувати

    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, json=api_full)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=32))
    await hass.async_block_till_done()
    assert hass.states.get(power).state == "3680"


async def test_update_401_starts_reauth(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_full) -> None:
    aioclient_mock.get(API_URL, json=api_full)
    entry = make_entry()
    await _setup(hass, entry)

    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, status=401, json={"error": "auth"})
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=16))
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]


async def test_bearer_header_sent_when_key_set(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_full
) -> None:
    aioclient_mock.get(API_URL, json=api_full)
    await _setup(hass, make_entry(api_key=API_KEY))
    _, _, _, headers = aioclient_mock.mock_calls[0]
    assert headers == {"Authorization": f"Bearer {API_KEY}"}


async def test_no_bearer_without_key(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_full) -> None:
    aioclient_mock.get(API_URL, json=api_full)
    await _setup(hass, make_entry())
    _, _, _, headers = aioclient_mock.mock_calls[0]
    assert not headers


async def test_new_fields_appear_without_restart(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_full, api_control
) -> None:
    """OTA на прошивку з енергією сесії й командами → сутності зʼявляються самі."""
    aioclient_mock.get(API_URL, json=api_full)
    entry = make_entry(api_key=API_KEY)
    await _setup(hass, entry)
    assert _entity_id(hass, "sensor", "charging_session_energy") is None
    assert _entity_id(hass, "switch", "charging_enabled") is None

    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, json=api_control)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=16))
    await hass.async_block_till_done()

    energy = _entity_id(hass, "sensor", "charging_session_energy")
    state = hass.states.get(energy)
    assert state.state == "4.25"
    assert state.attributes["unit_of_measurement"] == "kWh"
    assert state.attributes["device_class"] == "energy"
    assert state.attributes["state_class"] == "total_increasing"
    assert _entity_id(hass, "switch", "charging_enabled") is not None
    # sw_version пристрою оновлено після OTA без перезавантаження.
    device = _device(hass, entry)
    assert device.sw_version == "0.16.2"


async def test_missing_fields_are_unavailable_not_errors(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_partial
) -> None:
    aioclient_mock.get(API_URL, json=api_partial)
    await _setup(hass, make_entry())
    assert hass.states.get(_entity_id(hass, "sensor", "pv_power")).state == STATE_UNAVAILABLE
    assert hass.states.get(_entity_id(hass, "binary_sensor", "car_connected")).state == STATE_UNAVAILABLE
    # "idle" — не зі словника прошивки: ENUM-сенсор показує "unknown", а не падає.
    assert hass.states.get(_entity_id(hass, "sensor", "charging_state")).state == "unknown"


async def test_diagnostics_redacts_secrets(
    hass: HomeAssistant, hass_client, aioclient_mock: AiohttpClientMocker, api_control
) -> None:
    data = clone(api_control)
    data["evse"]["user"] = "admin"
    data["wifi"]["ssid"] = "HomeNet"
    data["evse"]["cands"] = [{"ip": "192.168.1.42", "mac": "aa:bb:cc:dd:ee:ff"}]
    aioclient_mock.get(API_URL, json=data)
    entry = make_entry(api_key=API_KEY)
    await _setup(hass, entry)

    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    text = str(diag)
    assert API_KEY not in text
    assert "HomeNet" not in text and "admin" not in text and "aa:bb:cc:dd:ee:ff" not in text
    assert diag["entry"]["data"]["api_key"] == "**REDACTED**"
    assert diag["api"]["dev"] == DEV
    assert diag["coordinator"]["control_available"] is True
    assert diag["coordinator"]["update_interval_s"] == 15
