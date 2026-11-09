"""Керування: switch/number/button → POST /api/evse/cmd; тіла запитів і обробка 401/409/422."""

from __future__ import annotations

import aiohttp
import pytest

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.components.number import ATTR_VALUE, DOMAIN as NUMBER_DOMAIN, SERVICE_SET_VALUE
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.strumok.const import DOMAIN

from .conftest import API_KEY, API_URL, CMD_URL, clone, make_entry


def _eid(hass: HomeAssistant, domain: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"strumok_ske89f6db694f0_{key}")
    assert entity_id, f"{domain}.{key} не створено"
    return entity_id


@pytest.fixture
async def loaded(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_control):
    aioclient_mock.get(API_URL, json=api_control)
    entry = make_entry(api_key=API_KEY)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _posts(aioclient_mock: AiohttpClientMocker) -> list:
    return [call for call in aioclient_mock.mock_calls if call[0] == "POST"]


async def test_control_entities_exist_with_key_and_auth_block(hass: HomeAssistant, loaded) -> None:
    switch = hass.states.get(_eid(hass, SWITCH_DOMAIN, "charging_enabled"))
    assert switch.state == STATE_ON  # evse.on = 1
    number = hass.states.get(_eid(hass, NUMBER_DOMAIN, "charging_current"))
    assert number.state == "16.0"  # evse.cur
    assert number.attributes["min"] == 7  # max(7, min_a=6)
    assert number.attributes["max"] == 32  # evse.max
    assert number.attributes["unit_of_measurement"] == "A"
    assert hass.states.get(_eid(hass, BUTTON_DOMAIN, "phase_reset")) is not None


@pytest.mark.parametrize("has_key", [False, True])
async def test_no_control_without_key_or_without_firmware_support(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_full, api_control, has_key
) -> None:
    # has_key=False: прошивка вміє, але ключа немає; has_key=True: ключ є, прошивка стара.
    aioclient_mock.get(API_URL, json=api_control if not has_key else api_full)
    entry = make_entry(api_key=API_KEY if has_key else None)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    registry = er.async_get(hass)
    for domain, key in (
        (SWITCH_DOMAIN, "charging_enabled"),
        (NUMBER_DOMAIN, "charging_current"),
        (BUTTON_DOMAIN, "phase_reset"),
    ):
        assert registry.async_get_entity_id(domain, DOMAIN, f"strumok_ske89f6db694f0_{key}") is None


async def test_switch_turn_off_and_on_bodies(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded, api_control
) -> None:
    aioclient_mock.post(CMD_URL, json={"ok": True, "id": "local1"})
    entity_id = _eid(hass, SWITCH_DOMAIN, "charging_enabled")

    await hass.services.async_call(SWITCH_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity_id}, blocking=True)
    # Плата ще показує on=1 (команда в черзі) — перемикач не «відскакує».
    assert hass.states.get(entity_id).state == STATE_OFF
    await hass.services.async_call(SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True)

    posts = _posts(aioclient_mock)
    assert [p[2] for p in posts] == [{"enabled": False}, {"enabled": True}]
    assert all(p[3]["Authorization"] == f"Bearer {API_KEY}" for p in posts)
    assert all(str(p[1]) == CMD_URL for p in posts)


async def test_switch_pending_clears_when_board_confirms(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded, api_control
) -> None:
    aioclient_mock.post(CMD_URL, json={"ok": True})
    entity_id = _eid(hass, SWITCH_DOMAIN, "charging_enabled")
    await hass.services.async_call(SWITCH_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity_id}, blocking=True)

    confirmed = clone(api_control)
    confirmed["evse"]["on"] = 0
    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, json=confirmed)
    await loaded.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_OFF

    # Далі стан іде від плати: хтось увімкнув заряд із застосунку.
    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, json=api_control)
    await loaded.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_ON


async def test_number_sets_current(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded) -> None:
    aioclient_mock.post(CMD_URL, json={"ok": True})
    entity_id = _eid(hass, NUMBER_DOMAIN, "charging_current")
    await hass.services.async_call(
        NUMBER_DOMAIN, SERVICE_SET_VALUE, {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 24}, blocking=True
    )
    assert [p[2] for p in _posts(aioclient_mock)] == [{"current_a": 24}]
    assert hass.states.get(entity_id).state == "24.0"


async def test_number_out_of_range_rejected_locally(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded
) -> None:
    entity_id = _eid(hass, NUMBER_DOMAIN, "charging_current")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            NUMBER_DOMAIN, SERVICE_SET_VALUE, {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 40}, blocking=True
        )
    assert _posts(aioclient_mock) == []


async def test_button_phase_reset(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded) -> None:
    aioclient_mock.post(CMD_URL, json={"ok": True})
    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: _eid(hass, BUTTON_DOMAIN, "phase_reset")}, blocking=True
    )
    assert [p[2] for p in _posts(aioclient_mock)] == [{"phase_reset": True}]


async def test_409_no_charger(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded) -> None:
    aioclient_mock.post(CMD_URL, status=409, json={"error": "no_charger", "msg": "Зарядку не знайдено"})
    entity_id = _eid(hass, SWITCH_DOMAIN, "charging_enabled")
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(SWITCH_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity_id}, blocking=True)
    assert err.value.translation_key == "command_conflict"
    assert err.value.translation_placeholders == {"message": "Зарядку не знайдено"}
    # Команда не пройшла — оптимістичного стану немає.
    assert hass.states.get(entity_id).state == STATE_ON


async def test_422_invalid(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded) -> None:
    aioclient_mock.post(
        CMD_URL, status=422, json={"error": "invalid", "fields": {"current_a": "від 7 до 48"}}
    )
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: _eid(hass, NUMBER_DOMAIN, "charging_current"), ATTR_VALUE: 20},
            blocking=True,
        )
    assert err.value.translation_key == "command_invalid"


async def test_401_on_command_starts_reauth(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded) -> None:
    aioclient_mock.post(CMD_URL, status=401, json={"error": "auth"})
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: _eid(hass, BUTTON_DOMAIN, "phase_reset")}, blocking=True
        )
    assert err.value.translation_key == "command_auth_failed"
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]


async def test_network_error_on_command(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded) -> None:
    aioclient_mock.post(CMD_URL, exc=aiohttp.ClientError())
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: _eid(hass, SWITCH_DOMAIN, "charging_enabled")},
            blocking=True,
        )
    assert err.value.translation_key == "cannot_connect"


async def test_old_firmware_404(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded) -> None:
    aioclient_mock.post(CMD_URL, status=404, text="Not found")
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: _eid(hass, BUTTON_DOMAIN, "phase_reset")}, blocking=True
        )
    assert err.value.translation_key == "command_unsupported"
