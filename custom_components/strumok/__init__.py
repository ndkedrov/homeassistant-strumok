"""Інтеграція СтрумОК для Home Assistant (HACS custom component).

Опитує локальний, вже наявний на платі HTTP API (`GET /api`, без
автентифікації — контракт `docs/HOME-ASSISTANT-DEVICE-INTEGRATION.md` §1)
і показує зарядну станцію СтрумОК як пристрій у Home Assistant. Лише
READ-ONLY сенсори (§0 контракту): `/api` не має жодного ендпоінту
керування зарядкою, тому ця інтеграція нічого не вмикає й не вимикає.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import StrumokDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Створити координатор опитування для цього config entry й підняти платформи."""
    coordinator = StrumokDataUpdateCoordinator(
        hass,
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
