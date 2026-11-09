"""Config flow: ручне додавання, DHCP/zeroconf, reauth, reconfigure, параметри."""

from __future__ import annotations

from datetime import timedelta
from ipaddress import ip_address
from unittest.mock import patch

import aiohttp
import pytest

from homeassistant.config_entries import SOURCE_DHCP, SOURCE_USER, SOURCE_ZEROCONF, ConfigEntryState
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.strumok.const import DOMAIN

from .conftest import API_KEY, API_URL, CMD_URL, DEV, HOST, make_entry

NEW_HOST = "192.168.1.99"


def _dhcp(ip: str = HOST, mac: str = "e89f6db694f0") -> DhcpServiceInfo:
    return DhcpServiceInfo(ip=ip, hostname="strumok-b694f0", macaddress=mac)


def _zeroconf(ip: str = HOST, uid: str = DEV) -> ZeroconfServiceInfo:
    return ZeroconfServiceInfo(
        ip_address=ip_address(ip),
        ip_addresses=[ip_address(ip)],
        hostname="sk-e89f6db694f0.local.",
        name=f"{uid}._strumok._tcp.local.",
        port=80,
        type="_strumok._tcp.local.",
        properties={"uid": uid, "fw": "0.16.2", "auth": "1"},
    )


# ── user ─────────────────────────────────────────────────────────────────────
async def test_user_flow_without_key(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_full) -> None:
    aioclient_mock.get(API_URL, json=api_full)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: f" {HOST} "})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == DEV
    assert result["data"] == {CONF_HOST: HOST, CONF_PORT: 80}
    assert result["result"].unique_id == DEV
    # Без ключа — жодного POST на плату.
    assert all(call[0] == "GET" for call in aioclient_mock.mock_calls)


async def test_user_flow_with_key_checks_it_without_side_effects(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_control
) -> None:
    aioclient_mock.get(API_URL, json=api_control)
    aioclient_mock.post(CMD_URL, status=422, json={"error": "empty"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_API_KEY: API_KEY}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_API_KEY] == API_KEY
    posts = [call for call in aioclient_mock.mock_calls if call[0] == "POST"]
    assert len(posts) == 1
    method, url, body, headers = posts[0]
    assert str(url) == CMD_URL
    assert body == {}  # порожня команда: плата відповідає 422 empty ще до дії
    assert headers["Authorization"] == f"Bearer {API_KEY}"


@pytest.mark.parametrize(
    ("get_kwargs", "post_kwargs", "user_input", "error_field", "error"),
    [
        ({"exc": aiohttp.ClientError()}, None, {CONF_HOST: HOST}, "base", "cannot_connect"),
        ({"exc": TimeoutError()}, None, {CONF_HOST: HOST}, "base", "cannot_connect"),
        ({"status": 500}, None, {CONF_HOST: HOST}, "base", "cannot_connect"),
        ({"text": "<html>router</html>"}, None, {CONF_HOST: HOST}, "base", "cannot_connect"),
        ({"json": {"hello": 1}}, None, {CONF_HOST: HOST}, "base", "not_strumok"),
        ({"status": 401, "json": {"error": "auth"}}, None, {CONF_HOST: HOST}, "base", "auth_required"),
        (
            {"status": 401, "json": {"error": "auth"}},
            None,
            {CONF_HOST: HOST, CONF_API_KEY: API_KEY},
            "base",
            "invalid_auth",
        ),
        (
            "control",
            {"status": 401, "json": {"error": "auth"}},
            {CONF_HOST: HOST, CONF_API_KEY: API_KEY},
            "base",
            "invalid_auth",
        ),
        (None, None, {CONF_HOST: HOST, CONF_API_KEY: "not-a-key"}, CONF_API_KEY, "invalid_key_format"),
    ],
)
async def test_user_flow_errors_then_recover(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    api_full,
    api_control,
    get_kwargs,
    post_kwargs,
    user_input,
    error_field,
    error,
) -> None:
    if get_kwargs == "control":
        aioclient_mock.get(API_URL, json=api_control)
    elif get_kwargs is not None:
        aioclient_mock.get(API_URL, **get_kwargs)
    if post_kwargs is not None:
        aioclient_mock.post(CMD_URL, **post_kwargs)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {error_field: error}

    # Після виправлення форма проходить.
    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, json=api_full)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_already_configured_updates_host(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_full
) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    aioclient_mock.get(f"http://{NEW_HOST}/api", json=api_full)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: NEW_HOST})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == NEW_HOST


# ── DHCP / zeroconf ──────────────────────────────────────────────────────────
async def test_dhcp_discovery_confirm(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_full) -> None:
    aioclient_mock.get(API_URL, json=api_full)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp())
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"] == {"name": DEV, "host": HOST}
    flows = hass.config_entries.flow.async_progress()
    assert flows[0]["context"]["title_placeholders"] == {"name": DEV}
    assert flows[0]["context"]["unique_id"] == DEV

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: HOST, CONF_PORT: 80}
    assert result["result"].unique_id == DEV


async def test_dhcp_known_station_new_ip_updates_host_without_http(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp(ip=NEW_HOST)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == NEW_HOST
    # unique_id виведено з MAC — у плату навіть не стукали.
    assert aioclient_mock.call_count == 0


async def test_dhcp_unreachable_aborts(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(API_URL, exc=aiohttp.ClientError())
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp())
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_dhcp_not_strumok_aborts(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(API_URL, json={"router": True})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp())
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_strumok"


async def test_dhcp_closed_reads_asks_for_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_control
) -> None:
    aioclient_mock.get(API_URL, status=401, json={"error": "auth"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp())
    assert result["step_id"] == "discovery_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "auth_required"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, json=api_control)
    aioclient_mock.post(CMD_URL, status=422, json={"error": "empty"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: API_KEY})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_API_KEY] == API_KEY


async def test_zeroconf_discovery(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_full) -> None:
    aioclient_mock.get(API_URL, json=api_full)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=_zeroconf()
    )
    assert result["step_id"] == "discovery_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == DEV


async def test_zeroconf_known_station_updates_host(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=_zeroconf(ip=NEW_HOST)
    )
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == NEW_HOST


async def test_zeroconf_ipv6_ignored(hass: HomeAssistant) -> None:
    info = _zeroconf()
    info.ip_address = ip_address("fe80::1")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_ZEROCONF}, data=info)
    assert result["reason"] == "not_ipv4_address"


# ── reauth / reconfigure ─────────────────────────────────────────────────────
async def test_reauth_flow(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_control) -> None:
    entry = make_entry(api_key="sk_" + "00" * 24)
    entry.add_to_hass(hass)
    aioclient_mock.get(API_URL, json=api_control)
    aioclient_mock.post(CMD_URL, status=401, json={"error": "auth"})

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "sk_" + "bb" * 24})
    assert result["errors"] == {"base": "invalid_auth"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, json=api_control)
    aioclient_mock.post(CMD_URL, status=422, json={"error": "empty"})
    with patch("custom_components.strumok.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: API_KEY})
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_KEY] == API_KEY


async def test_reauth_other_station_aborts(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_full
) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    other = dict(api_full, dev="SK-111111111111")
    aioclient_mock.get(API_URL, json=other)
    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: API_KEY})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"


async def test_reconfigure_keeps_key_when_left_empty(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_full
) -> None:
    entry = make_entry(api_key=API_KEY)
    entry.add_to_hass(hass)
    aioclient_mock.get(f"http://{NEW_HOST}/api", json=api_full)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    with patch("custom_components.strumok.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: NEW_HOST})
        await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == NEW_HOST
    assert entry.data[CONF_API_KEY] == API_KEY


# ── options ──────────────────────────────────────────────────────────────────
async def test_options_flow_applies_interval_without_reload(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_full
) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    aioclient_mock.get(API_URL, json=api_full)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    assert coordinator.update_interval == timedelta(seconds=15)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    with patch.object(hass.config_entries, "async_reload") as reload:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL: 60}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_SCAN_INTERVAL: 60}
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is coordinator  # той самий координатор — без перезавантаження
    assert coordinator.update_interval == timedelta(seconds=60)
    reload.assert_not_called()


@pytest.mark.parametrize("value", [4, 301])
async def test_options_flow_rejects_out_of_range(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_full, value
) -> None:
    from homeassistant.data_entry_flow import InvalidData

    entry = make_entry()
    entry.add_to_hass(hass)
    aioclient_mock.get(API_URL, json=api_full)
    assert await hass.config_entries.async_setup(entry.entry_id)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(result["flow_id"], {CONF_SCAN_INTERVAL: value})


async def test_coordinator_uses_saved_interval(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, api_full
) -> None:
    entry = make_entry(options={CONF_SCAN_INTERVAL: 120})
    entry.add_to_hass(hass)
    aioclient_mock.get(API_URL, json=api_full)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.runtime_data.update_interval == timedelta(seconds=120)
