"""Діагностика (Налаштування → Пристрої → СтрумОК → «Завантажити діагностику»).

Секрети вирізаються: ключ API, логіни/паролі/токени, назва Wi-Fi, MAC-адреси
сусідніх пристроїв. `dev` лишається — без нього діагностика нічого не варта.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from . import parser
from .coordinator import StrumokConfigEntry

TO_REDACT = {
    CONF_API_KEY,
    "app_key",
    "key",
    "local_key",
    "mac",
    "pass",
    "password",
    "psk",
    "ssid",
    "token",
    "user",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: StrumokConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    data = coordinator.data or {}
    return {
        "entry": {
            "title": entry.title,
            "unique_id": entry.unique_id,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_s": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
            "has_api_key": coordinator.has_api_key,
            "supports_local_control": parser.supports_local_control(data),
            "control_available": coordinator.control_available,
        },
        "api": async_redact_data(data, TO_REDACT),
    }
