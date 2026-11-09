"""Number `charging_current`: уставка струму заряду, А.

`POST /api/evse/cmd {"current_a": N}`; стан — `evse.cur` (уставка, яку
зарядка прийняла). Межі — як у сервера: від max(7, `evse.min_a`) до
`evse.max` (або 16 А, поки зарядка не сказала свій максимум), `parser.current_limits`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.core import HomeAssistant

from . import parser
from .coordinator import StrumokConfigEntry, StrumokDataUpdateCoordinator
from .entity import StrumokCommandEntity, async_setup_dynamic_entities

if TYPE_CHECKING:
    # AddConfigEntryEntitiesCallback зʼявився в HA 2025.3; лише для типів,
    # щоб компонент вантажився й на 2025.2 (мінімум у hacs.json).
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

PARALLEL_UPDATES = 1

CHARGING_CURRENT = NumberEntityDescription(
    key="charging_current",
    translation_key="charging_current",
    device_class=NumberDeviceClass.CURRENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
    native_step=1,
    mode=NumberMode.SLIDER,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StrumokConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    def candidates(coordinator: StrumokDataUpdateCoordinator):
        if coordinator.control_available:
            yield CHARGING_CURRENT.key, lambda: StrumokChargingCurrent(coordinator, CHARGING_CURRENT)

    async_setup_dynamic_entities(entry, async_add_entities, candidates)


class StrumokChargingCurrent(StrumokCommandEntity, NumberEntity):
    """Уставка струму керованої зарядки."""

    def _reported(self) -> float | None:
        value = parser.charging_current_a(self.data)
        return float(value) if isinstance(value, (int, float)) else None

    @property
    def native_value(self) -> float | None:
        return self._current()

    @property
    def native_min_value(self) -> float:
        return float(parser.current_limits(self.data)[0])

    @property
    def native_max_value(self) -> float:
        return float(parser.current_limits(self.data)[1])

    async def async_set_native_value(self, value: float) -> None:
        amps = int(round(value))
        await self.coordinator.async_command({"current_a": amps})
        self._set_pending(float(amps))
