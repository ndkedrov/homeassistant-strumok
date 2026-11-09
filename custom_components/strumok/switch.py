"""Switch `charging_enabled`: дозволити / призупинити заряд.

`POST /api/evse/cmd {"enabled": true|false}`; стан — `evse.on`. Та сама точка
входу, що й команда із застосунку (`evse::applyServerCommand`, `source:"local"`),
тож межі й ручна витримка зарядки ті самі. Сутність зʼявляється лише коли
прошивка вміє локальні команди (блок `auth` у `/api`) і задано ключ API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant

from . import parser
from .coordinator import StrumokConfigEntry, StrumokDataUpdateCoordinator
from .entity import StrumokCommandEntity, async_setup_dynamic_entities

PARALLEL_UPDATES = 1

CHARGING_ENABLED = SwitchEntityDescription(
    key="charging_enabled",
    translation_key="charging_enabled",
)

if TYPE_CHECKING:
    # AddConfigEntryEntitiesCallback зʼявився в HA 2025.3; лише для типів,
    # щоб компонент вантажився й на 2025.2 (мінімум у hacs.json).
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StrumokConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    def candidates(coordinator: StrumokDataUpdateCoordinator):
        if coordinator.control_available:
            yield CHARGING_ENABLED.key, lambda: StrumokChargingSwitch(coordinator, CHARGING_ENABLED)

    async_setup_dynamic_entities(entry, async_add_entities, candidates)


class StrumokChargingSwitch(StrumokCommandEntity, SwitchEntity):
    """Дозвіл заряду на керованій зарядці."""

    def _reported(self) -> bool | None:
        return parser.charging_allowed(self.data)

    @property
    def is_on(self) -> bool | None:
        return self._current()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_command({"enabled": True})
        self._set_pending(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_command({"enabled": False})
        self._set_pending(False)
