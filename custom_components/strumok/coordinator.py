"""DataUpdateCoordinator: опитує локальний `/api` плати й виконує команди.

Один `GET /api` на цикл віддає весь стан плати (`fillStatus`); розбір полів —
чисті функції `parser.py`. Помилка мережі одного циклу → `UpdateFailed`
(сутності `unavailable` до наступного вдалого опиту). 401 → `ConfigEntryAuthFailed`:
HA сам запускає reauth, де користувач вводить ключ API.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import parser
from .api import (
    StrumokAuthError,
    StrumokClient,
    StrumokCommandError,
    StrumokConnectionError,
)
from .const import DEFAULT_PORT, DEFAULT_SCAN_INTERVAL_S, DOMAIN

_LOGGER = logging.getLogger(__name__)

type StrumokConfigEntry = ConfigEntry[StrumokDataUpdateCoordinator]


def scan_interval_of(entry: ConfigEntry) -> timedelta:
    """Інтервал опиту з параметрів запису (options flow), типово 15 с."""
    return timedelta(seconds=int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_S)))


class StrumokDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Опитує `GET http://<host>/api` з інтервалом із параметрів запису."""

    config_entry: StrumokConfigEntry

    def __init__(self, hass: HomeAssistant, entry: StrumokConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}:{entry.data[CONF_HOST]}",
            update_interval=scan_interval_of(entry),
        )
        self.client = StrumokClient(
            async_get_clientsession(hass),
            entry.data[CONF_HOST],
            api_key=entry.data.get(CONF_API_KEY),
            port=entry.data.get(CONF_PORT, DEFAULT_PORT),
        )
        self._last_fw: str | None = None

    @property
    def host(self) -> str:
        return self.client.host

    @property
    def device_id(self) -> str:
        """`dev` плати; до першого опиту — unique_id запису або хост."""
        return (
            parser.device_id(self.data or {})
            or self.config_entry.unique_id
            or self.client.host
        )

    @property
    def has_api_key(self) -> bool:
        return bool(self.client.api_key)

    @property
    def control_available(self) -> bool:
        """Керування — лише якщо прошивка вміє локальні команди І ключ задано (§3)."""
        return self.has_api_key and parser.supports_local_control(self.data or {})

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.client.async_get_status()
        except StrumokAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except StrumokConnectionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"host": self.client.host, "error": str(err)},
            ) from err
        self._sync_firmware_version(data)
        return data

    def _sync_firmware_version(self, data: dict[str, Any]) -> None:
        """Після OTA оновити `sw_version` пристрою без перезавантаження інтеграції."""
        fw = parser.firmware_version(data)
        if fw is None or fw == self._last_fw:
            return
        first = self._last_fw is None
        self._last_fw = fw
        if first:
            return  # перший опит: device_info сутностей і так несе цю версію
        dev = parser.device_id(data)
        if not dev:
            return
        # async_entries_for_config_entry — а не async_get_device: той з HA 2026.9
        # застарів (ідентифікатори більше не унікальні між записами), а цей
        # працює однаково від 2025.2 до сьогодні.
        registry = dr.async_get(self.hass)
        for device in dr.async_entries_for_config_entry(registry, self.config_entry.entry_id):
            if (DOMAIN, dev) in device.identifiers:
                registry.async_update_device(device.id, sw_version=fw)

    def async_set_scan_interval(self, interval: timedelta) -> None:
        """Застосувати новий інтервал одразу (options flow) — без перезапуску."""
        self.update_interval = interval

    async def async_command(self, payload: dict[str, Any]) -> None:
        """`POST /api/evse/cmd` і людські помилки для сервісних викликів HA."""
        try:
            await self.client.async_command(payload)
        except StrumokAuthError as err:
            # Ключ відкликали або вхід на платі увімкнули пізніше — просимо новий.
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="command_auth_failed"
            ) from err
        except StrumokCommandError as err:
            placeholders = {"message": err.message or err.code or str(err.status)}
            if err.status == 422:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="command_invalid",
                    translation_placeholders=placeholders,
                ) from err
            if err.status == 409:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="command_conflict",
                    translation_placeholders=placeholders,
                ) from err
            if err.status in (404, 405, 501):
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="command_unsupported"
                ) from err
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders=placeholders,
            ) from err
        except StrumokConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"host": self.client.host},
            ) from err
        await self.async_request_refresh()
