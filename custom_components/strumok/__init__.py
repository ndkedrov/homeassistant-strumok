"""Інтеграція СтрумОК для Home Assistant (HACS custom component).

Опитує локальний HTTP API плати (`GET /api`) і показує зарядну станцію як
пристрій у Home Assistant. Керування зарядкою (`switch`, `number`, `button`) —
через `POST /api/evse/cmd`, лише якщо прошивка його має (блок `auth` у `/api`)
і в інтеграції задано ключ API (HA-FULL-CONTRACT §3).
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .coordinator import StrumokConfigEntry, StrumokDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: StrumokConfigEntry) -> bool:
    """Перший опит плати й підняття платформ."""
    coordinator = StrumokDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: StrumokConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
