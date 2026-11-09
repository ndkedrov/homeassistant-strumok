"""Config flow СтрумОК: ручне додавання, автовиявлення, ключ API, reauth, параметри.

- `user` — хост плати + необовʼязковий ключ API;
- `dhcp` — hostname `strumok-*` або вже відомий MAC (`registered_devices`):
  unique_id виводиться з MAC (`dev` = `SK-` + MAC станції), тож зміна IP
  оновлюється навіть без звернення до плати;
- `zeroconf` — `_strumok._tcp.local.` (TXT `uid`, `fw`, `auth`), якщо прошивка
  оголошує службу (LOCAL-AUTONOMY-CONTRACT §3.6: лише плати з PSRAM);
- `discovery_confirm` — підтвердження з назвою коробки (і ключ, якщо треба);
- `reauth_confirm` — новий ключ після 401;
- `reconfigure` — змінити хост/ключ без видалення інтеграції;
- параметри — інтервал опиту 5–300 с, застосовується одразу.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from . import parser
from .api import StrumokAuthError, StrumokClient, StrumokConnectionError
from .const import (
    API_KEY_PREFIX,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL_S,
    DOMAIN,
    MAX_SCAN_INTERVAL_S,
    MIN_SCAN_INTERVAL_S,
)

_LOGGER = logging.getLogger(__name__)

_KEY_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


class _NotStrumok(Exception):
    """За адресою відповідає не плата СтрумОК (немає `dev`)."""


async def _async_probe(hass: HomeAssistant, host: str, api_key: str | None) -> dict[str, Any]:
    """Постукати в плату; повернути `dev`, `fw`, чи вміє вона команди.

    Якщо ключ задано і прошивка вміє локальні команди — ключ перевіряється
    порожньою командою (без жодної дії на платі, див. `StrumokClient.async_check_key`).
    """
    client = StrumokClient(async_get_clientsession(hass), host, api_key=api_key)
    data = await client.async_get_status()
    dev = parser.device_id(data)
    if not dev:
        raise _NotStrumok
    control = parser.supports_local_control(data)
    if api_key and control:
        await client.async_check_key()
    return {"dev": dev, "fw": parser.firmware_version(data), "control": control}


class StrumokConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow для інтеграції СтрумОК."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._dev: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> StrumokOptionsFlow:
        return StrumokOptionsFlow()

    async def _async_validate(
        self, host: str, api_key: str | None
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        errors: dict[str, str] = {}
        if api_key and not api_key.startswith(API_KEY_PREFIX):
            errors[CONF_API_KEY] = "invalid_key_format"
            return None, errors
        try:
            info = await _async_probe(self.hass, host, api_key)
        except StrumokAuthError:
            errors["base"] = "invalid_auth" if api_key else "auth_required"
        except StrumokConnectionError:
            errors["base"] = "cannot_connect"
        except _NotStrumok:
            errors["base"] = "not_strumok"
        except Exception:  # noqa: BLE001 — будь-що інше не має валити форму
            _LOGGER.exception("Неочікувана помилка під час перевірки плати %s", host)
            errors["base"] = "unknown"
        else:
            return info, errors
        return None, errors

    @callback
    def _create(self, host: str, api_key: str | None, info: dict[str, Any]) -> ConfigFlowResult:
        data: dict[str, Any] = {CONF_HOST: host, CONF_PORT: DEFAULT_PORT}
        if api_key:
            data[CONF_API_KEY] = api_key
        return self.async_create_entry(title=info["dev"], data=data)

    # ── ручне додавання ──────────────────────────────────────────────────────
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            api_key = (user_input.get(CONF_API_KEY) or "").strip() or None
            info, errors = await self._async_validate(host, api_key)
            if info is not None:
                await self.async_set_unique_id(info["dev"])
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self._create(host, api_key, info)

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_API_KEY): _KEY_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                schema, {CONF_HOST: user_input[CONF_HOST]} if user_input else {}
            ),
            errors=errors,
        )

    # ── автовиявлення ────────────────────────────────────────────────────────
    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        return await self._async_handle_discovery(
            discovery_info.ip, parser.device_id_from_mac(discovery_info.macaddress)
        )

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        if discovery_info.ip_address.version != 4:
            return self.async_abort(reason="not_ipv4_address")
        uid = discovery_info.properties.get("uid")
        dev = uid if isinstance(uid, str) and parser.mac_from_device_id(uid) else None
        return await self._async_handle_discovery(discovery_info.host, dev)

    async def _async_handle_discovery(self, host: str, dev: str | None) -> ConfigFlowResult:
        if dev:
            await self.async_set_unique_id(dev)
            # Уже додана плата з новим IP — оновити хост і перезавантажити запис.
            self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        client = StrumokClient(async_get_clientsession(self.hass), host)
        try:
            data = await client.async_get_status()
        except StrumokAuthError:
            # Читання закрите — коробку знаємо з MAC/uid, ключ попросимо на підтвердженні.
            data = None
        except StrumokConnectionError:
            return self.async_abort(reason="cannot_connect")

        if data is not None:
            real = parser.device_id(data)
            if not real:
                return self.async_abort(reason="not_strumok")
            if real != dev:
                await self.async_set_unique_id(real)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                dev = real
        elif not dev:
            return self.async_abort(reason="cannot_connect")

        self._host = host
        self._dev = dev
        self.context["title_placeholders"] = {"name": dev}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._host is not None and self._dev is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = (user_input.get(CONF_API_KEY) or "").strip() or None
            info, errors = await self._async_validate(self._host, api_key)
            if info is not None:
                if info["dev"] != self.unique_id:
                    await self.async_set_unique_id(info["dev"])
                    self._abort_if_unique_id_configured(updates={CONF_HOST: self._host})
                return self._create(self._host, api_key, info)

        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=vol.Schema({vol.Optional(CONF_API_KEY): _KEY_SELECTOR}),
            description_placeholders={"name": self._dev, "host": self._host},
            errors=errors,
        )

    # ── reauth: 401 від плати ────────────────────────────────────────────────
    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        host = entry.data[CONF_HOST]
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            info, errors = await self._async_validate(host, api_key)
            if info is not None:
                await self.async_set_unique_id(info["dev"])
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_KEY: api_key}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): _KEY_SELECTOR}),
            description_placeholders={"name": entry.title, "host": host},
            errors=errors,
        )

    # ── reconfigure: змінити хост / ключ ─────────────────────────────────────
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            # Порожнє поле ключа — лишити наявний ключ (секрет у форму не підставляємо).
            api_key = (user_input.get(CONF_API_KEY) or "").strip() or entry.data.get(CONF_API_KEY)
            info, errors = await self._async_validate(host, api_key)
            if info is not None:
                await self.async_set_unique_id(info["dev"])
                self._abort_if_unique_id_mismatch()
                data = {**entry.data, CONF_HOST: host}
                if api_key:
                    data[CONF_API_KEY] = api_key
                return self.async_update_reload_and_abort(entry, data=data)

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_API_KEY): _KEY_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                schema, {CONF_HOST: (user_input or entry.data)[CONF_HOST]}
            ),
            description_placeholders={"name": entry.title},
            errors=errors,
        )


class StrumokOptionsFlow(OptionsFlow):
    """Інтервал опиту; новий інтервал діє одразу, без перезапуску HA."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            seconds = int(user_input[CONF_SCAN_INTERVAL])
            entry = self.config_entry
            if entry.state is ConfigEntryState.LOADED:
                coordinator = entry.runtime_data
                coordinator.async_set_scan_interval(timedelta(seconds=seconds))
                # Опит зараз — і далі вже з новим інтервалом (_schedule_refresh після оновлення).
                await coordinator.async_request_refresh()
            return self.async_create_entry(data={CONF_SCAN_INTERVAL: seconds})

        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL_S,
                        max=MAX_SCAN_INTERVAL_S,
                        step=1,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    CONF_SCAN_INTERVAL: self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_S
                    )
                },
            ),
        )
